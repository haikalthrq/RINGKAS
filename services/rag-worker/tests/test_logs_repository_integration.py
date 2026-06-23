import os
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from ringkas_worker.db.logs import IngestionLogRepository, STEP_NAME_MAX_LENGTH

TEST_DSN_ENV = "RINGKAS_POSTGRES_TEST_URL"
TEST_USER_PREFIX = "log-test-"
TEST_CHECKSUM_PREFIX = "log-"


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


def insert_job(connection: psycopg.Connection, job_id: UUID, user_id: str) -> None:
    connection.execute(
        'INSERT INTO "AspNetUsers" ("Id", "EmailConfirmed", "PhoneNumberConfirmed", "TwoFactorEnabled", "LockoutEnabled", "AccessFailedCount") VALUES (%s, false, false, false, false, 0)',
        (user_id,),
    )
    connection.execute(
        "INSERT INTO ingestion_jobs (id, requested_by_user_id, status, scope_region, scope_year_start, scope_year_end, max_documents) VALUES (%s, %s, 'queued', 'DKI Jakarta', 2022, 2026, 10)",
        (job_id, user_id),
    )


def insert_document(connection: psycopg.Connection, document_id: UUID) -> None:
    connection.execute(
        "INSERT INTO documents (id, title, publication_year, region, region_level, source_page_url, ingestion_status, checksum) VALUES (%s, 'Log fixture', 2025, 'DKI Jakarta', 'province', 'https://example.invalid/log', 'pending', %s)",
        (document_id, f"{TEST_CHECKSUM_PREFIX}{document_id}"),
    )


def cleanup_fixture(job_id: UUID, user_id: str, document_id: UUID | None = None) -> None:
    with psycopg.connect(os.environ[TEST_DSN_ENV]) as connection:
        with connection.transaction():
            connection.execute(
                "DELETE FROM ingestion_logs WHERE job_id = %s OR document_id = %s",
                (job_id, document_id),
            )
            connection.execute("DELETE FROM ingestion_jobs WHERE id = %s", (job_id,))
            if document_id is not None:
                connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            connection.execute('DELETE FROM "AspNetUsers" WHERE "Id" = %s', (user_id,))


def assert_no_leftover_fixtures(database: psycopg.Connection) -> None:
    assert database.execute(
        'SELECT count(*) FROM "AspNetUsers" WHERE "Id" LIKE %s', (f"{TEST_USER_PREFIX}%",)
    ).fetchone() == (0,)
    assert database.execute(
        "SELECT count(*) FROM documents WHERE checksum LIKE %s", (f"{TEST_CHECKSUM_PREFIX}%",)
    ).fetchone() == (0,)
    assert database.execute(
        "SELECT count(*) FROM ingestion_jobs WHERE requested_by_user_id LIKE %s", (f"{TEST_USER_PREFIX}%",)
    ).fetchone() == (0,)
    assert database.execute(
        "SELECT count(*) FROM ingestion_logs l JOIN ingestion_jobs j ON j.id = l.job_id WHERE j.requested_by_user_id LIKE %s",
        (f"{TEST_USER_PREFIX}%",),
    ).fetchone() == (0,)


def test_schema_and_repository_round_trip(database: psycopg.Connection) -> None:
    columns = {
        row[0]: (row[1], row[2])
        for row in database.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'ingestion_logs'"
        )
    }
    assert columns == {
        "id": ("uuid", "NO"), "job_id": ("uuid", "NO"), "document_id": ("uuid", "YES"),
        "level": ("text", "NO"), "message": ("text", "NO"), "metadata_json": ("jsonb", "YES"),
        "created_at": ("timestamp with time zone", "NO"),
    }
    job_id, document_id, user_id = uuid4(), uuid4(), f"{TEST_USER_PREFIX}{uuid4()}"
    try:
        insert_job(database, job_id, user_id)
        insert_document(database, document_id)
        database.commit()
        log = IngestionLogRepository(os.environ[TEST_DSN_ENV]).append(job_id, "error", "document failed", document_id, "parse", 2)
        assert log.job_id == job_id and log.document_id == document_id
        assert log.metadata_json == {"step_name": "parse", "retry_count": 2}
        assert log.created_at.tzinfo is not None
        assert database.execute(
            "SELECT column_default FROM information_schema.columns WHERE table_name = 'ingestion_logs' AND column_name = 'created_at'"
        ).fetchone()[0] is not None
    finally:
        database.rollback()
        cleanup_fixture(job_id, user_id, document_id)


def test_foreign_keys_delete_behavior_and_duplicate_events(database: psycopg.Connection) -> None:
    job_id, document_id, user_id = uuid4(), uuid4(), f"{TEST_USER_PREFIX}{uuid4()}"
    try:
        insert_job(database, job_id, user_id)
        insert_document(database, document_id)
        database.execute(
            "INSERT INTO ingestion_logs (id, job_id, document_id, level, message, metadata_json) VALUES (%s, %s, %s, 'info', 'same event', %s), (%s, %s, %s, 'info', 'same event', NULL)",
            (uuid4(), job_id, document_id, Jsonb({"step_name": "x"}), uuid4(), job_id, document_id),
        )
        assert database.execute("SELECT count(*) FROM ingestion_logs WHERE job_id = %s", (job_id,)).fetchone() == (2,)
        database.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        assert database.execute("SELECT count(*) FROM ingestion_logs WHERE job_id = %s AND document_id IS NULL", (job_id,)).fetchone() == (2,)
        database.execute("DELETE FROM ingestion_jobs WHERE id = %s", (job_id,))
        assert database.execute("SELECT count(*) FROM ingestion_logs WHERE job_id = %s", (job_id,)).fetchone() == (0,)
    finally:
        database.rollback()
        cleanup_fixture(job_id, user_id, document_id)


def test_unknown_foreign_keys_and_recent_ordering(database: psycopg.Connection) -> None:
    job_id, user_id = uuid4(), f"{TEST_USER_PREFIX}{uuid4()}"
    try:
        insert_job(database, job_id, user_id)
        database.execute(
            "INSERT INTO ingestion_logs (id, job_id, level, message, created_at) VALUES (%s, %s, 'info', 'first', %s), (%s, %s, 'warn', 'second', %s)",
            (uuid4(), job_id, datetime(2025, 1, 1, tzinfo=timezone.utc), uuid4(), job_id, datetime(2025, 1, 2, tzinfo=timezone.utc)),
        )
        database.commit()
        assert [entry.message for entry in IngestionLogRepository(os.environ[TEST_DSN_ENV]).recent(job_id)] == ["second", "first"]
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with database.transaction():
                database.execute("INSERT INTO ingestion_logs (id, job_id, level, message) VALUES (%s, %s, 'info', 'unknown job')", (uuid4(), uuid4()))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with database.transaction():
                database.execute("INSERT INTO ingestion_logs (id, job_id, document_id, level, message) VALUES (%s, %s, %s, 'info', 'unknown document')", (uuid4(), job_id, uuid4()))
    finally:
        database.rollback()
        cleanup_fixture(job_id, user_id)


def test_transaction_rollback_leaves_no_partial_log(database: psycopg.Connection) -> None:
    job_id, user_id = uuid4(), f"{TEST_USER_PREFIX}{uuid4()}"
    try:
        insert_job(database, job_id, user_id)
        log_id = uuid4()
        with pytest.raises(psycopg.errors.CheckViolation):
            with database.transaction():
                database.execute("INSERT INTO ingestion_logs (id, job_id, level, message) VALUES (%s, %s, 'info', 'valid')", (log_id, job_id))
                database.execute("INSERT INTO ingestion_logs (id, job_id, level, message) VALUES (%s, %s, 'invalid', 'bad')", (uuid4(), job_id))
        assert database.execute("SELECT count(*) FROM ingestion_logs WHERE id = %s", (log_id,)).fetchone() == (0,)
    finally:
        database.rollback()
        cleanup_fixture(job_id, user_id)


def test_deleting_a_log_leaves_job_and_document_intact(database: psycopg.Connection) -> None:
    job_id, document_id, user_id = uuid4(), uuid4(), f"{TEST_USER_PREFIX}{uuid4()}"
    try:
        insert_job(database, job_id, user_id)
        insert_document(database, document_id)
        log_id = uuid4()
        database.execute("INSERT INTO ingestion_logs (id, job_id, document_id, level, message) VALUES (%s, %s, %s, 'info', 'removable')", (log_id, job_id, document_id))
        database.execute("DELETE FROM ingestion_logs WHERE id = %s", (log_id,))
        assert database.execute("SELECT count(*) FROM ingestion_jobs WHERE id = %s", (job_id,)).fetchone() == (1,)
        assert database.execute("SELECT count(*) FROM documents WHERE id = %s", (document_id,)).fetchone() == (1,)
    finally:
        database.rollback()
        cleanup_fixture(job_id, user_id, document_id)


@pytest.mark.parametrize("metadata", [
    ["step"], "step", 1, {"step_name": " "}, {"step_name": "x" * (STEP_NAME_MAX_LENGTH + 1)},
    {"retry_count": -1}, {"retry_count": 1.5}, {"unknown": "value"},
])
def test_invalid_metadata_is_rejected(database: psycopg.Connection, metadata) -> None:
    job_id, user_id = uuid4(), f"{TEST_USER_PREFIX}{uuid4()}"
    try:
        insert_job(database, job_id, user_id)
        with pytest.raises(psycopg.errors.CheckViolation):
            with database.transaction():
                database.execute("INSERT INTO ingestion_logs (id, job_id, level, message, metadata_json) VALUES (%s, %s, 'info', 'valid message', %s)", (uuid4(), job_id, Jsonb(metadata)))
    finally:
        database.rollback()
        cleanup_fixture(job_id, user_id)


def test_no_leftover_fixture_rows(database: psycopg.Connection) -> None:
    assert_no_leftover_fixtures(database)
