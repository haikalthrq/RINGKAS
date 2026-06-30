from __future__ import annotations

import math
import os
from dataclasses import dataclass

from ringkas_worker.fusion import FusedRetrievalCandidate, FusedRetrievalResult, _order_key


class FinalSelectionError(Exception):
    code = "final_selection_error"


class FinalSelectionConfigurationError(FinalSelectionError):
    code = "invalid_final_selection_configuration"


class FinalSelectionValidationError(FinalSelectionError):
    code = "invalid_fused_retrieval_result"


def _raise_safe(error: FinalSelectionError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


def _finite(value: object, message: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise_safe(FinalSelectionValidationError(message))
    converted = None
    conversion_failed = False
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        conversion_failed = True
    if conversion_failed or converted is None or not math.isfinite(converted):
        _raise_safe(FinalSelectionValidationError(message))
    return converted


@dataclass(frozen=True, slots=True)
class FinalSelectionSettings:
    final_top_k: int = 10

    def __post_init__(self) -> None:
        if isinstance(self.final_top_k, bool) or not isinstance(self.final_top_k, int) or self.final_top_k <= 0:
            _raise_safe(FinalSelectionConfigurationError("final top-k must be a positive integer"))
        try:
            finite = math.isfinite(float(self.final_top_k))
        except (OverflowError, TypeError, ValueError):
            finite = False
        if not finite:
            _raise_safe(FinalSelectionConfigurationError("final top-k is outside the supported numeric range"))

    @classmethod
    def from_environment(cls) -> FinalSelectionSettings:
        value = 10
        conversion_failed = False
        try:
            value = int(os.getenv("FINAL_TOP_K", "10"))
        except (TypeError, ValueError, OverflowError):
            conversion_failed = True
        if conversion_failed:
            _raise_safe(FinalSelectionConfigurationError("FINAL_TOP_K must be a positive integer"))
        return cls(value)


@dataclass(frozen=True, slots=True)
class FinalRetrievalCandidate:
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
class FinalRetrievalResult:
    requested_limit: int
    candidates: tuple[FinalRetrievalCandidate, ...]


class FinalTopKSelector:
    def __init__(self, settings: FinalSelectionSettings | None = None) -> None:
        if settings is not None and not isinstance(settings, FinalSelectionSettings):
            _raise_safe(FinalSelectionConfigurationError("final selection settings have invalid type"))
        self._settings = settings or FinalSelectionSettings()

    def select(self, fused: FusedRetrievalResult) -> FinalRetrievalResult:
        if not isinstance(fused, FusedRetrievalResult):
            _raise_safe(FinalSelectionValidationError("fused retrieval result has invalid type"))
        if not isinstance(fused.collection_name, str) or not fused.collection_name.strip():
            _raise_safe(FinalSelectionValidationError("fused collection name must be nonblank"))
        if isinstance(fused.rrf_k, bool) or not isinstance(fused.rrf_k, int) or fused.rrf_k <= 0:
            _raise_safe(FinalSelectionValidationError("fused RRF k must be a positive integer"))
        try:
            rrf_k_finite = math.isfinite(float(fused.rrf_k))
        except (OverflowError, TypeError, ValueError):
            rrf_k_finite = False
        if not rrf_k_finite:
            _raise_safe(FinalSelectionValidationError("fused RRF k is outside the supported numeric range"))
        try:
            candidates = tuple(fused.candidates)
        except (TypeError, ValueError):
            candidates = ()
            conversion_failed = True
        else:
            conversion_failed = False
        if conversion_failed:
            _raise_safe(FinalSelectionValidationError("fused candidates must be a sequence"))
        if any(not isinstance(candidate, FusedRetrievalCandidate) for candidate in candidates):
            _raise_safe(FinalSelectionValidationError("fused candidates have invalid types"))
        for candidate in candidates:
            if not isinstance(candidate.chunk_id, str) or not candidate.chunk_id:
                _raise_safe(FinalSelectionValidationError("fused candidate chunk ID is invalid"))
            if candidate.dense_rank is None and candidate.sparse_rank is None:
                _raise_safe(FinalSelectionValidationError("fused candidate has no source rank"))
            if any(isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0 for rank in (candidate.dense_rank, candidate.sparse_rank) if rank is not None):
                _raise_safe(FinalSelectionValidationError("fused candidate source rank is invalid"))
            _finite(candidate.rrf_score, "fused candidate RRF score is invalid")
            for score in (candidate.dense_score, candidate.sparse_score):
                if score is not None:
                    _finite(score, "fused candidate source score is invalid")
        if tuple(candidate.rank for candidate in candidates) != tuple(range(1, len(candidates) + 1)):
            _raise_safe(FinalSelectionValidationError("fused candidate ranks must be contiguous and one-based"))
        if len({candidate.chunk_id for candidate in candidates}) != len(candidates):
            _raise_safe(FinalSelectionValidationError("fused candidates contain duplicate chunk IDs"))
        if tuple(sorted(candidates, key=_order_key)) != candidates:
            _raise_safe(FinalSelectionValidationError("fused candidates are incorrectly ordered"))
        selected = candidates[: self._settings.final_top_k]
        result = tuple(FinalRetrievalCandidate(index, candidate.rrf_score, candidate.chunk_id, candidate.document_id, candidate.qdrant_point_id, candidate.dense_rank, candidate.sparse_rank, candidate.dense_score, candidate.sparse_score, candidate.title, candidate.publication_year, candidate.region, candidate.region_level, candidate.topic, candidate.page_start, candidate.page_end, candidate.section_heading, candidate.chunk_index, candidate.extraction_method, candidate.low_structure_confidence, candidate.source_url, candidate.pdf_url) for index, candidate in enumerate(selected, 1))
        return FinalRetrievalResult(self._settings.final_top_k, result)
