from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ringkas_worker.chunking import TextChunk
from ringkas_worker.db.chunks import ChunkPersistenceError, ChunkRepository


class Cursor:
    def __init__(self, rows=(), fail_insert=False, fail_on_insert_number=None):
        self.rows = list(rows)
        self.statements = []
        self.fail_insert = fail_insert
        self.fail_on_insert_number = fail_on_insert_number
        self.insert_count = 0
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params):
        self.statements.append((sql, params))
        if sql.startswith("INSERT"):
            self.insert_count += 1
        if (self.fail_insert or self.insert_count == self.fail_on_insert_number) and sql.startswith("INSERT"):
            raise RuntimeError("database secret=do-not-leak")
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor; self.exit_error = None
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_value, _traceback): self.exit_error = exc_value; return False
    def cursor(self): return self.cursor_value


def chunk(index=0, text="text"):
    return TextChunk(text, index, 1, 1, "Heading")


def row(document_id, index=0, text="text", point_id="point"):
    return (uuid4(), document_id, index, text, 1, 1, "Heading", "text_layer", False,
            "https://bps.example/source", point_id, datetime.now(timezone.utc))


def test_duplicate_input_indexes_are_rejected_before_connecting():
    repository = ChunkRepository("unused", lambda: pytest.fail("database must not be contacted"))
    with pytest.raises(ChunkPersistenceError, match="duplicate indexes"):
        repository.persist_for_document(uuid4(), (chunk(), chunk()), "https://bps.example/source")


def test_exact_retry_reuses_existing_ids_and_parameterizes_select():
    document_id, existing = uuid4(), None
    existing = row(document_id)
    cursor = Cursor([existing])
    result = ChunkRepository("unused", lambda: Connection(cursor)).persist_for_document(
        document_id, (chunk(),), "https://bps.example/source")
    assert result[0].id == existing[0]
    assert result[0].qdrant_point_id == "point"
    assert len(cursor.statements) == 1
    assert "%s" in cursor.statements[0][0]
    assert cursor.statements[0][1] == (document_id,)


def test_stale_existing_indexes_are_rejected_without_insert():
    document_id = uuid4()
    cursor = Cursor([row(document_id, index=0), row(document_id, index=1, point_id="point-2")])
    with pytest.raises(ChunkPersistenceError, match="indexes conflict"):
        ChunkRepository("unused", lambda: Connection(cursor)).persist_for_document(
            document_id, (chunk(0),), "https://bps.example/source")
    assert len(cursor.statements) == 1


def test_conflicting_metadata_is_rejected_without_replacement():
    document_id = uuid4()
    cursor = Cursor([row(document_id, text="different")])
    with pytest.raises(ChunkPersistenceError, match="metadata conflicts"):
        ChunkRepository("unused", lambda: Connection(cursor)).persist_for_document(
            document_id, (chunk(),), "https://bps.example/source")
    assert len(cursor.statements) == 1


def test_new_batch_inserts_parameterized_rows():
    cursor = Cursor()
    result = ChunkRepository("unused", lambda: Connection(cursor)).persist_for_document(
        uuid4(), (chunk(),), "https://bps.example/source")
    assert len(result) == 1
    assert cursor.statements[1][0].startswith("INSERT INTO chunks")
    assert "%s" in cursor.statements[1][0]


def test_later_insert_failure_exits_transaction_with_error_and_no_partial_commit():
    cursor = Cursor(fail_on_insert_number=2)
    connection = Connection(cursor)
    repository = ChunkRepository("unused", lambda: connection)
    with pytest.raises(RuntimeError, match="database secret"):
        repository.persist_for_document(uuid4(), (chunk(0), chunk(1, "second")), "https://bps.example/source")
    assert cursor.insert_count == 2
    assert connection.exit_error is not None
