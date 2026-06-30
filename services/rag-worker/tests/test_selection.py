from __future__ import annotations

import math
import traceback
from dataclasses import replace
from uuid import uuid4

import pytest

from ringkas_worker.fusion import FusedRetrievalCandidate, FusedRetrievalResult
from ringkas_worker.selection import FinalSelectionConfigurationError, FinalSelectionSettings, FinalSelectionValidationError, FinalTopKSelector


def fused(rank, score=1.0):
    return FusedRetrievalCandidate(rank, score, str(uuid4()), str(uuid4()), str(uuid4()), rank, None, 1.0, None, "Title", 2026, "DKI Jakarta", "province", None, 1, 1, "Heading", rank, "text_layer", False, "https://bps.example/a", "https://bps.example/a.pdf")


def result(count, *, collection="ringkas_chunks_v1", rrf_k=60):
    return FusedRetrievalResult(collection, rrf_k, tuple(fused(index, 1.0 / index) for index in range(1, count + 1)))


def assert_safe(error: BaseException, *forbidden: object) -> None:
    rendered = "".join(traceback.format_exception(error))
    assert error.__cause__ is None and error.__context__ is None
    assert all(str(value) not in text for text in (str(error), repr(error), rendered) for value in forbidden)


@pytest.mark.parametrize("count,expected", [(0, 0), (3, 3), (10, 10), (12, 10)])
def test_final_selection_cardinalities_and_empty(count, expected):
    selected = FinalTopKSelector().select(result(count))
    assert len(selected.candidates) == expected
    assert [item.rank for item in selected.candidates] == list(range(1, expected + 1))
    assert selected.requested_limit == 10


def test_configurable_top_k_and_stable_prefix():
    source = result(5)
    selected = FinalTopKSelector(FinalSelectionSettings(3)).select(source)
    assert [item.chunk_id for item in selected.candidates] == [item.chunk_id for item in source.candidates[:3]]


@pytest.mark.parametrize("value", [0, -1, True, "10", 10**4000])
def test_invalid_settings_and_environment_are_safely_rejected(value, monkeypatch):
    with pytest.raises(FinalSelectionConfigurationError) as caught:
        FinalSelectionSettings(value)
    assert_safe(caught.value, value)
    monkeypatch.setenv("FINAL_TOP_K", "not-an-integer-secret")
    with pytest.raises(FinalSelectionConfigurationError) as environment:
        FinalSelectionSettings.from_environment()
    assert_safe(environment.value, "not-an-integer-secret")


@pytest.mark.parametrize("collection,rrf_k", [("", 60), (" ", 60), ("ringkas", 0), ("ringkas", -1), ("ringkas", True), ("ringkas", "60"), ("ringkas", 10**4000)])
def test_fused_result_settings_are_validated(collection, rrf_k):
    with pytest.raises(FinalSelectionValidationError):
        FinalTopKSelector().select(result(0, collection=collection, rrf_k=rrf_k))


@pytest.mark.parametrize("score", [True, "x", math.nan, math.inf, -math.inf, 10**4000])
def test_invalid_rrf_and_source_scores_are_rejected(score):
    item = replace(fused(1), rrf_score=score)
    with pytest.raises(FinalSelectionValidationError) as caught:
        FinalTopKSelector().select(FusedRetrievalResult("ringkas", 60, (item,)))
    assert_safe(caught.value, score)
    item = replace(fused(1), dense_score=score)
    with pytest.raises(FinalSelectionValidationError):
        FinalTopKSelector().select(FusedRetrievalResult("ringkas", 60, (item,)))


@pytest.mark.parametrize("ranks", [((0, None),), ((True, None),), (("1", None),), ((None, None),)])
def test_invalid_source_ranks_are_rejected(ranks):
    item = replace(fused(1), dense_rank=ranks[0][0], sparse_rank=ranks[0][1])
    with pytest.raises(FinalSelectionValidationError):
        FinalTopKSelector().select(FusedRetrievalResult("ringkas", 60, (item,)))


def test_malformed_fused_ranks_duplicates_and_order_are_rejected():
    with pytest.raises(FinalSelectionValidationError):
        FinalTopKSelector().select(FusedRetrievalResult("ringkas", 60, (fused(2),)))
    first, second = fused(1), fused(2)
    duplicate = replace(second, chunk_id=first.chunk_id)
    with pytest.raises(FinalSelectionValidationError):
        FinalTopKSelector().select(FusedRetrievalResult("ringkas", 60, (first, duplicate)))
    with pytest.raises(FinalSelectionValidationError):
        FinalTopKSelector().select(FusedRetrievalResult("ringkas", 60, (second, first)))


def test_full_metadata_is_preserved_and_no_reranking_or_threshold_is_applied():
    source = result(2)
    selected = FinalTopKSelector().select(source)
    first = selected.candidates[0]
    original = source.candidates[0]
    assert first.chunk_id == original.chunk_id
    assert first.document_id == original.document_id
    assert first.qdrant_point_id == original.qdrant_point_id
    assert first.rrf_score == original.rrf_score
    assert first.dense_rank == original.dense_rank and first.sparse_rank == original.sparse_rank
    assert first.title == original.title and first.page_start == original.page_start and first.page_end == original.page_end
    assert first.source_url == original.source_url and first.pdf_url == original.pdf_url
