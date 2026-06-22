import os
from collections.abc import Iterator
from datetime import datetime
from uuid import UUID, uuid4

import psycopg
import pytest


TEST_DSN_ENV = "RINGKAS_POSTGRES_TEST_URL"


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


def insert_document(connection: psycopg.Connection, document_id: UUID | None = None) -> UUID:
    document_id = document_id or uuid4()
    connection.execute(
        """
        INSERT INTO documents (
            id, title, publication_year, region, region_level,
            source_page_url, ingestion_status, checksum
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (document_id, "Chunk schema fixture", 2025, "DKI Jakarta", "province",
         "https://example.invalid/chunk-schema", "pending", f"chunk-{document_id}"),
    )
    return document_id


def insert_chunk(
    connection: psycopg.Connection,
    document_id: UUID,
    *,
    chunk_id: UUID | None = None,
    chunk_index: int = 0,
    text: str = "A valid chunk of extracted text.",
    page_start: int | None = 1,
    page_end: int | None = 1,
    section_heading: str | None = "Overview",
    extraction_method: str = "text_layer",
    low_structure_confidence: bool = False,
    source_url: str = "https://example.invalid/chunk.pdf",
    qdrant_point_id: str = "point-1",
) -> UUID:
    chunk_id = chunk_id or uuid4()
    connection.execute(
        """
        INSERT INTO chunks (
            id, document_id, chunk_index, text, page_start, page_end,
            section_heading, extraction_method, low_structure_confidence,
            source_url, qdrant_point_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (chunk_id, document_id, chunk_index, text, page_start, page_end,
         section_heading, extraction_method, low_structure_confidence,
         source_url, qdrant_point_id),
    )
    return chunk_id


def test_chunks_columns_types_and_nullability(database: psycopg.Connection) -> None:
    columns = {
        row[0]: (row[1], row[2])
        for row in database.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'chunks'
            """
        )
    }
    assert columns == {
        "id": ("uuid", "NO"),
        "document_id": ("uuid", "NO"),
        "chunk_index": ("integer", "NO"),
        "text": ("text", "NO"),
        "page_start": ("integer", "YES"),
        "page_end": ("integer", "YES"),
        "section_heading": ("text", "YES"),
        "extraction_method": ("text", "NO"),
        "low_structure_confidence": ("boolean", "NO"),
        "source_url": ("text", "NO"),
        "qdrant_point_id": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    }


def test_valid_chunk_round_trip_and_timezone_aware_created_at(database: psycopg.Connection) -> None:
    document_id = insert_document(database)
    chunk_id = insert_chunk(database, document_id)
    row = database.execute(
        "SELECT document_id, chunk_index, text, page_start, page_end, section_heading, "
        "extraction_method, low_structure_confidence, source_url, qdrant_point_id, created_at "
        "FROM chunks WHERE id = %s",
        (chunk_id,),
    ).fetchone()
    assert row is not None
    assert row[:10] == (
        document_id, 0, "A valid chunk of extracted text.", 1, 1, "Overview",
        "text_layer", False, "https://example.invalid/chunk.pdf", "point-1",
    )
    assert isinstance(row[10], datetime)
    assert row[10].tzinfo is not None


def test_unknown_document_is_rejected(database: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with database.transaction():
            insert_chunk(database, uuid4())


def test_duplicate_document_chunk_index_is_rejected(database: psycopg.Connection) -> None:
    document_id = insert_document(database)
    insert_chunk(database, document_id)
    with pytest.raises(psycopg.errors.UniqueViolation):
        with database.transaction():
            insert_chunk(database, document_id, chunk_id=uuid4(), qdrant_point_id="point-2")


def test_duplicate_qdrant_point_id_is_rejected(database: psycopg.Connection) -> None:
    document_id = insert_document(database)
    insert_chunk(database, document_id)
    with pytest.raises(psycopg.errors.UniqueViolation):
        with database.transaction():
            insert_chunk(database, document_id, chunk_index=1, qdrant_point_id="point-1")


@pytest.mark.parametrize("overrides", [
    {"chunk_index": -1},
    {"page_start": 0, "page_end": 1},
    {"page_start": 1, "page_end": 0},
    {"page_start": 2, "page_end": 1},
    {"page_start": None, "page_end": 1},
    {"page_start": 1, "page_end": None},
    {"extraction_method": "ocr"},
    {"text": ""},
    {"text": " \t\n"},
    {"source_url": ""},
    {"source_url": "  \t"},
    {"qdrant_point_id": ""},
    {"qdrant_point_id": " \n"},
])
def test_invalid_chunk_values_are_rejected(
    database: psycopg.Connection, overrides: dict[str, object]
) -> None:
    document_id = insert_document(database)
    with pytest.raises(psycopg.errors.CheckViolation):
        with database.transaction():
            insert_chunk(database, document_id, **overrides)


def test_document_delete_cascades_to_chunks(database: psycopg.Connection) -> None:
    document_id = insert_document(database)
    insert_chunk(database, document_id)
    database.execute("DELETE FROM documents WHERE id = %s", (document_id,))
    assert database.execute("SELECT count(*) FROM chunks WHERE document_id = %s", (document_id,)).fetchone() == (0,)


def test_transaction_rollback_leaves_no_partial_chunk_records(database: psycopg.Connection) -> None:
    document_id = insert_document(database)
    chunk_id = uuid4()
    with pytest.raises(psycopg.errors.CheckViolation):
        with database.transaction():
            insert_chunk(database, document_id, chunk_id=chunk_id, qdrant_point_id="rollback-point")
            insert_chunk(database, document_id, chunk_index=1, text=" ", qdrant_point_id="rollback-point-2")
    assert database.execute("SELECT count(*) FROM chunks WHERE id = %s", (chunk_id,)).fetchone() == (0,)


def test_required_indexes_exist_and_are_unique(database: psycopg.Connection) -> None:
    indexes = {
        row[0]: row[1]
        for row in database.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = 'chunks'"
        )
    }
    assert "IX_chunks_document_id_chunk_index" in indexes
    assert "IX_chunks_qdrant_point_id" in indexes
    assert "UNIQUE" in indexes["IX_chunks_document_id_chunk_index"]
    assert "UNIQUE" in indexes["IX_chunks_qdrant_point_id"]
