from uuid import uuid4

from ringkas_worker.db.documents import DocumentRepository
from ringkas_worker.db.jobs import IngestionJobRepository


class Cursor:
    def __init__(self, rowcount=1): self.rowcount = rowcount; self.statements = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params): self.statements.append((sql, params))


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return self.cursor_value


def test_job_terminal_transitions_are_parameterized_and_running_only():
    cursor = Cursor()
    repository = IngestionJobRepository("unused", lambda: Connection(cursor))
    assert repository.mark_completed(uuid4()) is True
    assert repository.mark_failed(uuid4(), "safe failure") is True
    assert all("status = %s" in statement[0] and "running" in statement[1] for statement in cursor.statements)
    assert all("%s" in statement[0] for statement in cursor.statements)


def test_job_terminal_transition_returns_false_for_terminal_row():
    repository = IngestionJobRepository("unused", lambda: Connection(Cursor(0)))
    assert repository.mark_completed(uuid4()) is False
    assert repository.mark_failed(uuid4(), "safe failure") is False


def test_document_transitions_are_parameterized_and_indexed_cannot_regress():
    cursor = Cursor()
    repository = DocumentRepository("unused", lambda: Connection(cursor))
    assert repository.mark_parsed(uuid4(), 2) is True
    assert repository.mark_indexed(uuid4()) is True
    assert repository.mark_failed(uuid4(), "safe failure") is True
    assert repository.mark_unsupported(uuid4(), "no_text", 2) is True
    indexed = cursor.statements[1]
    assert "ANY(%s)" in indexed[0]
    assert indexed[1][-1] == ["parsed", "indexed"]
    assert all("%s" in statement[0] for statement in cursor.statements)
