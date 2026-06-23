from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ringkas_worker.db.logs import (
    MESSAGE_MAX_LENGTH,
    STEP_NAME_MAX_LENGTH,
    IngestionLogRepository,
    IngestionLogValidationError,
)


class FakeCursor:
    def __init__(self, row):
        self.row = row
        self.executed: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        self.executed.append((query, params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row]


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance


def persisted_row(job_id, document_id=None):
    return (uuid4(), job_id, document_id, "info", "download started", {"step_name": "download"}, datetime.now(timezone.utc))


def test_append_uses_parameterized_sql_and_returns_typed_record():
    job_id = uuid4()
    cursor = FakeCursor(persisted_row(job_id))
    repository = IngestionLogRepository("unused", lambda: FakeConnection(cursor))

    result = repository.append(job_id, "info", "download started", step_name="download", retry_count=0)

    assert result.job_id == job_id
    assert result.metadata_json == {"step_name": "download"}
    assert "%s" in cursor.executed[0][0]
    assert "download started" not in cursor.executed[0][0]
    assert cursor.executed[0][1][1] == job_id


@pytest.mark.parametrize(
    ("level", "message", "step_name", "retry_count", "code"),
    [
        ("debug", "message", None, None, "invalid_level"),
        ("info", "", None, None, "invalid_message"),
        ("info", " \t\n", None, None, "invalid_message"),
        ("info", "x" * (MESSAGE_MAX_LENGTH + 1), None, None, "invalid_message"),
        ("info", "message", " ", None, "invalid_step_name"),
        ("info", "message", "x" * (STEP_NAME_MAX_LENGTH + 1), None, "invalid_step_name"),
        ("info", "message", None, -1, "invalid_retry_count"),
        ("info", "message", None, True, "invalid_retry_count"),
        ("info", "message", None, 1.5, "invalid_retry_count"),
        ("info", "SECRET_MARKER=abc", None, None, "unsafe_message"),
        ("info", "message", "api_key=abc", None, "unsafe_step_name"),
    ],
)
def test_append_rejects_invalid_or_sensitive_input(level, message, step_name, retry_count, code):
    repository = IngestionLogRepository("unused", lambda: pytest.fail("database must not be called"))

    with pytest.raises(IngestionLogValidationError) as error:
        repository.append(uuid4(), level, message, step_name=step_name, retry_count=retry_count)

    assert error.value.code == code
    assert "SECRET_MARKER" not in str(error.value)


def test_invalid_identifiers_are_sanitized():
    repository = IngestionLogRepository("unused", lambda: pytest.fail("database must not be called"))

    with pytest.raises(IngestionLogValidationError, match="must be a UUID"):
        repository.append("not-a-uuid", "info", "message")


def test_raw_exception_object_is_rejected_without_persisting_it():
    repository = IngestionLogRepository("unused", lambda: pytest.fail("database must not be called"))

    with pytest.raises(IngestionLogValidationError) as error:
        repository.append(uuid4(), "error", RuntimeError("SECRET_MARKER"))

    assert error.value.code == "invalid_message"
    assert str(error.value) == "message must not be blank"
