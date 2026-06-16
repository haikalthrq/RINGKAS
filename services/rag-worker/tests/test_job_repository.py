from datetime import datetime, timezone
from uuid import uuid4

from ringkas_worker.db.jobs import IngestionJobRepository


class FakeCursor:
    def __init__(self, rows: list[tuple | None]) -> None:
        self.rows = iter(rows)
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query: str, params: tuple) -> None:
        self.executed.append((query, params))

    def fetchone(self):
        return next(self.rows)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance


def job_row(job_id):
    now = datetime.now(timezone.utc)
    return (job_id, "user", "queued", "DKI Jakarta", 2022, 2026, 300, None, None, now, None)


def test_claim_uses_locking_query_and_returns_running_job() -> None:
    job_id = uuid4()
    cursor = FakeCursor([job_row(job_id), (*job_row(job_id)[:2], "running", *job_row(job_id)[3:6], job_row(job_id)[6], datetime.now(timezone.utc), None, job_row(job_id)[9], None)])
    repository = IngestionJobRepository("unused", lambda: FakeConnection(cursor))

    claimed = repository.claim_next_job()

    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.status == "running"
    assert claimed.started_at is not None
    assert "FOR UPDATE SKIP LOCKED" in cursor.executed[0][0]
    assert cursor.executed[0][1] == ("queued",)


def test_no_queued_job_returns_none() -> None:
    repository = IngestionJobRepository("unused", lambda: FakeConnection(FakeCursor([None])))
    assert repository.claim_next_job() is None
