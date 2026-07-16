from __future__ import annotations

import math
import traceback
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr
from qdrant_client import models

from ringkas_worker.qdrant_setup import COLLECTION_NAME, LEGACY_COLLECTION_NAME
from ringkas_worker.sparse_retrieval import (
    QdrantSparseRetriever,
    SparseQuery,
    SparseRetrievalConfigurationError,
    SparseRetrievalQueryError,
    SparseRetrievalResponseError,
    SparseRetrievalSettings,
    SparseRetrievalTransportError,
)


class FakeQdrant:
    def __init__(self, points=(), error=None):
        self.points, self.error, self.calls = points, error, []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(points=self.points)


def payload(**updates):
    value = {"document_id": str(uuid4()), "chunk_id": str(uuid4()), "title": "Title", "publication_year": 2026, "region": "DKI Jakarta", "region_level": "province", "topic": None, "page_start": 1, "page_end": 1, "section_heading": None, "chunk_index": 0, "extraction_method": "text_layer", "low_structure_confidence": False, "source_url": "https://bps.example/a", "pdf_url": None}
    value.update(updates)
    return value


def point(**kwargs):
    value = {"id": str(uuid4()), "score": 0.5, "payload": payload()}
    value.update(kwargs)
    return SimpleNamespace(**value)


def service(points=(), error=None, **overrides):
    qdrant = FakeQdrant(points, error)
    settings = SparseRetrievalSettings(qdrant_api_key=SecretStr("api-secret"), **overrides)
    return QdrantSparseRetriever(qdrant, settings), qdrant


def assert_safe(error: BaseException, *forbidden: object) -> None:
    rendered = "".join(traceback.format_exception(error))
    assert error.__cause__ is None and error.__context__ is None
    assert all(str(value) not in text for text in (str(error), repr(error), rendered) for value in forbidden)


def test_query_sorting_and_exact_contract():
    item = point()
    retriever, qdrant = service([item])
    result = retriever.retrieve(SparseQuery((7, 2), (0.7, 0.2)))
    assert result.candidates[0].rank == 1 and result.candidates[0].score == 0.5
    call = qdrant.calls[0]
    assert isinstance(call["query"], models.SparseVector)
    assert call["query"].indices == [2, 7] and call["query"].values == [0.2, 0.7]
    assert call["using"] == "sparse" and call["limit"] == 20
    assert call["collection_name"] == COLLECTION_NAME
    assert call["with_payload"] is True and call["with_vectors"] is False
    assert call["score_threshold"] is None and "query_filter" not in call


@pytest.mark.parametrize("indices,values", [((), (1.0,)), ((1,), ()), ((1,), (1.0, 2.0)), ("1", (1.0,))])
def test_empty_sides_and_length_mismatch(indices, values):
    with pytest.raises(SparseRetrievalQueryError) as caught:
        SparseQuery(indices, values)
    assert_safe(caught.value)


@pytest.mark.parametrize("indices", [(-1,), (True,), ("1",), (1, 1)])
def test_invalid_indices(indices):
    with pytest.raises(SparseRetrievalQueryError):
        SparseQuery(indices, (1.0,) * len(indices))


@pytest.mark.parametrize("value", [True, "x", math.nan, math.inf, -math.inf, 10**4000])
def test_invalid_values(value):
    with pytest.raises(SparseRetrievalQueryError) as caught:
        SparseQuery((1,), (value,))
    assert_safe(caught.value, value)


def test_results_are_empty_and_ordered():
    retriever, qdrant = service([])
    assert retriever.retrieve(SparseQuery((1,), (1.0,))).candidates == ()
    first, second = point(), point()
    retriever, _ = service([first, second], sparse_top_k=3)
    result = retriever.retrieve(SparseQuery((1,), (1.0,)))
    assert [candidate.rank for candidate in result.candidates] == [1, 2]


@pytest.mark.parametrize("response", [None, SimpleNamespace(), SimpleNamespace(points=None), SimpleNamespace(points="points")])
def test_invalid_response_shape(response):
    retriever, qdrant = service([])
    qdrant.query_points = lambda **_: response
    with pytest.raises(SparseRetrievalResponseError):
        retriever.retrieve(SparseQuery((1,), (1.0,)))


@pytest.mark.parametrize("payload_value", [None, [], "payload"])
def test_malformed_payload(payload_value):
    retriever, _ = service([point(payload=payload_value)])
    with pytest.raises(SparseRetrievalResponseError):
        retriever.retrieve(SparseQuery((1,), (1.0,)))


@pytest.mark.parametrize("field,value", [("id", "not-uuid"), ("document_id", "not-uuid"), ("chunk_id", "not-uuid")])
def test_invalid_uuids(field, value):
    item = point() if field == "id" else point(payload=payload(**{field: value}))
    if field == "id":
        item.id = value
    retriever, _ = service([item])
    with pytest.raises(SparseRetrievalResponseError):
        retriever.retrieve(SparseQuery((1,), (1.0,)))


@pytest.mark.parametrize("score", [True, "score", math.nan, math.inf, -math.inf, 10**4000])
def test_invalid_scores(score):
    retriever, _ = service([point(score=score)])
    with pytest.raises(SparseRetrievalResponseError) as caught:
        retriever.retrieve(SparseQuery((1,), (1.0,)))
    assert_safe(caught.value, score if score != "score" else "provider-score")


@pytest.mark.parametrize("page_start,page_end", [(1, None), (None, 1), (0, 1), (-1, 1), (2, 1)])
def test_invalid_page_ranges(page_start, page_end):
    retriever, _ = service([point(payload=payload(page_start=page_start, page_end=page_end))])
    with pytest.raises(SparseRetrievalResponseError):
        retriever.retrieve(SparseQuery((1,), (1.0,)))


@pytest.mark.parametrize("field,value", [("extraction_method", "ocr"), ("low_structure_confidence", 1)])
def test_invalid_extraction_and_confidence(field, value):
    retriever, _ = service([point(payload=payload(**{field: value}))])
    with pytest.raises(SparseRetrievalResponseError):
        retriever.retrieve(SparseQuery((1,), (1.0,)))


def test_duplicate_ids_and_too_many_results():
    first = point()
    with pytest.raises(SparseRetrievalResponseError):
        service([first, point(id=first.id)])[0].retrieve(SparseQuery((1,), (1.0,)))
    with pytest.raises(SparseRetrievalResponseError):
        service([first, point(payload=payload(chunk_id=first.payload["chunk_id"]))])[0].retrieve(SparseQuery((1,), (1.0,)))
    with pytest.raises(SparseRetrievalResponseError):
        service([point(), point(), point()], sparse_top_k=2)[0].retrieve(SparseQuery((1,), (1.0,)))


def test_transport_and_configuration_errors_are_sanitized(monkeypatch):
    retriever, _ = service(error=RuntimeError("api-key sparse payload"))
    with pytest.raises(SparseRetrievalTransportError) as transport:
        retriever.retrieve(SparseQuery((1,), (1.0,)))
    assert_safe(transport.value, "api-key", "payload")
    monkeypatch.setenv("SPARSE_TOP_K", "not-an-integer-secret")
    with pytest.raises(SparseRetrievalConfigurationError) as configuration:
        SparseRetrievalSettings.from_environment()
    assert_safe(configuration.value, "not-an-integer-secret")


def test_api_key_is_masked_in_repr():
    settings = SparseRetrievalSettings(qdrant_api_key=SecretStr("sparse-api-key-secret"))
    assert "sparse-api-key-secret" not in str(settings)
    assert "sparse-api-key-secret" not in repr(settings)


@pytest.mark.parametrize("value", [0, -1, True, "20"])
def test_sparse_top_k_is_positive_integer(value):
    with pytest.raises(SparseRetrievalConfigurationError):
        SparseRetrievalSettings(sparse_top_k=value)


def test_legacy_collection_is_rejected():
    with pytest.raises(SparseRetrievalConfigurationError):
        SparseRetrievalSettings(collection_name=LEGACY_COLLECTION_NAME)
