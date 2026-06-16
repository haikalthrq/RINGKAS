import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest

from ringkas_worker.db.jobs import IngestionJobRepository


DATABASE_URL = os.getenv("RINGKAS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set RINGKAS_TEST_DATABASE_URL for PostgreSQL integration tests",
)


def insert_fixture_jobs(first_id, second_id, user_id):
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """
            INSERT INTO "AspNetUsers"
                ("Id", "EmailConfirmed", "PhoneNumberConfirmed", "TwoFactorEnabled", "LockoutEnabled", "AccessFailedCount")
            VALUES (%s, false, false, false, false, 0)
            """,
            (user_id,),
        )
        connection.execute(
            """
            INSERT INTO ingestion_jobs
                (id, requested_by_user_id, status, scope_region, scope_year_start,
                 scope_year_end, max_documents, created_at)
            VALUES (%s, %s, 'queued', 'DKI Jakarta', 2022, 2026, 10, %s),
                   (%s, %s, 'queued', 'DKI Jakarta', 2022, 2026, 10, %s)
            """,
            (
                first_id,
                user_id,
                datetime(2020, 1, 1, tzinfo=timezone.utc),
                second_id,
                user_id,
                datetime(2021, 1, 1, tzinfo=timezone.utc),
            ),
        )


def cleanup_fixture(first_id, second_id, user_id):
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("DELETE FROM ingestion_jobs WHERE id IN (%s, %s)", (first_id, second_id))
        connection.execute('DELETE FROM "AspNetUsers" WHERE "Id" = %s', (user_id,))


def test_skip_locked_claims_newer_job_while_oldest_lock_is_held() -> None:
    first_id, second_id = uuid4(), uuid4()
    user_id = f"worker-test-{uuid4()}"
    insert_fixture_jobs(first_id, second_id, user_id)
    locked = threading.Event()
    release_lock = threading.Event()

    def hold_oldest_lock() -> None:
        connection = psycopg.connect(DATABASE_URL)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM ingestion_jobs
                    WHERE status = 'queued'
                    ORDER BY created_at ASC, id ASC
                    FOR UPDATE
                    LIMIT 1
                    """
                )
            locked.set()
            release_lock.wait(timeout=10)
            connection.rollback()
        finally:
            connection.close()

    holder = threading.Thread(target=hold_oldest_lock)
    holder.start()
    try:
        assert locked.wait(timeout=10)
        newer = IngestionJobRepository(DATABASE_URL).claim_next_job()
        assert newer is not None
        assert newer.id == second_id
        assert newer.status == "running"
        assert newer.started_at is not None

        release_lock.set()
        holder.join(timeout=10)
        assert not holder.is_alive()

        oldest = IngestionJobRepository(DATABASE_URL).claim_next_job()
        assert oldest is not None
        assert oldest.id == first_id
        assert oldest.status == "running"
        assert oldest.started_at is not None
    finally:
        release_lock.set()
        holder.join(timeout=10)
        cleanup_fixture(first_id, second_id, user_id)


def test_single_job_has_one_successful_concurrent_claim() -> None:
    first_id = uuid4()
    user_id = f"worker-test-{uuid4()}"
    insert_fixture_jobs(first_id, uuid4(), user_id)
    second_id = None
    with psycopg.connect(DATABASE_URL) as connection:
        second_id = connection.execute(
            "SELECT id FROM ingestion_jobs WHERE requested_by_user_id = %s AND id <> %s",
            (user_id, first_id),
        ).fetchone()[0]
        connection.execute("DELETE FROM ingestion_jobs WHERE id = %s", (second_id,))
    try:
        barrier = threading.Barrier(2)

        def claim():
            barrier.wait(timeout=10)
            return IngestionJobRepository(DATABASE_URL).claim_next_job()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: claim(), range(2)))
        successful = [job for job in results if job is not None]
        assert len(successful) == 1
        assert successful[0].id == first_id
    finally:
        cleanup_fixture(first_id, second_id, user_id)


class FailingAfterUpdateCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def execute(self, query, params=None):
        result = self._cursor.execute(query, params)
        if query.lstrip().upper().startswith("UPDATE INGESTION_JOBS"):
            raise psycopg.Error("intentional failure after actual claim update")
        return result

    def fetchone(self):
        return self._cursor.fetchone()


class FailingAfterUpdateConnection:
    def __init__(self, connection):
        self._connection = connection

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *args):
        return self._connection.__exit__(*args)

    def cursor(self):
        return FailingAfterUpdateCursor(self._connection.cursor())


def test_actual_claim_rolls_back_after_update_failure() -> None:
    first_id = uuid4()
    user_id = f"worker-test-{uuid4()}"
    insert_fixture_jobs(first_id, uuid4(), user_id)
    second_id = None
    with psycopg.connect(DATABASE_URL) as connection:
        second_id = connection.execute(
            "SELECT id FROM ingestion_jobs WHERE requested_by_user_id = %s AND id <> %s",
            (user_id, first_id),
        ).fetchone()[0]
        connection.execute("DELETE FROM ingestion_jobs WHERE id = %s", (second_id,))
    try:
        def failing_connection():
            return FailingAfterUpdateConnection(psycopg.connect(DATABASE_URL))

        with pytest.raises(psycopg.Error, match="intentional failure"):
            IngestionJobRepository(DATABASE_URL, connection_factory=failing_connection).claim_next_job()

        with psycopg.connect(DATABASE_URL) as connection:
            assert connection.execute(
                "SELECT status, started_at FROM ingestion_jobs WHERE id = %s",
                (first_id,),
            ).fetchone() == ("queued", None)

        claimed = IngestionJobRepository(DATABASE_URL).claim_next_job()
        assert claimed is not None
        assert claimed.id == first_id
    finally:
        cleanup_fixture(first_id, second_id, user_id)
