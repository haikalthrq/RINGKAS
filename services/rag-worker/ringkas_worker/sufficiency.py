from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Protocol, runtime_checkable
from uuid import UUID

from ringkas_worker.citations import CitationBuildResult
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult


class SufficiencyError(Exception):
    code = "retrieval_sufficiency_error"


class SufficiencyValidationError(SufficiencyError):
    code = "invalid_retrieval_sufficiency_input"


def _raise_safe(error: SufficiencyError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


def _uuid(value: object, message: str) -> None:
    if type(value) is not str:
        _raise_safe(SufficiencyValidationError(message))
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError):
        parsed = None
    if parsed is None or str(parsed) != value:
        _raise_safe(SufficiencyValidationError(message))


class EvidenceRelevance(str, Enum):
    RELEVANT = "relevant"
    WEAK = "weak"
    IRRELEVANT = "irrelevant"
    UNCLEAR = "unclear"


@dataclass(frozen=True, slots=True)
class CitationRelevanceAssessment:
    citation_id: str
    order: int
    relevance: EvidenceRelevance

    def __post_init__(self) -> None:
        _uuid(self.citation_id, "assessment citation ID must be canonical UUID text")
        if type(self.order) is not int or self.order <= 0:
            _raise_safe(SufficiencyValidationError("assessment order must be positive"))
        if not isinstance(self.relevance, EvidenceRelevance):
            _raise_safe(SufficiencyValidationError("assessment relevance is invalid"))


@dataclass(frozen=True, slots=True)
class EvidenceAssessmentResult:
    assessments: tuple[CitationRelevanceAssessment, ...]

    def __post_init__(self) -> None:
        if type(self.assessments) is not tuple or any(
            not isinstance(item, CitationRelevanceAssessment) for item in self.assessments
        ):
            _raise_safe(SufficiencyValidationError("assessment result contains invalid records"))
        if tuple(item.order for item in self.assessments) != tuple(range(1, len(self.assessments) + 1)):
            _raise_safe(SufficiencyValidationError("assessment orders must be contiguous and one-based"))
        ids = tuple(item.citation_id for item in self.assessments)
        if len(set(ids)) != len(ids):
            _raise_safe(SufficiencyValidationError("assessment citation IDs must be unique"))


@runtime_checkable
class EvidenceRelevanceAssessor(Protocol):
    def assess(self, query: str, citations: CitationBuildResult) -> EvidenceAssessmentResult: ...


class SufficiencyDecision(str, Enum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class QueryEvidenceAnalysis:
    assessment: EvidenceAssessmentResult
    decision: SufficiencyDecision
    contributing_citation_ids: tuple[str, ...] = ()


class LexicalEvidenceRelevanceAssessor:
    """Deterministic excerpt relevance only; never proves answer entailment."""

    _TOKEN = re.compile(r"[a-z0-9]+")
    _STOP_WORDS = frozenset(
        {
            "a", "adalah", "apa", "apakah", "bagaimana", "bahwa", "dan", "dari", "di",
            "dengan", "dalam", "ini", "itu", "juga", "ke", "kapan", "karena", "mengapa",
            "menurut", "oleh", "pada", "publikasi", "sebagai", "sebutkan", "siapa", "tahun",
            "tentang", "untuk", "yang", "antara", "berdasarkan", "jelaskan", "tolong", "the",
        }
    )

    @classmethod
    def _terms(cls, text: str) -> frozenset[str]:
        return frozenset(token for token in cls._TOKEN.findall(text.casefold()) if token not in cls._STOP_WORDS)

    def assess(self, query: str, citations: CitationBuildResult) -> EvidenceAssessmentResult:
        if type(query) is not str or not query.strip():
            _raise_safe(SufficiencyValidationError("query must be nonblank"))
        if type(citations) is not CitationBuildResult:
            _raise_safe(SufficiencyValidationError("citations have invalid type"))
        query_terms = self._terms(query)
        records: list[CitationRelevanceAssessment] = []
        for citation in citations.citations:
            evidence_terms = self._terms(citation.excerpt)
            overlap = query_terms & evidence_terms
            if not query_terms or not overlap:
                relevance = EvidenceRelevance.IRRELEVANT
            elif overlap == query_terms or len(overlap) >= 2:
                relevance = EvidenceRelevance.RELEVANT
            else:
                relevance = EvidenceRelevance.WEAK
            records.append(CitationRelevanceAssessment(citation.chunk_id, citation.order, relevance))
        return EvidenceAssessmentResult(tuple(records))


@dataclass(frozen=True, slots=True)
class RetrievalSufficiencyResult:
    decision: SufficiencyDecision
    reason_code: str
    citation_count: int
    usable_citation_count: int
    low_structure_confidence_citation_count: int
    limited_citation_count: int
    excluded_citation_count: int
    citation_ids: tuple[str, ...]
    usable_citation_ids: tuple[str, ...]
    limited_citation_ids: tuple[str, ...]
    excluded_citation_ids: tuple[str, ...]
    may_answer_substantively: bool
    requires_limitation: bool
    requires_refusal: bool

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SufficiencyDecision):
            _raise_safe(SufficiencyValidationError("sufficiency decision is invalid"))
        if type(self.reason_code) is not str or not self.reason_code.strip() or len(self.reason_code) > 80:
            _raise_safe(SufficiencyValidationError("sufficiency reason code is invalid"))
        counts = (
            self.citation_count,
            self.usable_citation_count,
            self.low_structure_confidence_citation_count,
            self.limited_citation_count,
            self.excluded_citation_count,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            _raise_safe(SufficiencyValidationError("sufficiency counts are invalid"))
        if self.low_structure_confidence_citation_count > self.citation_count:
            _raise_safe(SufficiencyValidationError("structural-low count exceeds citations"))
        flags = (self.may_answer_substantively, self.requires_limitation, self.requires_refusal)
        if not all(type(value) is bool for value in flags):
            _raise_safe(SufficiencyValidationError("sufficiency flags must be boolean"))
        partitions = (
            self.citation_ids,
            self.usable_citation_ids,
            self.limited_citation_ids,
            self.excluded_citation_ids,
        )
        if any(type(values) is not tuple for values in partitions):
            _raise_safe(SufficiencyValidationError("citation identity lists must be tuples"))
        for values in partitions:
            for value in values:
                _uuid(value, "citation identity must be canonical UUID text")
            if len(set(values)) != len(values):
                _raise_safe(SufficiencyValidationError("citation identities must be unique"))
        if (
            len(self.citation_ids) != self.citation_count
            or len(self.usable_citation_ids) != self.usable_citation_count
            or len(self.limited_citation_ids) != self.limited_citation_count
            or len(self.excluded_citation_ids) != self.excluded_citation_count
        ):
            _raise_safe(SufficiencyValidationError("citation counts do not match identities"))
        sets = tuple(set(values) for values in partitions[1:])
        if any(sets[left] & sets[right] for left in range(3) for right in range(left + 1, 3)):
            _raise_safe(SufficiencyValidationError("citation partitions overlap"))
        if set.union(*sets) != set(self.citation_ids):
            _raise_safe(SufficiencyValidationError("citation partitions are incomplete"))
        positions = {value: index for index, value in enumerate(self.citation_ids)}
        if any(tuple(sorted(values, key=positions.get)) != values for values in partitions[1:]):
            _raise_safe(SufficiencyValidationError("citation partition order is invalid"))
        if self.citation_count == 0 and self.reason_code != "no_citable_evidence":
            _raise_safe(SufficiencyValidationError("zero citations require no-citable-evidence reason"))
        if self.reason_code == "no_citable_evidence" and self.citation_count != 0:
            _raise_safe(SufficiencyValidationError("no-citable-evidence reason requires zero citations"))
        if self.decision is SufficiencyDecision.SUFFICIENT:
            if not self.usable_citation_ids or flags != (True, False, False) or self.reason_code != "citable_evidence_available":
                _raise_safe(SufficiencyValidationError("invalid sufficient result semantics"))
        elif self.decision is SufficiencyDecision.PARTIAL:
            if self.usable_citation_ids or not self.limited_citation_ids or flags != (True, True, False) or self.reason_code != "limited_citable_evidence":
                _raise_safe(SufficiencyValidationError("invalid partial result semantics"))
        elif self.decision is SufficiencyDecision.INSUFFICIENT:
            if self.usable_citation_ids or self.limited_citation_ids or flags != (False, True, True) or len(self.excluded_citation_ids) != self.citation_count:
                _raise_safe(SufficiencyValidationError("invalid insufficient result semantics"))
            if self.reason_code not in {"no_citable_evidence", "no_relevant_evidence", "relevance_assessment_unavailable"}:
                _raise_safe(SufficiencyValidationError("invalid insufficient reason"))


@runtime_checkable
class RetrievalSufficiencyEvaluator(Protocol):
    def evaluate(self, query: str, final_retrieval: FinalRetrievalResult, citations: CitationBuildResult) -> RetrievalSufficiencyResult: ...


class QualitativeRetrievalSufficiencyEvaluator:
    def __init__(self, assessor: EvidenceRelevanceAssessor | None = None) -> None:
        if assessor is not None and not isinstance(assessor, EvidenceRelevanceAssessor):
            _raise_safe(SufficiencyValidationError("relevance assessor has invalid type"))
        self._assessor = assessor or LexicalEvidenceRelevanceAssessor()

    @classmethod
    def default(cls) -> QualitativeRetrievalSufficiencyEvaluator:
        return cls()

    def evaluate(self, query: str, final_retrieval: FinalRetrievalResult, citations: CitationBuildResult) -> RetrievalSufficiencyResult:
        self._validate_inputs(query, final_retrieval, citations)
        ids = tuple(citation.chunk_id for citation in citations.citations)
        low_count = sum(citation.low_structure_confidence for citation in citations.citations)
        if not ids:
            return self._result(SufficiencyDecision.INSUFFICIENT, "no_citable_evidence", ids, (), (), (), low_count)
        try:
            assessment = self._assessor.assess(query, citations)
            self._validate_assessment(assessment, ids)
        except Exception:
            return self._result(SufficiencyDecision.INSUFFICIENT, "relevance_assessment_unavailable", ids, (), (), ids, low_count)
        by_id = {item.citation_id: item.relevance for item in assessment.assessments}
        limited = tuple(
            citation.chunk_id
            for citation in citations.citations
            if by_id[citation.chunk_id] in {EvidenceRelevance.RELEVANT, EvidenceRelevance.WEAK}
        )
        excluded = tuple(citation_id for citation_id in ids if citation_id not in limited)
        if not limited:
            return self._result(SufficiencyDecision.INSUFFICIENT, "no_relevant_evidence", ids, (), (), excluded, low_count)
        # Semantic sufficiency requires a future separately approved assessor.
        return self._result(SufficiencyDecision.PARTIAL, "limited_citable_evidence", ids, (), limited, excluded, low_count)

    @staticmethod
    def _validate_inputs(query: str, final_retrieval: FinalRetrievalResult, citations: CitationBuildResult) -> None:
        if type(query) is not str or not query.strip() or type(final_retrieval) is not FinalRetrievalResult or type(citations) is not CitationBuildResult:
            _raise_safe(SufficiencyValidationError("retrieval sufficiency input is invalid"))
        if type(final_retrieval.requested_limit) is not int or final_retrieval.requested_limit <= 0:
            _raise_safe(SufficiencyValidationError("final retrieval requested limit is invalid"))
        candidates = final_retrieval.candidates
        if type(candidates) is not tuple or len(candidates) != len(citations.citations) or len(candidates) > final_retrieval.requested_limit:
            _raise_safe(SufficiencyValidationError("final retrieval candidates are invalid"))
        if any(type(item) is not FinalRetrievalCandidate for item in candidates):
            _raise_safe(SufficiencyValidationError("final retrieval candidates are invalid"))
        candidate_ids: list[str] = []
        point_ids: list[str] = []
        for expected_rank, (candidate, citation) in enumerate(zip(candidates, citations.citations), 1):
            if type(candidate.rank) is not int or candidate.rank != expected_rank:
                _raise_safe(SufficiencyValidationError("final retrieval ranks are invalid"))
            for value, message in ((candidate.chunk_id, "final retrieval chunk ID is invalid"), (candidate.document_id, "final retrieval document ID is invalid"), (candidate.qdrant_point_id, "final retrieval point ID is invalid")):
                _uuid(value, message)
            QualitativeRetrievalSufficiencyEvaluator._validate_candidate_metadata(candidate)
            QualitativeRetrievalSufficiencyEvaluator._validate_citation_metadata(citation)
            if type(candidate.extraction_method) is not str:
                _raise_safe(SufficiencyValidationError("final retrieval extraction metadata is invalid"))
            if candidate.extraction_method != "text_layer":
                _raise_safe(SufficiencyValidationError("final retrieval extraction metadata is invalid"))
            if not QualitativeRetrievalSufficiencyEvaluator._finite(candidate.rrf_score):
                _raise_safe(SufficiencyValidationError("final retrieval score is invalid"))
            if candidate.dense_rank is None and candidate.sparse_rank is None:
                _raise_safe(SufficiencyValidationError("final retrieval candidate has no retrieval source"))
            for rank, score in ((candidate.dense_rank, candidate.dense_score), (candidate.sparse_rank, candidate.sparse_score)):
                if (rank is None) != (score is None):
                    _raise_safe(SufficiencyValidationError("final retrieval rank and score must be paired"))
                if rank is not None and (type(rank) is not int or rank <= 0):
                    _raise_safe(SufficiencyValidationError("final retrieval source rank is invalid"))
                if score is not None and not QualitativeRetrievalSufficiencyEvaluator._finite(score):
                    _raise_safe(SufficiencyValidationError("final retrieval score is invalid"))
            candidate_metadata = (candidate.chunk_id, candidate.document_id, candidate.title, candidate.publication_year, candidate.region, candidate.region_level, candidate.topic, candidate.page_start, candidate.page_end, candidate.section_heading, candidate.source_url, candidate.pdf_url, candidate.low_structure_confidence)
            citation_metadata = (citation.chunk_id, citation.document_id, citation.title, citation.publication_year, citation.region, citation.region_level, citation.topic, citation.page_start, citation.page_end, citation.section_heading, citation.source_url, citation.pdf_url, citation.low_structure_confidence)
            if candidate_metadata != citation_metadata:
                _raise_safe(SufficiencyValidationError("retrieval and citation metadata do not align"))
            candidate_ids.append(candidate.chunk_id)
            point_ids.append(candidate.qdrant_point_id)
        if len(set(candidate_ids)) != len(candidate_ids) or len(set(point_ids)) != len(point_ids):
            _raise_safe(SufficiencyValidationError("final retrieval identities must be unique"))
        if tuple(candidate_ids) != tuple(citation.chunk_id for citation in citations.citations):
            _raise_safe(SufficiencyValidationError("retrieval and citation identities do not align"))

    @staticmethod
    def _finite(value: object) -> bool:
        if type(value) not in {int, float}:
            return False
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            return False

    @staticmethod
    def _validate_candidate_metadata(candidate: FinalRetrievalCandidate) -> None:
        if type(candidate.publication_year) is not int or candidate.publication_year <= 0:
            _raise_safe(SufficiencyValidationError("final retrieval publication year is invalid"))
        if type(candidate.chunk_index) is not int or candidate.chunk_index < 0:
            _raise_safe(SufficiencyValidationError("final retrieval chunk index is invalid"))
        for value, name in ((candidate.page_start, "page start"), (candidate.page_end, "page end")):
            if value is not None and (type(value) is not int or value <= 0):
                _raise_safe(SufficiencyValidationError(f"final retrieval {name} is invalid"))
        required_text = ((candidate.title, "title"), (candidate.region, "region"), (candidate.region_level, "region level"), (candidate.source_url, "source URL"))
        for value, name in required_text:
            if type(value) is not str or not value.strip():
                _raise_safe(SufficiencyValidationError(f"final retrieval {name} is invalid"))
        for value, name in ((candidate.topic, "topic"), (candidate.section_heading, "section heading"), (candidate.pdf_url, "PDF URL")):
            if value is not None and type(value) is not str:
                _raise_safe(SufficiencyValidationError(f"final retrieval {name} is invalid"))
        if type(candidate.low_structure_confidence) is not bool:
            _raise_safe(SufficiencyValidationError("final retrieval extraction metadata is invalid"))

    @staticmethod
    def _validate_citation_metadata(citation: object) -> None:
        if type(citation.chunk_id) is not str or type(citation.document_id) is not str:
            _raise_safe(SufficiencyValidationError("citation metadata is invalid"))
        _uuid(citation.chunk_id, "citation chunk ID is invalid")
        _uuid(citation.document_id, "citation document ID is invalid")
        if type(citation.title) is not str or not citation.title.strip() or type(citation.region) is not str or not citation.region.strip() or type(citation.region_level) is not str or not citation.region_level.strip() or type(citation.source_url) is not str or not citation.source_url.strip() or type(citation.excerpt) is not str or not citation.excerpt.strip():
            _raise_safe(SufficiencyValidationError("citation metadata is invalid"))
        if type(citation.publication_year) is not int or citation.publication_year <= 0:
            _raise_safe(SufficiencyValidationError("citation metadata is invalid"))
        for value in (citation.page_start, citation.page_end):
            if value is not None and (type(value) is not int or value <= 0):
                _raise_safe(SufficiencyValidationError("citation metadata is invalid"))
        for value in (citation.topic, citation.section_heading, citation.pdf_url):
            if value is not None and type(value) is not str:
                _raise_safe(SufficiencyValidationError("citation metadata is invalid"))
        if type(citation.low_structure_confidence) is not bool:
            _raise_safe(SufficiencyValidationError("citation metadata is invalid"))

    @staticmethod
    def _validate_assessment(assessment: object, ids: tuple[str, ...]) -> None:
        if not isinstance(assessment, EvidenceAssessmentResult) or tuple(item.citation_id for item in assessment.assessments) != ids:
            _raise_safe(SufficiencyValidationError("relevance assessment is malformed"))

    @staticmethod
    def _result(decision, reason, ids, usable, limited, excluded, low_count):
        return RetrievalSufficiencyResult(decision, reason, len(ids), len(usable), low_count, len(limited), len(excluded), tuple(ids), tuple(usable), tuple(limited), tuple(excluded), decision is not SufficiencyDecision.INSUFFICIENT, decision is not SufficiencyDecision.SUFFICIENT, decision is SufficiencyDecision.INSUFFICIENT)
