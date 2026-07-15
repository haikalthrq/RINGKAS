from __future__ import annotations

from uuid import uuid4

import pytest

from ringkas_worker.dimension import DimensionVerificationError, verify_embedding_dimension
from ringkas_worker.embedding import EmbeddingBatchResult, EmbeddingVector
from ringkas_worker.indexing import ChunkIndexingResult, IndexableChunk
from ringkas_worker.reindex import FileReindexCheckpoint, InMemoryReindexCheckpoint, ReindexProgress, ReindexRunner


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
        return ChunkIndexingResult("ringkas_chunks_cf_qwen3_embedding_v1", len(chunks), tuple(c.qdrant_point_id for c in chunks), tuple(str(c.chunk_id) for c in chunks))


def test_reindex_isolated_resumable_and_reports_progress():
    first, second = chunk(str(uuid4())), chunk(str(uuid4()))
    checkpoint = InMemoryReindexCheckpoint([first.qdrant_point_id])
    progress: list[ReindexProgress] = []
    indexer = FakeIndexer()
    result = ReindexRunner(FakeSource([(first, second)]), indexer, checkpoint, progress.append).run()
    assert result == ReindexProgress(2, 1, 1, None)
    assert [item.qdrant_point_id for item in indexer.calls[0]] == [second.qdrant_point_id]
    assert progress[-1] == result


def test_file_checkpoint_survives_runner_restart(tmp_path):
    path = str(tmp_path / "reindex.json")
    checkpoint = FileReindexCheckpoint(path)
    checkpoint.mark_complete(["point-1"])
    restored = FileReindexCheckpoint(path)
    assert restored.is_complete("point-1")
