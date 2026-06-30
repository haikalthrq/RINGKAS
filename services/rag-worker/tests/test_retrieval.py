from __future__ import annotations

import math
import traceback
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr

from ringkas_worker.embedding import EmbeddingBatchResult, EmbeddingVector
from ringkas_worker.retrieval import (
    DenseRetriever,
    DenseRetrievalConfigurationError,
    DenseRetrievalEmbeddingError,
    DenseRetrievalEmbeddingValidationError,
    DenseRetrievalQueryError,
    DenseRetrievalResponseError,
    DenseRetrievalSettings,
    DenseRetrievalTransportError,
    QdrantDenseRetriever,
)


class FakeEmbedding:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def embed(self, texts, *, input_type=None, truncate=None):
        self.calls.append((tuple(texts), input_type, truncate))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeQdrant:
    def __init__(self, points=(), error=None):
        self.points = list(points)
        self.error = error
        self.calls = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(points=self.points)


def settings(**overrides):
    values = {"qdrant_api_key": SecretStr("test-secret"), "expected_dense_vector_size": 2}
    values.update(overrides)
    return DenseRetrievalSettings(**values)


def point(*, score=0.5, point_id=None, chunk_id=None, payload=None):
    values = {
        "document_id": str(uuid4()), "chunk_id": chunk_id or str(uuid4()), "title": "Publication",
        "publication_year": 2026, "region": "DKI Jakarta", "region_level": "province", "topic": None,
        "page_start": None, "page_end": None, "section_heading": None, "chunk_index": 0,
        "extraction_method": "text_layer", "low_structure_confidence": False,
        "source_url": "https://bps.example/source", "pdf_url": None,
    }
    if payload:
        values.update(payload)
    return SimpleNamespace(id=point_id or str(uuid4()), score=score, payload=values)


_MISSING = object()


def retriever(result=_MISSING, points=(), qdrant=None, **setting_overrides):
    if result is _MISSING:
        result = EmbeddingBatchResult((EmbeddingVector(0, (1.0, 2.0)),), 2)
    embedding = FakeEmbedding(result)
    client = qdrant or FakeQdrant(points)
    return QdrantDenseRetriever(embedding, client, settings(**setting_overrides)), embedding, client


def assert_sanitized(error: BaseException, *forbidden: object) -> None:
    rendered = "".join(traceback.format_exception(error))
    assert error.__cause__ is None and error.__context__ is None
    assert all(str(value) not in str(error) for value in forbidden)
    assert all(str(value) not in repr(error) for value in forbidden)
    assert all(str(value) not in rendered for value in forbidden)


def test_protocol_query_contract_and_ordered_immutable_candidates():
    first, second = point(score=-1), point(score=0),
    service, embedding, qdrant = retriever(points=[first, second])
    assert isinstance(service, DenseRetriever)
    result = service.retrieve("  unchanged query  ", input_type="custom", truncate="END")
    assert isinstance(result.candidates, tuple)
    assert [item.rank for item in result.candidates] == [1, 2]
    assert [item.qdrant_point_id for item in result.candidates] == [str(first.id), str(second.id)]
    assert embedding.calls == [(("  unchanged query  ",), "custom", "END")]
    call = qdrant.calls[0]
    assert call["collection_name"] == "ringkas_chunks_v1"
    assert call["using"] == "dense" and call["limit"] == 20
    assert call["with_payload"] is True and call["with_vectors"] is False
    assert call["score_threshold"] is None and "query_filter" not in call


def test_empty_result_and_positive_override():
    service, _, qdrant = retriever(points=[], dense_top_k=3)
    result = service.retrieve("query")
    assert result.candidates == () and result.requested_limit == 3
    assert qdrant.calls[0]["limit"] == 3


@pytest.mark.parametrize("query", ["", "  ", None, 1, True])
def test_invalid_queries_do_not_call_clients(query):
    service, embedding, qdrant = retriever()
    with pytest.raises(DenseRetrievalQueryError):
        service.retrieve(query)
    assert not embedding.calls and not qdrant.calls


def test_embedding_is_called_once_and_failure_prevents_qdrant():
    service, embedding, qdrant = retriever(result=RuntimeError("query secret"))
    with pytest.raises(DenseRetrievalEmbeddingError) as caught:
        service.retrieve("query")
    assert len(embedding.calls) == 1 and not qdrant.calls
    assert "query secret" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("result", [None, EmbeddingBatchResult((), 2), EmbeddingBatchResult((EmbeddingVector(1, (1.0, 2.0)),), 2), EmbeddingBatchResult((EmbeddingVector(0, (1.0,)),), 1)])
def test_malformed_or_mismatched_embeddings_prevent_qdrant(result):
    service, _, qdrant = retriever(result=result)
    with pytest.raises(DenseRetrievalEmbeddingValidationError):
        service.retrieve("query")
    assert not qdrant.calls


@pytest.mark.parametrize("value", [True, "x", math.nan, math.inf, -math.inf, 10**4000])
def test_invalid_embedding_values_prevent_qdrant(value):
    result = EmbeddingBatchResult((EmbeddingVector(0, (value, 1.0)),), 2)
    service, _, qdrant = retriever(result=result)
    with pytest.raises(DenseRetrievalEmbeddingValidationError):
        service.retrieve("query")
    assert not qdrant.calls


def test_extremely_large_embedding_value_has_no_conversion_chain():
    value = 10**4000
    result = EmbeddingBatchResult((EmbeddingVector(0, (value, 1.0)),), 2)
    service, _, _ = retriever(result=result)
    with pytest.raises(DenseRetrievalEmbeddingValidationError) as caught:
        service.retrieve("query")
    assert_sanitized(caught.value, value)


@pytest.mark.parametrize("score", [True, "score", math.nan, math.inf, -math.inf])
def test_invalid_scores_are_rejected(score):
    service, _, _ = retriever(points=[point(score=score)])
    with pytest.raises(DenseRetrievalResponseError):
        service.retrieve("query")


@pytest.mark.parametrize("score", [-1.0, 0.0, 1.0])
def test_finite_negative_zero_and_positive_scores_are_preserved(score):
    service, _, _ = retriever(points=[point(score=score)])
    assert service.retrieve("query").candidates[0].score == score


def test_extremely_large_score_has_no_conversion_chain():
    score = 10**4000
    service, _, _ = retriever(points=[point(score=score)])
    with pytest.raises(DenseRetrievalResponseError) as caught:
        service.retrieve("query")
    assert_sanitized(caught.value, score)


@pytest.mark.parametrize("field,value", [("title", ""), ("region", None), ("region_level", " "), ("source_url", ""), ("publication_year", 0), ("chunk_index", -1), ("extraction_method", "ocr"), ("low_structure_confidence", 1), ("page_start", 1), ("document_id", "bad")])
def test_payload_citation_validation(field, value):
    service, _, _ = retriever(points=[point(payload={field: value})])
    with pytest.raises(DenseRetrievalResponseError):
        service.retrieve("query")


@pytest.mark.parametrize("payload", [None, [], "payload"])
def test_payload_must_be_a_json_object(payload):
    item = point()
    item.payload = payload
    service, _, _ = retriever(points=[item])
    with pytest.raises(DenseRetrievalResponseError):
        service.retrieve("query")


def test_invalid_point_and_chunk_ids_are_rejected():
    service, _, _ = retriever(points=[point(point_id="not-a-uuid")])
    with pytest.raises(DenseRetrievalResponseError) as point_error:
        service.retrieve("query")
    assert_sanitized(point_error.value, "not-a-uuid")

    service, _, _ = retriever(points=[point(payload={"chunk_id": "not-a-uuid"})])
    with pytest.raises(DenseRetrievalResponseError) as chunk_error:
        service.retrieve("query")
    assert_sanitized(chunk_error.value, "not-a-uuid")


def test_duplicate_chunk_ids_are_rejected():
    chunk_id = str(uuid4())
    service, _, _ = retriever(points=[point(chunk_id=chunk_id), point(chunk_id=chunk_id)])
    with pytest.raises(DenseRetrievalResponseError):
        service.retrieve("query")


@pytest.mark.parametrize("page_start,page_end", [(0, 1), (-1, 1), (1, 0), (2, 1)])
def test_zero_negative_partial_and_inverted_page_ranges_are_rejected(page_start, page_end):
    if page_start == 1 and page_end == 0:
        payload = {"page_start": page_start}
    else:
        payload = {"page_start": page_start, "page_end": page_end}
    service, _, _ = retriever(points=[point(payload=payload)])
    with pytest.raises(DenseRetrievalResponseError):
        service.retrieve("query")


@pytest.mark.parametrize("dimension", [None, True, 0, -1, 1, 3, "2"])
def test_invalid_declared_embedding_dimensions_prevent_qdrant(dimension):
    result = EmbeddingBatchResult((EmbeddingVector(0, (1.0, 2.0)),), dimension)
    service, _, qdrant = retriever(result=result)
    with pytest.raises(DenseRetrievalEmbeddingValidationError):
        service.retrieve("query")
    assert not qdrant.calls


def test_duplicate_ids_and_too_many_results_are_rejected():
    duplicate = point()
    service, _, _ = retriever(points=[duplicate, point(point_id=duplicate.id)])
    with pytest.raises(DenseRetrievalResponseError):
        service.retrieve("query")
    service, _, _ = retriever(points=[point() for _ in range(3)], dense_top_k=2)
    with pytest.raises(DenseRetrievalResponseError):
        service.retrieve("query")


def test_qdrant_failure_is_sanitized_and_uncaused():
    service, _, _ = retriever(qdrant=FakeQdrant(error=RuntimeError("api-key and payload secret")))
    query = "private query"
    with pytest.raises(DenseRetrievalTransportError) as caught:
        service.retrieve(query)
    assert_sanitized(caught.value, "api-key", "payload secret", query)


@pytest.mark.parametrize("variable", ["QDRANT_DENSE_VECTOR_SIZE", "DENSE_TOP_K"])
def test_invalid_environment_integer_has_no_exception_chain(monkeypatch, variable):
    monkeypatch.setenv("QDRANT_DENSE_VECTOR_SIZE", "2")
    monkeypatch.setenv("DENSE_TOP_K", "20")
    raw_value = "not-an-integer-secret"
    monkeypatch.setenv(variable, raw_value)
    with pytest.raises(DenseRetrievalConfigurationError) as caught:
        DenseRetrievalSettings.from_environment()
    assert_sanitized(caught.value, raw_value)


def test_malformed_url_and_port_have_no_exception_chain():
    malformed_url = "not a url with secret"
    with pytest.raises(DenseRetrievalConfigurationError) as malformed:
        settings(qdrant_url=malformed_url)
    assert_sanitized(malformed.value, malformed_url)

    malformed_port = "http://qdrant.example:99999"
    with pytest.raises(DenseRetrievalConfigurationError) as port_error:
        settings(qdrant_url=malformed_port)
    assert_sanitized(port_error.value, malformed_port)


def test_api_key_is_absent_from_retrieval_settings_repr():
    secret = "retrieval-api-key-secret"
    configured = settings(qdrant_api_key=SecretStr(secret))
    assert secret not in str(configured)
    assert secret not in repr(configured)


@pytest.mark.parametrize("value", [0, -1, True, "2"])
def test_settings_require_positive_dimensions_and_limits(value):
    with pytest.raises(DenseRetrievalConfigurationError):
        settings(expected_dense_vector_size=value)
    with pytest.raises(DenseRetrievalConfigurationError):
        settings(dense_top_k=value)
