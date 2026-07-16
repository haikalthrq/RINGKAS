from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from ringkas_worker.dimension import (
    DimensionVerificationError,
    verify_embedding_dimension,
    verify_live_dimension_from_environment,
)
from ringkas_worker.embedding import EmbeddingBatchResult, EmbeddingVector
from ringkas_worker.indexing import ChunkIndexingResult, IndexableChunk
from ringkas_worker.reindex import (
    COLLECTION_NAME,
    MODEL,
    PROVIDER,
    SCHEMA_VERSION,
    FileReindexCheckpoint,
    InMemoryReindexCheckpoint,
    MigrationIdentity,
    ReindexBatchError,
    ReindexCheckpointError,
    ReindexProgress,
    ReindexRunner,
)


class FakeEmbedding:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def embed(self, texts):
        self.calls.append(texts)
        if self.error:
            raise self.error
        return self.result


def verified_result(dimension=3, model="@cf/qwen/qwen3-embedding-0.6b"):
    vectors = tuple(EmbeddingVector(i, tuple(1.0 for _ in range(dimension))) for i in range(2))
    return EmbeddingBatchResult(vectors, dimension, model)


def test_dimension_verifier_uses_synthetic_batch_and_returns_provider_dimension():
    client = FakeEmbedding(verified_result(3))
    result = verify_embedding_dimension(client)
    assert result.dimension == 3
    assert client.calls == [("RINGKAS dimension verification sample.", "RINGKAS second sample.")]


def test_dimension_verifier_rejects_configured_dimension_mismatch_before_mutation():
    with pytest.raises(DimensionVerificationError):
        verify_embedding_dimension(FakeEmbedding(verified_result(3)), expected_dimension=4)


def test_live_verifier_requires_expected_dimension_before_provider_call(monkeypatch):
    monkeypatch.delenv("QDRANT_DENSE_VECTOR_SIZE", raising=False)

    def unexpected_provider_call():
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(
        "ringkas_worker.dimension.CloudflareWorkersAiEmbeddingSettings.from_environment",
        unexpected_provider_call,
    )
    with pytest.raises(DimensionVerificationError):
        verify_live_dimension_from_environment()


@pytest.mark.parametrize("result", [EmbeddingBatchResult((), 0), EmbeddingBatchResult((EmbeddingVector(0, (1.0,)), EmbeddingVector(1, (1.0, 2.0))), 1)])
def test_dimension_verifier_rejects_inconsistent_or_zero_dimension(result):
    with pytest.raises(DimensionVerificationError):
        verify_embedding_dimension(FakeEmbedding(result))


def test_dimension_verifier_sanitizes_provider_failure():
    with pytest.raises(DimensionVerificationError) as caught:
        verify_embedding_dimension(FakeEmbedding(error=RuntimeError("cloudflare-token-secret")))
    assert "cloudflare-token-secret" not in repr(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def chunk(point_id: str) -> IndexableChunk:
    return IndexableChunk(
        qdrant_point_id=point_id, chunk_id=uuid4(), document_id=uuid4(), text="authoritative text",
        title="Title", publication_year=2026, region="National", region_level="national",
        source_url="https://bps.example/source",
    )


def identity(dimension=3, distance="cosine"):
    return MigrationIdentity(PROVIDER, MODEL, COLLECTION_NAME, dimension, distance)


class FakeSource:
    def __init__(self, batches):
        self._batches = batches

    def batches(self, batch_size):
        yield from self._batches


class FakeIndexer:
    def __init__(self):
        self.calls = []

    def index(self, chunks):
        self.calls.append(tuple(chunks))
        return ChunkIndexingResult(COLLECTION_NAME, len(chunks), tuple(c.qdrant_point_id for c in chunks), tuple(str(c.chunk_id) for c in chunks))


def test_reindex_isolated_resumable_and_reports_progress():
    first, second = chunk(str(uuid4())), chunk(str(uuid4()))
    checkpoint = InMemoryReindexCheckpoint(identity(), [first.qdrant_point_id])
    progress: list[ReindexProgress] = []
    indexer = FakeIndexer()
    result = ReindexRunner(FakeSource([(first, second)]), indexer, checkpoint, progress.append).run()
    assert result == ReindexProgress(2, 1, 1, None)
    assert [item.qdrant_point_id for item in indexer.calls[0]] == [second.qdrant_point_id]
    assert checkpoint.is_complete(second.qdrant_point_id)
    assert progress[-1] == result


def test_file_checkpoint_survives_runner_restart(tmp_path):
    path = str(tmp_path / "reindex.json")
    checkpoint = FileReindexCheckpoint(path, identity())
    checkpoint.mark_complete(["point-1"])
    restored = FileReindexCheckpoint(path, identity())
    assert restored.is_complete("point-1")


def test_checkpoint_contains_identity_and_rejects_foreign_or_corrupt_data(tmp_path):
    path = str(tmp_path / "reindex.json")
    checkpoint = FileReindexCheckpoint(path, identity())
    checkpoint.mark_complete(["point-1"])
    payload = json.loads(Path(path).read_text())
    assert payload["migration"] == identity().as_dict()
    with pytest.raises(Exception):
        FileReindexCheckpoint(path, identity(dimension=4))
    Path(path).write_text("not json")
    with pytest.raises(Exception):
        FileReindexCheckpoint(path, identity())


def test_checkpoint_schema_change_restarts_sparse_migration(tmp_path):
    path = str(tmp_path / "reindex.json")
    checkpoint = FileReindexCheckpoint(path, identity())
    checkpoint.mark_complete(["point-1"])
    payload = json.loads(Path(path).read_text())
    payload["migration"]["schema_version"] = SCHEMA_VERSION - 1
    Path(path).write_text(json.dumps(payload))

    with pytest.raises(ReindexCheckpointError):
        FileReindexCheckpoint(path, identity())


def test_failed_upsert_is_not_checkpointed_and_is_observable():
    item = chunk(str(uuid4()))

    class FailingIndexer:
        def index(self, chunks):
            raise RuntimeError("qdrant secret")

    checkpoint = InMemoryReindexCheckpoint(identity())
    progress: list[ReindexProgress] = []
    with pytest.raises(ReindexBatchError) as caught:
        ReindexRunner(FakeSource([(item,)]), FailingIndexer(), checkpoint, progress.append).run()
    assert not checkpoint.is_complete(item.qdrant_point_id)
    assert caught.value.progress == ReindexProgress(1, 0, 0, None, 1)
    assert progress[-1].failed == 1


def test_empty_corpus_completes_deterministically():
    result = ReindexRunner(FakeSource([]), FakeIndexer(), InMemoryReindexCheckpoint(identity())).run()
    assert result == ReindexProgress(0, 0, 0, None, 0)


def test_postgres_source_uses_authoritative_text_and_preserves_mapping():
    class Cursor:
        def __init__(self):
            self.rows = [(str(uuid4()), uuid4(), uuid4(), "database text", "Title", 2026, "National", "national", None, None, None, None, 0, "text_layer", False, "https://bps.example/source", None)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, query):
            assert "c.text" in query and "FROM chunks" in query

        def __iter__(self):
            return iter(self.rows)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def cursor(self):
            return Cursor()

    from ringkas_worker.reindex import PostgresChunkSource

    item = next(PostgresChunkSource("unused", lambda: Connection()).batches(1))[0]
    assert item.text == "database text"
    assert item.qdrant_point_id
