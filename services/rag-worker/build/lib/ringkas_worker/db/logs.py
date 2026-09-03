from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb


MESSAGE_MAX_LENGTH = 2000
STEP_NAME_MAX_LENGTH = 128
ALLOWED_METADATA_KEYS = frozenset({"step_name", "retry_count"})
_UNSAFE_INPUT = re.compile(
    r"(?i)(traceback\s*\(most recent call last\)|authorization\s*[:=]|bearer\s+|"
    r"api[_-]?key\s*[:=]|database[_-]?url\s*[:=]|password\s*[:=]|secret[_-]?marker|"
    r"cookie\s*[:=]|postgres(?:ql)?://)"
)
# This is a known-sensitive-pattern defense, not a complete secret detector. Callers
# must provide sanitized summaries rather than str(exception), tracebacks, or raw errors.


class IngestionLogValidationError(ValueError):
    """A sanitized, stable validation error safe to expose to callers."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class IngestionLog:
    id: UUID
    job_id: UUID
    document_id: UUID | None
    level: str
    message: str
    metadata_json: dict[str, str | int] | None
    created_at: datetime


ConnectionFactory = Callable[[], psycopg.Connection]


class IngestionLogRepository:
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

    def append(
        self,
        job_id: UUID,
        level: str,
        message: str,
        document_id: UUID | None = None,
        step_name: str | None = None,
        retry_count: int | None = None,
    ) -> IngestionLog:
        """Persist a caller-provided sanitized summary, never raw exception/provider errors."""
        _validate_uuid(job_id, "job_id")
        _validate_uuid(document_id, "document_id", nullable=True)
        _validate_level(level)
        _validate_message(message)
        _validate_step_name(step_name)
        _validate_retry_count(retry_count)
        metadata = _build_metadata(step_name, retry_count)
        log_id = uuid4()
        created_at = datetime.now(timezone.utc)

        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ingestion_logs
                        (id, job_id, document_id, level, message, metadata_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, job_id, document_id, level, message, metadata_json, created_at
                    """,
                    (log_id, job_id, document_id, level, message, Jsonb(metadata) if metadata is not None else None, created_at),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("ingestion log insert returned no row")
                return _to_log(row)

    def recent(self, job_id: UUID, limit: int = 100) -> list[IngestionLog]:
        _validate_uuid(job_id, "job_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise IngestionLogValidationError("invalid_limit", "limit must be between 1 and 1000")
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, job_id, document_id, level, message, metadata_json, created_at
                    FROM ingestion_logs
                    WHERE job_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (job_id, limit),
                )
                return [_to_log(row) for row in cursor.fetchall()]


def _build_metadata(step_name: str | None, retry_count: int | None) -> dict[str, str | int] | None:
    metadata: dict[str, str | int] = {}
    if step_name is not None:
        metadata["step_name"] = step_name
    if retry_count is not None:
        metadata["retry_count"] = retry_count
    return metadata or None


def _validate_uuid(value: object, field: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, UUID):
        raise IngestionLogValidationError("invalid_identifier", f"{field} must be a UUID")


def _validate_level(level: object) -> None:
    if not isinstance(level, str) or level not in {"info", "warn", "error"}:
        raise IngestionLogValidationError("invalid_level", "level must be info, warn, or error")


def _validate_message(message: object) -> None:
    if not isinstance(message, str) or not message.strip():
        raise IngestionLogValidationError("invalid_message", "message must not be blank")
    if len(message) > MESSAGE_MAX_LENGTH:
        raise IngestionLogValidationError("invalid_message", "message exceeds the maximum length")
    if _UNSAFE_INPUT.search(message):
        raise IngestionLogValidationError("unsafe_message", "message contains prohibited sensitive content")


def _validate_step_name(step_name: object) -> None:
    if step_name is not None and (not isinstance(step_name, str) or not step_name.strip()):
        raise IngestionLogValidationError("invalid_step_name", "step_name must not be blank")
    if isinstance(step_name, str) and len(step_name) > STEP_NAME_MAX_LENGTH:
        raise IngestionLogValidationError("invalid_step_name", "step_name exceeds the maximum length")
    if isinstance(step_name, str) and _UNSAFE_INPUT.search(step_name):
        raise IngestionLogValidationError("unsafe_step_name", "step_name contains prohibited sensitive content")


def _validate_retry_count(retry_count: object) -> None:
    if retry_count is not None and (
        isinstance(retry_count, bool) or not isinstance(retry_count, int) or retry_count < 0
    ):
        raise IngestionLogValidationError("invalid_retry_count", "retry_count must be a non-negative integer")


def _to_log(row: tuple) -> IngestionLog:
    metadata = row[5]
    return IngestionLog(row[0], row[1], row[2], row[3], row[4], metadata, row[6])
