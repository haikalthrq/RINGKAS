import os
from collections.abc import Iterator
from uuid import UUID, uuid4

import psycopg
import pytest


TEST_DSN_ENV = "RINGKAS_POSTGRES_TEST_URL"
FIXTURE_TITLE = "schema-integration-fixture"


@pytest.fixture()
def database() -> Iterator[psycopg.Connection]:
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        pytest.skip(f"{TEST_DSN_ENV} is not configured")

    connection = psycopg.connect(dsn)
    try:
        yield connection
    finally:
        if connection.closed == 0:
            connection.rollback()
        connection.close()


def insert_document(
    connection: psycopg.Connection,
    *,
    publication_year: int = 2025,
    page_count: int | None = None,
    ingestion_status: str = "pending",
    checksum: str | None = "schema-test-checksum",
    document_id: UUID | None = None,
) -> UUID:
    document_id = document_id or uuid4()
    connection.execute(
        """
        INSERT INTO documents (
            id, title, publication_year, region, region_level,
            source_page_url, page_count, ingestion_status, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            document_id,
            FIXTURE_TITLE,
            publication_year,
            "DKI Jakarta",
            "province",
            "https://example.invalid/schema-test",
            page_count,
            ingestion_status,
            checksum,
        ),
    )
    return document_id


def test_documents_and_existing_tables_exist(database: psycopg.Connection) -> None:
    tables = {
        row[0]
        for row in database.execute(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename IN ('documents', 'ingestion_jobs', 'AspNetUsers')
            """
        )
    }
    assert tables == {"documents", "ingestion_jobs", "AspNetUsers"}


def test_document_defaults_and_timezone_aware_created_at(database: psycopg.Connection) -> None:
    document_id = insert_document(database)
    row = database.execute(
        "SELECT ingestion_status, created_at FROM documents WHERE id = %s",
        (document_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == "pending"
    assert row[1] is not None
    column = database.execute(
        """
        SELECT data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'documents'
          AND column_name = 'created_at'
        """
    ).fetchone()
    assert column is not None
    assert column[0] == "timestamp with time zone"
    assert column[1] == "NO"
    assert "CURRENT_TIMESTAMP" in (column[2] or "")


def test_all_allowed_ingestion_statuses_are_accepted(database: psycopg.Connection) -> None:
    statuses = {"pending", "downloaded", "parsed", "indexed", "failed", "unsupported_or_extraction_failed"}
    ids = [insert_document(database, ingestion_status=status) for status in statuses]
    stored = {
        row[0]
        for row in database.execute("SELECT ingestion_status FROM documents WHERE id = ANY(%s)", (ids,))
    }
    assert stored == statuses


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("ingestion_status", "invalid"),
        ("publication_year", 0),
        ("publication_year", -1),
        ("page_count", 0),
        ("page_count", -1),
    ],
)
def test_invalid_document_values_are_rejected(
    database: psycopg.Connection, column: str, value: object
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        insert_document(database, **{column: value})


def test_page_count_null_and_checksum_required(database: psycopg.Connection) -> None:
    document_id = insert_document(database, page_count=None)
    assert database.execute("SELECT page_count FROM documents WHERE id = %s", (document_id,)).fetchone() == (None,)

    with pytest.raises(psycopg.errors.NotNullViolation):
        insert_document(database, checksum=None)


def test_required_indexes_exist_and_checksum_is_not_unique(database: psycopg.Connection) -> None:
    indexes = {
        row[0]: row[1]
        for row in database.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'documents'
            """
        )
    }
    assert {
        "IX_documents_publication_year",
        "IX_documents_region",
        "IX_documents_ingestion_status",
        "IX_documents_checksum",
    } <= indexes.keys()
    checksum_unique = database.execute(
        "SELECT indisunique FROM pg_index WHERE indexrelid = '\"IX_documents_checksum\"'::regclass"
    ).fetchone()
    assert checksum_unique == (False,)
