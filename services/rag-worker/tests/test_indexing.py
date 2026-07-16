from __future__ import annotations

import traceback
from uuid import uuid4

import pytest
from qdrant_client import models
from pydantic import SecretStr

from ringkas_worker.embedding import CloudflareWorkersAiEmbeddingClient, EmbeddingBatchResult, EmbeddingVector
from ringkas_worker.qdrant_setup import COLLECTION_NAME, LEGACY_COLLECTION_NAME
from ringkas_worker.sparse_retrieval import SparseQuery
from ringkas_worker.indexing import (
    ChunkIndexer,
    ChunkIndexingResult,
    EmbeddingIndexingFailure,
    EmbeddingValidationError,
    IndexableChunk,
    IndexingConfigurationError,
    InvalidIndexableChunkError,
    QdrantChunkIndexer,
    QdrantIndexingSettings,
    QdrantUpsertIncompleteError,
    QdrantIndexingTransportError,
    SparseIndexingFailure,
)


_MISSING = object()


class FakeEmbedding:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[tuple[str, ...], str | None, str | None]] = []

    def embed(self, texts, *, input_type=None, truncate=None):
        self.calls.append((tuple(texts), input_type, truncate))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeSparseEncoder:
    def __init__(self, result=None):
        self.result = result or SparseQuery((1,), (1.0,))
        self.calls = []

    def encode_documents(self, texts):
        values = tuple(texts)
        self.calls.append(values)
        return tuple(self.result for _ in values)

    def encode_query(self, query):
        return self.result


class FakeQdrant:
    def __init__(self, response=_MISSING, error=None) -> None:
        self.response = models.UpdateResult(status=models.UpdateStatus.COMPLETED, operation_id=1) if response is _MISSING else response
        self.error = error
        self.calls = []
        self.point_batches = []

    def upsert(self, collection_name, points, wait=True, **kwargs):
        self.point_batches.append(points)
        self.calls.append((collection_name, tuple(points), wait, kwargs))
        if self.error:
            raise self.error
        return self.response


def chunk(*, point=None, chunk_id=None, text=" unchanged  text ", **overrides):
    values = {
        "qdrant_point_id": point or str(uuid4()), "chunk_id": chunk_id or str(uuid4()), "document_id": str(uuid4()),
        "text": text, "title": "Publication", "publication_year": 2026, "region": "DKI Jakarta", "region_level": "province",
        "source_url": "https://bps.example/source",
    }
    values.update(overrides)
    return IndexableChunk(**values)


def indexer(embedding, qdrant=None):
    return QdrantChunkIndexer(
        embedding,
        qdrant or FakeQdrant(),
        QdrantIndexingSettings(qdrant_api_key=SecretStr(""), expected_dense_vector_size=2),
        FakeSparseEncoder(),
    )


def result(count=1, dimension=2, indexes=None, declared_dimension=_MISSING):
    indexes = indexes or list(range(count))
    return EmbeddingBatchResult(
        tuple(EmbeddingVector(i, tuple(float(i + 1) for _ in range(dimension))) for i in indexes),
        dimension if declared_dimension is _MISSING else declared_dimension,
    )


def test_protocol_and_valid_indexing_maps_exact_payload_and_named_dense_sparse_vectors():
    qdrant = FakeQdrant()
    embedding = FakeEmbedding(result(2))
    service = indexer(embedding, qdrant)
    assert isinstance(service, ChunkIndexer)
    first, second = chunk(), chunk()
    output = service.index([first, second], input_type="passage", truncate="END")
    assert isinstance(output, ChunkIndexingResult)
    assert output.point_ids == (first.qdrant_point_id, second.qdrant_point_id)
    assert embedding.calls == [((first.text, second.text), "passage", "END")]
    _, points, wait, _ = qdrant.calls[0]
    assert wait is True
    assert [point.id for point in points] == list(output.point_ids)
    assert all(set(point.vector) == {"dense", "sparse"} for point in points)
    assert points[0].vector["sparse"].indices == [1]
    assert points[0].vector["sparse"].values == [1.0]
    assert set(points[0].payload) == {
        "document_id", "chunk_id", "title", "publication_year", "region", "region_level", "topic",
        "page_start", "page_end", "section_heading", "chunk_index", "extraction_method",
        "low_structure_confidence", "source_url", "pdf_url",
    }
    assert points[0].payload["chunk_id"] == str(first.chunk_id)
    assert points[0].payload["topic"] is None and points[0].payload["pdf_url"] is None
    assert isinstance(qdrant.point_batches[0], list)


@pytest.mark.parametrize("value", [[], "text", 1, None])
def test_empty_or_scalar_batches_rejected(value):
    service = indexer(FakeEmbedding(result()))
    with pytest.raises(InvalidIndexableChunkError):
        service.index(value)


@pytest.mark.parametrize("field,value", [("document_id", "bad"), ("chunk_id", "bad"), ("qdrant_point_id", "bad"), ("text", "  "), ("title", ""), ("region", ""), ("region_level", ""), ("source_url", "")])
def test_invalid_chunk_fields_rejected(field, value):
    with pytest.raises(InvalidIndexableChunkError) as caught:
        chunk(**{field: value})
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_duplicate_ids_are_rejected_before_embedding():
    point, chunk_id = str(uuid4()), str(uuid4())
    service = indexer(FakeEmbedding(result()))
    with pytest.raises(InvalidIndexableChunkError):
        service.index([chunk(point=point), chunk(point=point)])
    with pytest.raises(InvalidIndexableChunkError):
        service.index([chunk(chunk_id=chunk_id), chunk(chunk_id=chunk_id)])


@pytest.mark.parametrize("overrides", [
    {"publication_year": 0}, {"chunk_index": -1}, {"extraction_method": "ocr"},
    {"low_structure_confidence": 1}, {"page_start": 1}, {"page_start": 3, "page_end": 2},
])
def test_citation_contract_validation(overrides):
    with pytest.raises(InvalidIndexableChunkError):
        chunk(**overrides)


def test_optional_citation_fields_and_pages_are_preserved():
    item = chunk(topic="economy", section_heading="Summary", pdf_url="https://bps.example/file.pdf", page_start=2, page_end=4)
    qdrant = FakeQdrant()
    indexer(FakeEmbedding(result()), qdrant).index([item])
    payload = qdrant.calls[0][1][0].payload
    assert payload["topic"] == "economy" and payload["section_heading"] == "Summary"
    assert payload["page_start"] == 2 and payload["page_end"] == 4 and payload["pdf_url"].endswith("file.pdf")


def test_embedding_provider_failure_is_typed_sanitized_and_prevents_upsert():
    secret = "provider-secret"
    qdrant = FakeQdrant()
    with pytest.raises(EmbeddingIndexingFailure) as caught:
        indexer(FakeEmbedding(RuntimeError(secret)), qdrant).index([chunk()])
    assert not qdrant.calls
    rendered = "".join(traceback.format_exception(caught.value))
    assert secret not in str(caught.value)
    assert secret not in repr(caught.value)
    assert secret not in rendered
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_embedding_count_mismatch_prevents_upsert():
    qdrant = FakeQdrant()
    with pytest.raises(EmbeddingValidationError) as caught:
        indexer(FakeEmbedding(EmbeddingBatchResult((), 2)), qdrant).index([chunk()])
    assert not qdrant.calls
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_sparse_encoding_failure_prevents_upsert():
    qdrant = FakeQdrant()

    class FailingSparseEncoder(FakeSparseEncoder):
        def encode_documents(self, texts):
            raise RuntimeError("sparse-provider-secret")

    service = QdrantChunkIndexer(
        FakeEmbedding(result()),
        qdrant,
        QdrantIndexingSettings(qdrant_api_key=SecretStr(""), expected_dense_vector_size=2),
        FailingSparseEncoder(),
    )
    with pytest.raises(SparseIndexingFailure) as caught:
        service.index([chunk()])
    assert not qdrant.calls
    assert "sparse-provider-secret" not in repr(caught.value)


@pytest.mark.parametrize("vectors", [
    (EmbeddingVector(1, (1.0, 2.0)),),
    (EmbeddingVector(0, (1.0,)),),
    (EmbeddingVector(0, (1.0, 2.0)), EmbeddingVector(1, (1.0,))),
])
def test_embedding_order_or_dimension_mismatch_prevents_upsert(vectors):
    qdrant = FakeQdrant()
    with pytest.raises(EmbeddingValidationError):
        indexer(FakeEmbedding(EmbeddingBatchResult(vectors, 2)), qdrant).index([chunk()] if len(vectors) == 1 else [chunk(), chunk()])
    assert not qdrant.calls


@pytest.mark.parametrize("declared_dimension", [None, True, 0, -1, 1, 3, "2"])
def test_invalid_or_mismatched_declared_dimension_prevents_upsert(declared_dimension):
    qdrant = FakeQdrant()
    with pytest.raises(EmbeddingValidationError) as caught:
        indexer(FakeEmbedding(result(declared_dimension=declared_dimension)), qdrant).index([chunk()])
    assert not qdrant.calls
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_declared_dimension_must_match_each_vector_length():
    qdrant = FakeQdrant()
    embedding = EmbeddingBatchResult((EmbeddingVector(0, (1.0, 2.0)),), 3)
    with pytest.raises(EmbeddingValidationError):
        indexer(FakeEmbedding(embedding), qdrant).index([chunk()])
    assert not qdrant.calls


@pytest.mark.parametrize("value", [True, "not-a-number", float("nan"), float("inf"), float("-inf"), 10**4000])
def test_invalid_vector_values_are_typed_and_prevent_upsert(value):
    qdrant = FakeQdrant()
    embedding = EmbeddingBatchResult((EmbeddingVector(0, (value, 1.0)),), 2)
    with pytest.raises(EmbeddingValidationError) as caught:
        indexer(FakeEmbedding(embedding), qdrant).index([chunk()])
    assert not qdrant.calls
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_invalid_uuid_and_environment_dimension_errors_have_no_exception_chain(monkeypatch):
    with pytest.raises(InvalidIndexableChunkError) as uuid_error:
        chunk(document_id="not-a-uuid")
    monkeypatch.setenv("QDRANT_DENSE_VECTOR_SIZE", "not-an-integer")
    with pytest.raises(IndexingConfigurationError) as dimension_error:
        QdrantIndexingSettings.from_environment()
    for error in (uuid_error.value, dimension_error.value):
        rendered = "".join(traceback.format_exception(error))
        assert error.__cause__ is None and error.__context__ is None
        assert "ValueError" not in rendered


@pytest.mark.parametrize("response", [None, models.UpdateResult(status=models.UpdateStatus.ACKNOWLEDGED, operation_id=1), object()])
def test_missing_or_incomplete_qdrant_result_is_typed(response):
    qdrant = FakeQdrant(response=response)
    with pytest.raises(QdrantUpsertIncompleteError):
        indexer(FakeEmbedding(result()), qdrant).index([chunk()])


def test_qdrant_failure_is_sanitized_and_repeated_request_uses_same_ids():
    item = chunk()
    qdrant = FakeQdrant(error=RuntimeError("qdrant secret"))
    with pytest.raises(QdrantIndexingTransportError) as caught:
        indexer(FakeEmbedding(result()), qdrant).index([item])
    assert "qdrant secret" not in repr(caught.value)
    qdrant = FakeQdrant()
    service = indexer(FakeEmbedding(result()), qdrant)
    service.index([item])
    service.index([item])
    assert qdrant.calls[0][1][0].id == qdrant.calls[1][1][0].id == item.qdrant_point_id


def test_legacy_collection_cannot_receive_new_vectors():
    with pytest.raises(IndexingConfigurationError):
        QdrantIndexingSettings(
            qdrant_api_key=SecretStr(""),
            collection_name=LEGACY_COLLECTION_NAME,
            expected_dense_vector_size=2,
        )


def test_environment_composition_uses_cloudflare_and_versioned_1024_contract(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account-id")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cloudflare-token")
    monkeypatch.setenv("CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL", "@cf/qwen/qwen3-embedding-0.6b")
    monkeypatch.setenv("QDRANT_DENSE_VECTOR_SIZE", "1024")
    qdrant = FakeQdrant()
    monkeypatch.setattr("ringkas_worker.indexing.qdrant_client_from_settings", lambda _: qdrant)
    monkeypatch.setattr("ringkas_worker.indexing.FastEmbedSparseEncoder.from_environment", lambda: FakeSparseEncoder())

    service = QdrantChunkIndexer.from_environment()
    assert isinstance(service._embedding_client, CloudflareWorkersAiEmbeddingClient)
    assert service._embedding_client._settings.model == "@cf/qwen/qwen3-embedding-0.6b"
    assert service._settings.expected_dense_vector_size == 1024
    assert service._settings.collection_name == COLLECTION_NAME
    service.close()
    assert service._embedding_client._closed is True


def test_1024_index_vector_is_accepted_before_upsert():
    qdrant = FakeQdrant()
    service = QdrantChunkIndexer(
        FakeEmbedding(result(dimension=1024)),
        qdrant,
        QdrantIndexingSettings(qdrant_api_key=SecretStr(""), expected_dense_vector_size=1024),
        FakeSparseEncoder(),
    )
    service.index([chunk()])
    assert len(qdrant.point_batches[0][0].vector["dense"]) == 1024
