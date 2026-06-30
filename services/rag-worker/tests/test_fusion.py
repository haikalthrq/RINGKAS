from __future__ import annotations

import math
import traceback
from dataclasses import replace
from uuid import uuid4

import pytest

from ringkas_worker.fusion import RrfConfigurationError, RrfFusion, RrfSettings, RrfValidationError
from ringkas_worker.retrieval import DenseRetrievalCandidate, DenseRetrievalResult
from ringkas_worker.sparse_retrieval import SparseRetrievalCandidate, SparseRetrievalResult


def candidate(cls, chunk, rank, score, *, point_id=None, document_id=None):
    values = dict(rank=rank, score=score, qdrant_point_id=point_id or str(uuid4()), chunk_id=chunk, document_id=document_id or str(uuid4()), title="Title", publication_year=2026, region="DKI Jakarta", region_level="province", topic=None, page_start=1, page_end=1, section_heading=None, chunk_index=0, extraction_method="text_layer", low_structure_confidence=False, source_url="https://bps.example/a", pdf_url=None)
    return cls(**values)


def results(dense=(), sparse=(), *, collection="ringkas_chunks_v1", dense_limit=20, sparse_limit=20):
    return DenseRetrievalResult(collection, dense_limit, tuple(dense)), SparseRetrievalResult(collection, sparse_limit, tuple(sparse))


def assert_safe(error: BaseException, *forbidden: object) -> None:
    rendered = "".join(traceback.format_exception(error))
    assert error.__cause__ is None and error.__context__ is None
    assert all(str(value) not in text for text in (str(error), repr(error), rendered) for value in forbidden)


def test_rrf_overlap_nonoverlap_source_only_and_exact_formula():
    overlap, dense_only, sparse_only = str(uuid4()), str(uuid4()), str(uuid4())
    dense_overlap = candidate(DenseRetrievalCandidate, overlap, 1, -100)
    sparse_overlap = candidate(SparseRetrievalCandidate, overlap, 1, 100)
    sparse_overlap = replace(sparse_overlap, qdrant_point_id=dense_overlap.qdrant_point_id, document_id=dense_overlap.document_id)
    dense_result, sparse_result = results((dense_overlap, candidate(DenseRetrievalCandidate, dense_only, 2, 100)), (sparse_overlap, candidate(SparseRetrievalCandidate, sparse_only, 2, -100)))
    result = RrfFusion().fuse(dense_result, sparse_result)
    assert result.collection_name == "ringkas_chunks_v1"
    assert result.candidates[0].chunk_id == overlap
    assert result.candidates[0].rrf_score == 2 / 61
    assert {item.chunk_id for item in result.candidates} == {overlap, dense_only, sparse_only}
    assert [item.rank for item in result.candidates] == [1, 2, 3]


def test_raw_scores_do_not_affect_order_or_rrf_score():
    chunk_a, chunk_b = str(uuid4()), str(uuid4())
    first = candidate(DenseRetrievalCandidate, chunk_a, 1, -10**300)
    second = candidate(DenseRetrievalCandidate, chunk_b, 2, 10**300)
    dense, sparse = results((first, second), ())
    fused = RrfFusion().fuse(dense, sparse)
    assert [item.chunk_id for item in fused.candidates] == [chunk_a, chunk_b]
    assert fused.candidates[0].rrf_score == 1 / 61


def test_empty_inputs_are_valid():
    dense, sparse = results()
    assert RrfFusion().fuse(dense, sparse).candidates == ()
    dense, sparse = results((), (candidate(SparseRetrievalCandidate, str(uuid4()), 1, 1.0),))
    assert len(RrfFusion().fuse(dense, sparse).candidates) == 1


@pytest.mark.parametrize("value", [0, -1, True, "60", math.inf, 10**4000])
def test_invalid_rrf_k_and_environment_are_rejected_safely(value, monkeypatch):
    with pytest.raises(RrfConfigurationError) as caught:
        RrfSettings(value)
    assert_safe(caught.value, value)
    monkeypatch.setenv("RRF_K", "not-an-integer-secret")
    with pytest.raises(RrfConfigurationError) as environment:
        RrfSettings.from_environment()
    assert_safe(environment.value, "not-an-integer-secret")


def test_collection_mismatch_and_invalid_result_are_rejected():
    dense, sparse = results()
    with pytest.raises(RrfValidationError):
        RrfFusion().fuse(DenseRetrievalResult("one", 20, ()), SparseRetrievalResult("two", 20, ()))
    with pytest.raises(RrfValidationError):
        RrfFusion().fuse(DenseRetrievalResult(" ", 20, ()), sparse)
    with pytest.raises(RrfValidationError):
        RrfFusion().fuse(DenseRetrievalResult("c", 20, (object(),)), SparseRetrievalResult("c", 20, ()))


@pytest.mark.parametrize("rank", [0, -1, True, 2])
def test_invalid_source_ranks_are_rejected(rank):
    item = candidate(DenseRetrievalCandidate, str(uuid4()), rank, 1.0)
    dense, sparse = results((item,), ())
    with pytest.raises(RrfValidationError):
        RrfFusion().fuse(dense, sparse)


@pytest.mark.parametrize("score", [True, "x", math.nan, math.inf, -math.inf, 10**4000])
def test_invalid_source_scores_are_rejected(score):
    dense, sparse = results((candidate(DenseRetrievalCandidate, str(uuid4()), 1, score),), ())
    with pytest.raises(RrfValidationError) as caught:
        RrfFusion().fuse(dense, sparse)
    assert_safe(caught.value, score)


def test_duplicate_chunk_and_point_ids_and_too_many_candidates_are_rejected():
    chunk = str(uuid4())
    with pytest.raises(RrfValidationError):
        RrfFusion().fuse(*results((candidate(DenseRetrievalCandidate, chunk, 1, 1.0), candidate(DenseRetrievalCandidate, chunk, 2, 1.0)), ()))
    shared_point = str(uuid4())
    with pytest.raises(RrfValidationError):
        RrfFusion().fuse(*results((candidate(DenseRetrievalCandidate, str(uuid4()), 1, 1.0, point_id=shared_point), candidate(DenseRetrievalCandidate, str(uuid4()), 2, 1.0, point_id=shared_point)), ()))
    with pytest.raises(RrfValidationError):
        RrfFusion().fuse(*results((candidate(DenseRetrievalCandidate, str(uuid4()), 1, 1.0),), (), dense_limit=0))


def test_metadata_conflict_ties_and_input_immutability():
    chunk = str(uuid4())
    dense_item = candidate(DenseRetrievalCandidate, chunk, 1, 1.0)
    sparse_item = replace(candidate(SparseRetrievalCandidate, chunk, 1, 1.0), qdrant_point_id=dense_item.qdrant_point_id, document_id=dense_item.document_id, title="Different")
    dense, sparse = results((dense_item,), (sparse_item,))
    with pytest.raises(RrfValidationError):
        RrfFusion().fuse(dense, sparse)
    first, second = str(uuid4()), str(uuid4())
    dense, sparse = results((candidate(DenseRetrievalCandidate, first, 1, 1.0),), (candidate(SparseRetrievalCandidate, second, 1, 1.0),))
    original = (dense.candidates, sparse.candidates)
    fused = RrfFusion().fuse(dense, sparse)
    assert fused.candidates[0].dense_rank == 1
    assert (dense.candidates, sparse.candidates) == original


def test_configurable_k():
    dense, sparse = results((candidate(DenseRetrievalCandidate, str(uuid4()), 1, 1.0),), ())
    result = RrfFusion(RrfSettings(10)).fuse(dense, sparse)
    assert result.rrf_k == 10 and result.candidates[0].rrf_score == 1 / 11
