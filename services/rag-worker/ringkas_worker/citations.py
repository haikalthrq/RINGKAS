from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from ringkas_worker.db.citations import (
    CitationSourceRecord,
    CitationSourceRepository,
)
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult


class CitationError(Exception):
    code = "citation_error"


class CitationValidationError(CitationError):
    code = "invalid_citation_input"


class CitationSourceMismatchError(CitationError):
    code = "citation_source_mismatch"


class CitationPersistenceError(CitationError):
    code = "citation_persistence_error"


def _raise_safe(error: CitationError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


@dataclass(frozen=True, slots=True)
class CitationPayload:
    citation_id: str
    order: int
    chunk_id: str
    document_id: str
    title: str
    publication_year: int
    region: str
    region_level: str
    topic: str | None
    page_start: int | None
    page_end: int | None
    section_heading: str | None
    source_url: str
    pdf_url: str | None
    excerpt: str
    low_structure_confidence: bool

    def __post_init__(self) -> None:
        _validate_payload(self)


@dataclass(frozen=True, slots=True)
class CitationBuildResult:
    citations: tuple[CitationPayload, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.citations, tuple) or any(
            not isinstance(citation, CitationPayload) for citation in self.citations
        ):
            _raise_safe(
                CitationValidationError("citation result must contain typed payloads")
            )
        orders = tuple(citation.order for citation in self.citations)
        if orders != tuple(range(1, len(self.citations) + 1)):
            _raise_safe(
                CitationValidationError(
                    "citation orders must be contiguous and one-based"
                )
            )
        citation_ids = tuple(citation.citation_id for citation in self.citations)
        chunk_ids = tuple(citation.chunk_id for citation in self.citations)
        if len(set(citation_ids)) != len(citation_ids) or len(set(chunk_ids)) != len(
            chunk_ids
        ):
            _raise_safe(CitationValidationError("citation identities must be unique"))


@runtime_checkable
class CitationBuilder(Protocol):
    def build(self, final_retrieval: FinalRetrievalResult) -> CitationBuildResult: ...


def _canonical(value: object, field_name: str) -> str:
    try:
        parsed = (
            value
            if isinstance(value, UUID)
            else UUID(value)
            if isinstance(value, str)
            else None
        )
    except (AttributeError, TypeError, ValueError):
        parsed = None
    if parsed is None:
        _raise_safe(CitationValidationError(f"{field_name} must be a UUID"))
    return str(parsed)


def _nonblank(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_safe(CitationValidationError(f"{field_name} must be nonblank"))
    return value


def _validate_payload(payload: CitationPayload) -> None:
    citation_id = _canonical(payload.citation_id, "citation ID")
    chunk_id = _canonical(payload.chunk_id, "chunk ID")
    document_id = _canonical(payload.document_id, "document ID")
    if (
        citation_id != payload.citation_id
        or chunk_id != payload.chunk_id
        or document_id != payload.document_id
    ):
        _raise_safe(CitationValidationError("citation identifiers must be canonical"))
    if citation_id != chunk_id:
        _raise_safe(CitationValidationError("citation ID must equal chunk ID"))
    if (
        isinstance(payload.order, bool)
        or not isinstance(payload.order, int)
        or payload.order <= 0
    ):
        _raise_safe(CitationValidationError("citation order must be positive"))
    _nonblank(payload.title, "title")
    if (
        isinstance(payload.publication_year, bool)
        or not isinstance(payload.publication_year, int)
        or payload.publication_year <= 0
    ):
        _raise_safe(CitationValidationError("publication year must be positive"))
    _nonblank(payload.region, "region")
    _nonblank(payload.region_level, "region level")
    _nonblank(payload.source_url, "source URL")
    _nonblank(payload.excerpt, "source excerpt")
    if (payload.page_start is None) != (payload.page_end is None) or (
        payload.page_start is not None
        and (
            isinstance(payload.page_start, bool)
            or not isinstance(payload.page_start, int)
            or isinstance(payload.page_end, bool)
            or not isinstance(payload.page_end, int)
            or payload.page_start <= 0
            or payload.page_end <= 0
            or payload.page_end < payload.page_start
        )
    ):
        _raise_safe(CitationValidationError("page range is invalid"))
    for value, name in (
        (payload.topic, "topic"),
        (payload.section_heading, "section heading"),
        (payload.pdf_url, "PDF URL"),
    ):
        if value is not None and not isinstance(value, str):
            _raise_safe(CitationValidationError(f"{name} must be text or null"))
    if not isinstance(payload.low_structure_confidence, bool):
        _raise_safe(CitationValidationError("confidence flag must be boolean"))


def _validate_candidate(candidate: object) -> FinalRetrievalCandidate:
    if not isinstance(candidate, FinalRetrievalCandidate):
        _raise_safe(
            CitationValidationError("final retrieval candidate has invalid type")
        )
    _canonical(candidate.chunk_id, "chunk ID")
    _canonical(candidate.document_id, "document ID")
    _canonical(candidate.qdrant_point_id, "Qdrant point ID")
    _nonblank(candidate.title, "title")
    if (
        isinstance(candidate.publication_year, bool)
        or not isinstance(candidate.publication_year, int)
        or candidate.publication_year <= 0
    ):
        _raise_safe(CitationValidationError("publication year must be positive"))
    _nonblank(candidate.region, "region")
    _nonblank(candidate.region_level, "region level")
    _nonblank(candidate.source_url, "source URL")
    if (candidate.page_start is None) != (candidate.page_end is None) or (
        candidate.page_start is not None
        and (
            isinstance(candidate.page_start, bool)
            or not isinstance(candidate.page_start, int)
            or isinstance(candidate.page_end, bool)
            or not isinstance(candidate.page_end, int)
            or candidate.page_start <= 0
            or candidate.page_end <= 0
            or candidate.page_end < candidate.page_start
        )
    ):
        _raise_safe(CitationValidationError("page range is invalid"))
    for value, name in (
        (candidate.topic, "topic"),
        (candidate.section_heading, "section heading"),
        (candidate.pdf_url, "PDF URL"),
    ):
        if value is not None and not isinstance(value, str):
            _raise_safe(CitationValidationError(f"{name} must be text or null"))
    if candidate.extraction_method != "text_layer" or not isinstance(
        candidate.low_structure_confidence, bool
    ):
        _raise_safe(CitationValidationError("candidate extraction metadata is invalid"))
    return candidate


def _validate_source(source: object) -> CitationSourceRecord:
    if not isinstance(source, CitationSourceRecord):
        _raise_safe(CitationValidationError("citation source record has invalid type"))
    _canonical(source.chunk_id, "chunk ID")
    _canonical(source.document_id, "document ID")
    _canonical(source.qdrant_point_id, "Qdrant point ID")
    if (
        isinstance(source.chunk_index, bool)
        or not isinstance(source.chunk_index, int)
        or source.chunk_index < 0
    ):
        _raise_safe(CitationValidationError("chunk index must be nonnegative"))
    _nonblank(source.chunk_text, "source excerpt")
    _nonblank(source.document_title, "title")
    if (
        isinstance(source.publication_year, bool)
        or not isinstance(source.publication_year, int)
        or source.publication_year <= 0
    ):
        _raise_safe(CitationValidationError("publication year must be positive"))
    _nonblank(source.region, "region")
    _nonblank(source.region_level, "region level")
    _nonblank(source.chunk_source_url, "source URL")
    if (source.page_start is None) != (source.page_end is None) or (
        source.page_start is not None
        and (
            isinstance(source.page_start, bool)
            or not isinstance(source.page_start, int)
            or isinstance(source.page_end, bool)
            or not isinstance(source.page_end, int)
            or source.page_start <= 0
            or source.page_end <= 0
            or source.page_end < source.page_start
        )
    ):
        _raise_safe(CitationValidationError("page range is invalid"))
    for value, name in (
        (source.topic, "topic"),
        (source.section_heading, "section heading"),
        (source.pdf_url, "PDF URL"),
    ):
        if value is not None and not isinstance(value, str):
            _raise_safe(CitationValidationError(f"{name} must be text or null"))
    if source.extraction_method != "text_layer" or not isinstance(
        source.low_structure_confidence, bool
    ):
        _raise_safe(CitationValidationError("source extraction metadata is invalid"))
    if source.ingestion_status != "indexed":
        _raise_safe(CitationSourceMismatchError("citation source is not indexed"))
    return source


def _same(candidate: FinalRetrievalCandidate, source: CitationSourceRecord) -> bool:
    return (
        _canonical(candidate.chunk_id, "chunk ID") == source.chunk_id
        and _canonical(candidate.document_id, "document ID") == source.document_id
        and _canonical(candidate.qdrant_point_id, "Qdrant point ID")
        == source.qdrant_point_id
        and (
            candidate.title,
            candidate.publication_year,
            candidate.region,
            candidate.region_level,
            candidate.topic,
            candidate.page_start,
            candidate.page_end,
            candidate.section_heading,
            candidate.chunk_index,
            candidate.extraction_method,
            candidate.low_structure_confidence,
            candidate.source_url,
            candidate.pdf_url,
        )
        == (
            source.document_title,
            source.publication_year,
            source.region,
            source.region_level,
            source.topic,
            source.page_start,
            source.page_end,
            source.section_heading,
            source.chunk_index,
            source.extraction_method,
            source.low_structure_confidence,
            source.chunk_source_url,
            source.pdf_url,
        )
    )


class GroundedCitationBuilder:
    def __init__(self, repository: CitationSourceRepository) -> None:
        if not isinstance(repository, CitationSourceRepository):
            _raise_safe(CitationValidationError("citation repository has invalid type"))
        self._repository = repository

    def build(self, final_retrieval: FinalRetrievalResult) -> CitationBuildResult:
        if not isinstance(final_retrieval, FinalRetrievalResult):
            _raise_safe(
                CitationValidationError("final retrieval result has invalid type")
            )
        try:
            candidates = tuple(final_retrieval.candidates)
        except (AttributeError, TypeError, ValueError):
            _raise_safe(
                CitationValidationError("final retrieval candidates must be iterable")
            )
        if any(
            not isinstance(candidate, FinalRetrievalCandidate)
            for candidate in candidates
        ):
            _raise_safe(
                CitationValidationError("final retrieval candidate has invalid type")
            )
        for expected_rank, candidate in enumerate(candidates, 1):
            if (
                isinstance(candidate.rank, bool)
                or not isinstance(candidate.rank, int)
                or candidate.rank != expected_rank
            ):
                _raise_safe(
                    CitationValidationError(
                        "final retrieval ranks must be contiguous and one-based"
                    )
                )
        for candidate in candidates:
            _validate_candidate(candidate)
        candidate_ids = tuple(
            _canonical(candidate.chunk_id, "chunk ID") for candidate in candidates
        )
        if len(set(candidate_ids)) != len(candidate_ids):
            _raise_safe(
                CitationValidationError("final retrieval contains duplicate chunk IDs")
            )
        try:
            raw_sources = self._repository.get_by_chunk_ids(
                tuple(candidate.chunk_id for candidate in candidates)
            )
            sources = tuple(raw_sources)
        except Exception:
            persistence_error = CitationPersistenceError(
                "citation source persistence operation failed"
            )
        else:
            persistence_error = None
        if persistence_error is not None:
            _raise_safe(persistence_error)
        for source in sources:
            _validate_source(source)
        by_id = {_canonical(source.chunk_id, "chunk ID"): source for source in sources}
        if (
            len(set(candidate_ids)) != len(candidate_ids)
            or len(by_id) != len(sources)
            or set(by_id) != set(candidate_ids)
        ):
            _raise_safe(
                CitationSourceMismatchError(
                    "citation sources do not match final retrieval"
                )
            )
        payloads: list[CitationPayload] = []
        for order, candidate in enumerate(candidates, 1):
            source = by_id.get(_canonical(candidate.chunk_id, "chunk ID"))
            if source is None or not _same(candidate, source):
                _raise_safe(
                    CitationSourceMismatchError(
                        "citation source metadata is stale or invalid"
                    )
                )
            excerpt = _nonblank(source.chunk_text, "source excerpt")
            payloads.append(
                CitationPayload(
                    source.chunk_id,
                    order,
                    source.chunk_id,
                    source.document_id,
                    source.document_title,
                    source.publication_year,
                    source.region,
                    source.region_level,
                    source.topic,
                    source.page_start,
                    source.page_end,
                    source.section_heading,
                    source.chunk_source_url,
                    source.pdf_url,
                    excerpt,
                    source.low_structure_confidence,
                )
            )
        return CitationBuildResult(tuple(payloads))
