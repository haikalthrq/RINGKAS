from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ringkas_worker.retrieval import DenseRetrievalCandidate, DenseRetrievalResult
from ringkas_worker.sparse_retrieval import SparseRetrievalCandidate, SparseRetrievalResult


class RrfFusionError(Exception):
    code = "rrf_fusion_error"


class RrfConfigurationError(RrfFusionError):
    code = "invalid_rrf_configuration"


class RrfValidationError(RrfFusionError):
    code = "invalid_rrf_candidates"


def _raise_safe(error: RrfFusionError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


@dataclass(frozen=True, slots=True)
class RrfSettings:
    rrf_k: int = 60

    def __post_init__(self) -> None:
        if isinstance(self.rrf_k, bool) or not isinstance(self.rrf_k, int) or self.rrf_k <= 0:
            _raise_safe(RrfConfigurationError("rrf_k must be a positive integer"))
        converted = None
        conversion_failed = False
        try:
            converted = float(self.rrf_k)
        except (OverflowError, TypeError, ValueError):
            conversion_failed = True
        if conversion_failed or converted is None or not math.isfinite(converted):
            _raise_safe(RrfConfigurationError("rrf_k is outside the supported numeric range"))

    @classmethod
    def from_environment(cls) -> RrfSettings:
        value = 60
        conversion_failed = False
        try:
            value = int(os.getenv("RRF_K", "60"))
        except (TypeError, ValueError, OverflowError):
            conversion_failed = True
        if conversion_failed:
            _raise_safe(RrfConfigurationError("RRF_K must be a positive integer"))
        return cls(value)


@dataclass(frozen=True, slots=True)
class FusedRetrievalCandidate:
    rank: int
    rrf_score: float
    chunk_id: str
    document_id: str
    qdrant_point_id: str
    dense_rank: int | None
    sparse_rank: int | None
    dense_score: float | None
    sparse_score: float | None
    title: str
    publication_year: int
    region: str
    region_level: str
    topic: str | None
    page_start: int | None
    page_end: int | None
    section_heading: str | None
    chunk_index: int
    extraction_method: str
    low_structure_confidence: bool
    source_url: str
    pdf_url: str | None


@dataclass(frozen=True, slots=True)
class FusedRetrievalResult:
    collection_name: str
    rrf_k: int
    candidates: tuple[FusedRetrievalCandidate, ...]


@runtime_checkable
class RetrievalFusion(Protocol):
    def fuse(self, dense: DenseRetrievalResult, sparse: SparseRetrievalResult) -> FusedRetrievalResult: ...


_METADATA_FIELDS = ("document_id", "qdrant_point_id", "title", "publication_year", "region", "region_level", "topic", "page_start", "page_end", "section_heading", "chunk_index", "extraction_method", "low_structure_confidence", "source_url", "pdf_url")


def _finite_score(value: object, message: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise_safe(RrfValidationError(message))
    converted = None
    conversion_failed = False
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        conversion_failed = True
    if conversion_failed or converted is None or not math.isfinite(converted):
        _raise_safe(RrfValidationError(message))
    return converted


def _validate_source(candidates: tuple[object, ...], source: str, expected_type: type, requested_limit: object) -> None:
    if isinstance(requested_limit, bool) or not isinstance(requested_limit, int) or requested_limit <= 0 or len(candidates) > requested_limit:
        _raise_safe(RrfValidationError(f"{source} requested limit is invalid"))
    expected = tuple(range(1, len(candidates) + 1))
    ranks = tuple(getattr(candidate, "rank", None) for candidate in candidates)
    if any(isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0 for rank in ranks):
        _raise_safe(RrfValidationError(f"{source} candidate ranks are invalid"))
    if ranks != expected:
        _raise_safe(RrfValidationError(f"{source} candidate ranks must be contiguous and one-based"))
    if any(not isinstance(candidate, expected_type) for candidate in candidates):
        _raise_safe(RrfValidationError(f"{source} candidate type is invalid"))
    chunk_ids = [getattr(candidate, "chunk_id", None) for candidate in candidates]
    if any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in chunk_ids) or len(set(chunk_ids)) != len(chunk_ids):
        _raise_safe(RrfValidationError(f"{source} candidates contain duplicate or invalid chunk IDs"))
    point_ids = [getattr(candidate, "qdrant_point_id", None) for candidate in candidates]
    if any(not isinstance(point_id, str) or not point_id for point_id in point_ids) or len(set(point_ids)) != len(point_ids):
        _raise_safe(RrfValidationError(f"{source} candidates contain duplicate or invalid point IDs"))
    for candidate in candidates:
        _finite_score(getattr(candidate, "score", None), f"{source} candidate score is invalid")


def _order_key(candidate: FusedRetrievalCandidate) -> tuple[float, int, int, int, str]:
    return (-candidate.rrf_score, min(value for value in (candidate.dense_rank, candidate.sparse_rank) if value is not None), candidate.dense_rank if candidate.dense_rank is not None else 10**9, candidate.sparse_rank if candidate.sparse_rank is not None else 10**9, candidate.chunk_id)


def _rrf_term(rrf_k: int, rank: int) -> float:
    denominator = rrf_k + rank
    converted = None
    conversion_failed = False
    try:
        converted = float(denominator)
    except (OverflowError, TypeError, ValueError):
        conversion_failed = True
    if conversion_failed or converted is None or not math.isfinite(converted) or converted <= 0:
        _raise_safe(RrfValidationError("RRF score denominator is invalid"))
    return 1.0 / converted


class RrfFusion:
    def __init__(self, settings: RrfSettings | None = None) -> None:
        if settings is not None and not isinstance(settings, RrfSettings):
            _raise_safe(RrfConfigurationError("rrf settings have invalid type"))
        self._settings = settings or RrfSettings()

    def fuse(self, dense: DenseRetrievalResult, sparse: SparseRetrievalResult) -> FusedRetrievalResult:
        if not isinstance(dense, DenseRetrievalResult) or not isinstance(sparse, SparseRetrievalResult):
            _raise_safe(RrfValidationError("retrieval results have invalid types"))
        if not isinstance(dense.collection_name, str) or not dense.collection_name.strip() or dense.collection_name != sparse.collection_name or not isinstance(sparse.collection_name, str) or not sparse.collection_name.strip():
            _raise_safe(RrfValidationError("dense and sparse collections must match and be nonblank"))
        try:
            dense_candidates, sparse_candidates = tuple(dense.candidates), tuple(sparse.candidates)
        except (TypeError, ValueError):
            dense_candidates, sparse_candidates = (), ()
            conversion_failed = True
        else:
            conversion_failed = False
        if conversion_failed:
            _raise_safe(RrfValidationError("retrieval candidates must be sequences"))
        _validate_source(dense_candidates, "dense", DenseRetrievalCandidate, dense.requested_limit)
        _validate_source(sparse_candidates, "sparse", SparseRetrievalCandidate, sparse.requested_limit)
        combined: dict[str, dict[str, object]] = {}
        for source, candidates in (("dense", dense_candidates), ("sparse", sparse_candidates)):
            for candidate in candidates:
                chunk_id = candidate.chunk_id
                entry = combined.setdefault(chunk_id, {"candidate": candidate, "dense": None, "sparse": None})
                existing = entry[source]
                if existing is not None:
                    _raise_safe(RrfValidationError("candidate appears more than once in a source"))
                if entry["dense"] is not None or entry["sparse"] is not None:
                    other = entry["candidate"]
                    if any(getattr(other, name) != getattr(candidate, name) for name in _METADATA_FIELDS):
                        _raise_safe(RrfValidationError("overlapping candidates have conflicting metadata"))
                entry[source] = candidate
        fused: list[FusedRetrievalCandidate] = []
        for entry in combined.values():
            base = entry["candidate"]
            dense_candidate = entry["dense"]
            sparse_candidate = entry["sparse"]
            dense_rank = getattr(dense_candidate, "rank", None)
            sparse_rank = getattr(sparse_candidate, "rank", None)
            score = sum(_rrf_term(self._settings.rrf_k, rank) for rank in (dense_rank, sparse_rank) if rank is not None)
            if not math.isfinite(score):
                _raise_safe(RrfValidationError("RRF score is invalid"))
            fused.append(FusedRetrievalCandidate(0, score, base.chunk_id, base.document_id, base.qdrant_point_id, dense_rank, sparse_rank, getattr(dense_candidate, "score", None), getattr(sparse_candidate, "score", None), base.title, base.publication_year, base.region, base.region_level, base.topic, base.page_start, base.page_end, base.section_heading, base.chunk_index, base.extraction_method, base.low_structure_confidence, base.source_url, base.pdf_url))
        ordered = sorted(fused, key=_order_key)
        ranked = tuple(FusedRetrievalCandidate(index, candidate.rrf_score, candidate.chunk_id, candidate.document_id, candidate.qdrant_point_id, candidate.dense_rank, candidate.sparse_rank, candidate.dense_score, candidate.sparse_score, candidate.title, candidate.publication_year, candidate.region, candidate.region_level, candidate.topic, candidate.page_start, candidate.page_end, candidate.section_heading, candidate.chunk_index, candidate.extraction_method, candidate.low_structure_confidence, candidate.source_url, candidate.pdf_url) for index, candidate in enumerate(ordered, 1))
        return FusedRetrievalResult(dense.collection_name, self._settings.rrf_k, ranked)
