import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

import psycopg


@dataclass(frozen=True, slots=True)
class IngestionJob:
    id: UUID
    requested_by_user_id: str
    status: str
    scope_region: str
    scope_year_start: int
    scope_year_end: int
    max_documents: int
    started_at: datetime | None
    heartbeat_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    error_summary: str | None


ConnectionFactory = Callable[[], psycopg.Connection]


class IngestionJobRepository:
    def __init__(
        self,
        database_url: str,
        connection_factory: ConnectionFactory | None = None,
        connect_timeout_seconds: int = 10,
        statement_timeout_ms: int = 30_000,
    ) -> None:
        self._database_url = database_url
        self._connection_factory = connection_factory or self._connect
        self._connect_timeout_seconds = connect_timeout_seconds
        self._statement_timeout_ms = statement_timeout_ms

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self._database_url,
            connect_timeout=self._connect_timeout_seconds,
            options=f"-c statement_timeout={self._statement_timeout_ms}",
        )

    def has_queued_job(self) -> bool:
        """Observe queue state without locking or changing a job."""
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM ingestion_jobs WHERE status = %s LIMIT 1",
                    ("queued",),
                )
                return cursor.fetchone() is not None

    def claim_next_job(self) -> IngestionJob | None:
        """Atomically lock the oldest queued job and transition it to running."""
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, requested_by_user_id, status, scope_region,
                           scope_year_start, scope_year_end, max_documents,
                           started_at, heartbeat_at, completed_at, created_at, error_summary
                    FROM ingestion_jobs
                    WHERE status = %s
                    ORDER BY created_at ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                    ("queued",),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                started_at = datetime.now(timezone.utc)
                cursor.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = %s, started_at = %s, heartbeat_at = %s
                    WHERE id = %s AND status = %s
                    RETURNING id, requested_by_user_id, status, scope_region,
                              scope_year_start, scope_year_end, max_documents,
                              started_at, heartbeat_at, completed_at, created_at, error_summary
                    """,
                    ("running", started_at, started_at, row[0], "queued"),
                )
                claimed = cursor.fetchone()
                return _to_job(claimed) if claimed is not None else None

    def heartbeat(self, job_id: UUID) -> bool:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE ingestion_jobs SET heartbeat_at = CURRENT_TIMESTAMP WHERE id = %s AND status = %s",
                    (job_id, "running"),
                )
                return cursor.rowcount == 1

    def requeue_stale_jobs(self, timeout_seconds: int) -> int:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingestion_jobs
                    SET status = %s, started_at = NULL, heartbeat_at = NULL, completed_at = NULL, error_summary = NULL
                    WHERE status = %s
                      AND COALESCE(heartbeat_at, started_at) IS NOT NULL
                      AND COALESCE(heartbeat_at, started_at) < CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                    """,
                    ("queued", "running", timeout_seconds),
                )
                return cursor.rowcount

    def mark_completed(self, job_id: UUID) -> bool:
        return self._mark_terminal(job_id, "completed", None)

    def mark_failed(self, job_id: UUID, safe_error_summary: str) -> bool:
        if not isinstance(safe_error_summary, str) or not safe_error_summary.strip():
            raise ValueError("safe_error_summary must be nonblank")
        summary = _safe_summary(safe_error_summary)
        return self._mark_terminal(job_id, "failed", summary)

    def _mark_terminal(self, job_id: UUID, status: str, summary: str | None) -> bool:
        completed_at = datetime.now(timezone.utc)
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE ingestion_jobs
                       SET status = %s, heartbeat_at = NULL, completed_at = %s, error_summary = %s
                       WHERE id = %s AND status = %s""",
                    (status, completed_at, summary, job_id, "running"),
                )
                return cursor.rowcount == 1


def _to_job(row: tuple | None) -> IngestionJob | None:
    if row is None:
        return None
    return IngestionJob(*row)


def _safe_summary(value: str) -> str:
    normalized = " ".join(value.split())[:2000]
    if re.search(r"(?i)(traceback|authorization|bearer|api[_-]?key|database[_-]?url|password|secret|postgres(?:ql)?://)", normalized):
        return "systemic ingestion failure"
    return normalized
