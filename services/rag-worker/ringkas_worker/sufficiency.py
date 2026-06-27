from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
        try:
            parsed = UUID(self.citation_id)
        except (AttributeError, TypeError, ValueError):
            _raise_safe(SufficiencyValidationError("assessment citation ID must be a UUID"))
        if str(parsed) != self.citation_id:
            _raise_safe(SufficiencyValidationError("assessment citation ID must be canonical"))
        if isinstance(self.order, bool) or not isinstance(self.order, int) or self.order <= 0:
            _raise_safe(SufficiencyValidationError("assessment order must be positive"))
        if not isinstance(self.relevance, EvidenceRelevance):
            _raise_safe(SufficiencyValidationError("assessment relevance is invalid"))


@dataclass(frozen=True, slots=True)
class EvidenceAssessmentResult:
    assessments: tuple[CitationRelevanceAssessment, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.assessments, tuple) or any(not isinstance(item, CitationRelevanceAssessment) for item in self.assessments):
            _raise_safe(SufficiencyValidationError("assessment result contains invalid records"))
        if tuple(item.order for item in self.assessments) != tuple(range(1, len(self.assessments) + 1)):
            _raise_safe(SufficiencyValidationError("assessment orders must be contiguous and one-based"))
        if len({item.citation_id for item in self.assessments}) != len(self.assessments):
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


class LexicalEvidenceRelevanceAssessor:
    """Conservative lexical checks over excerpts; they do not establish factual accuracy."""

    _TOKEN = re.compile(r"[a-z0-9]+")
    _NUMBER = re.compile(r"(?<![a-z0-9])\d+(?:[.,]\d+)?")
    _STOP_WORDS = frozenset({"a", "adalah", "apa", "apakah", "bagaimana", "bahwa", "dan", "dari", "di", "dengan", "dalam", "ini", "itu", "juga", "ke", "kapan", "karena", "mengapa", "menurut", "oleh", "pada", "publikasi", "sebagai", "sebutkan", "siapa", "tentang", "untuk", "yang", "berdasarkan", "jelaskan", "tolong", "the"})
    _REQUEST_CUES = frozenset({"berapa", "jumlah", "nilai", "tingkat", "persentase", "persen", "rata", "rasio", "definisi", "artinya", "maksud", "bandingkan", "perbandingan", "dibandingkan", "versus", "vs", "tren", "perkembangan", "perubahan", "berubah", "meningkat", "menurun", "penyebab", "dampak", "mempengaruhi", "menyebabkan"})
    _NUMERIC_CUES = frozenset({"berapa", "jumlah", "nilai", "tingkat", "persentase", "persen", "rata", "rasio"})
    _UNIT_TERMS = frozenset({"persen", "persentase", "orang", "jiwa", "rupiah", "ribu", "juta", "miliar", "rumah", "tangga", "kilometer", "hektar", "unit"})
    _DEFINITION_CUES = frozenset({"definisi", "artinya", "maksud"})
    _DEFINITION_EVIDENCE = re.compile(r"\b(adalah|merupakan|didefinisikan|yaitu|berarti)\b")
    _COMPARISON_CUES = frozenset({"bandingkan", "perbandingan", "dibandingkan", "versus", "vs"})
    _TREND_CUES = frozenset({"tren", "perkembangan", "perubahan", "berubah"})
    _CAUSAL_CUES = frozenset({"mengapa", "penyebab", "dampak", "mempengaruhi", "menyebabkan"})
    _CAUSAL_EVIDENCE = re.compile(r"\b(karena|disebabkan|menyebabkan|akibat|berdampak|mempengaruhi)\b")

    @classmethod
    def _terms(cls, text: str) -> frozenset[str]:
        return frozenset(cls._TOKEN.findall(text.casefold()))

    @classmethod
    def _subject_terms(cls, query_terms: frozenset[str]) -> frozenset[str]:
        return query_terms - cls._STOP_WORDS - cls._REQUEST_CUES

    def assess(self, query: str, citations: CitationBuildResult) -> EvidenceAssessmentResult:
        self._validate(query, citations)
        subjects = self._subject_terms(self._terms(query))
        assessments = []
        for citation in citations.citations:
            overlap = subjects & self._terms(citation.excerpt)
            relevance = EvidenceRelevance.IRRELEVANT
            if subjects and overlap == subjects:
                relevance = EvidenceRelevance.RELEVANT
            elif len(subjects) >= 3 and len(overlap) >= 2:
                relevance = EvidenceRelevance.WEAK
            assessments.append(CitationRelevanceAssessment(citation.chunk_id, citation.order, relevance))
        return EvidenceAssessmentResult(tuple(assessments))

    def analyze(self, query: str, citations: CitationBuildResult) -> QueryEvidenceAnalysis:
        assessment = self.assess(query, citations)
        terms, subjects = self._terms(query), self._subject_terms(self._terms(query))
        relevant = tuple(citation for citation, item in zip(citations.citations, assessment.assessments) if item.relevance is not EvidenceRelevance.IRRELEVANT)
        if not relevant or not subjects:
            return QueryEvidenceAnalysis(assessment, SufficiencyDecision.INSUFFICIENT)
        evidence = "\n".join(citation.excerpt.casefold() for citation in relevant)
        evidence_terms = self._terms(evidence)
        if not subjects <= evidence_terms:
            return QueryEvidenceAnalysis(assessment, SufficiencyDecision.PARTIAL)
        definition = bool(terms & self._DEFINITION_CUES) or "apa itu" in query.casefold()
        if not definition and terms & self._NUMERIC_CUES and not self._supports_numeric(terms, evidence):
            return QueryEvidenceAnalysis(assessment, SufficiencyDecision.PARTIAL)
        if terms & self._UNIT_TERMS and not (terms & self._UNIT_TERMS) <= evidence_terms:
            return QueryEvidenceAnalysis(assessment, SufficiencyDecision.PARTIAL)
        if definition and not self._DEFINITION_EVIDENCE.search(evidence):
            return QueryEvidenceAnalysis(assessment, SufficiencyDecision.PARTIAL)
        if terms & self._TREND_CUES and not self._supports_trend(evidence):
            return QueryEvidenceAnalysis(assessment, SufficiencyDecision.PARTIAL)
        if terms & self._CAUSAL_CUES and not self._CAUSAL_EVIDENCE.search(evidence):
            return QueryEvidenceAnalysis(assessment, SufficiencyDecision.PARTIAL)
        return QueryEvidenceAnalysis(assessment, SufficiencyDecision.SUFFICIENT)

    def _supports_numeric(self, terms: frozenset[str], evidence: str) -> bool:
        periods = {term for term in terms if len(term) == 4 and term.isdigit()}
        return bool({value.replace(",", ".") for value in self._NUMBER.findall(evidence)} - periods)

    def _supports_trend(self, evidence: str) -> bool:
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", evidence))
        values = {value.replace(",", ".") for value in self._NUMBER.findall(evidence)} - years
        return len(years) >= 2 and len(values) >= 2

    @staticmethod
    def _validate(query: str, citations: CitationBuildResult) -> None:
        if not isinstance(query, str) or not query.strip() or not isinstance(citations, CitationBuildResult):
            _raise_safe(SufficiencyValidationError("query or citations are invalid"))


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
        counts = (self.citation_count, self.usable_citation_count, self.low_structure_confidence_citation_count, self.limited_citation_count, self.excluded_citation_count)
        lists = (self.citation_ids, self.usable_citation_ids, self.limited_citation_ids, self.excluded_citation_ids)
        if not isinstance(self.decision, SufficiencyDecision) or not isinstance(self.reason_code, str) or not self.reason_code or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts) or any(not isinstance(values, tuple) for values in lists):
            _raise_safe(SufficiencyValidationError("sufficiency result is invalid"))
        if len(self.citation_ids) != self.citation_count or len(self.usable_citation_ids) != self.usable_citation_count or len(self.limited_citation_ids) != self.limited_citation_count or len(self.excluded_citation_ids) != self.excluded_citation_count:
            _raise_safe(SufficiencyValidationError("citation counts do not match identities"))
        partitions = tuple(set(values) for values in lists[1:])
        if any(len(values) != len(set(values)) for values in lists) or any(partitions[left] & partitions[right] for left in range(3) for right in range(left + 1, 3)) or set.union(*partitions) != set(self.citation_ids):
            _raise_safe(SufficiencyValidationError("citation eligibility partition is invalid"))
        positions = {value: index for index, value in enumerate(self.citation_ids)}
        if any(tuple(sorted(values, key=positions.get)) != values for values in lists[1:]):
            _raise_safe(SufficiencyValidationError("citation eligibility order is invalid"))


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
        if not isinstance(query, str) or not query.strip() or not isinstance(final_retrieval, FinalRetrievalResult) or not isinstance(citations, CitationBuildResult):
            _raise_safe(SufficiencyValidationError("retrieval sufficiency input is invalid"))
        ids = tuple(citation.chunk_id for citation in citations.citations)
        candidates = tuple(final_retrieval.candidates)
        if tuple(candidate.chunk_id for candidate in candidates) != ids:
            _raise_safe(SufficiencyValidationError("retrieval and citation identities do not align"))
        low_count = sum(citation.low_structure_confidence for citation in citations.citations)
        if not ids:
            return self._result(SufficiencyDecision.INSUFFICIENT, "no_citable_evidence", ids, (), (), (), low_count)
        try:
            if isinstance(self._assessor, LexicalEvidenceRelevanceAssessor):
                analysis = self._assessor.analyze(query, citations)
                assessment, decision = analysis.assessment, analysis.decision
            else:
                assessment, decision = self._assessor.assess(query, citations), None
            if not isinstance(assessment, EvidenceAssessmentResult) or tuple(item.citation_id for item in assessment.assessments) != ids:
                raise TypeError
        except Exception:
            return self._result(SufficiencyDecision.INSUFFICIENT, "relevance_assessment_unavailable", ids, (), (), ids, low_count)
        relevant = tuple(item.citation_id for item in assessment.assessments if item.relevance is not EvidenceRelevance.IRRELEVANT)
        if decision is None:
            decision = SufficiencyDecision.SUFFICIENT if any(item.relevance is EvidenceRelevance.RELEVANT for item in assessment.assessments) else SufficiencyDecision.PARTIAL if relevant else SufficiencyDecision.INSUFFICIENT
        if decision is SufficiencyDecision.INSUFFICIENT:
            return self._result(decision, "no_relevant_evidence", ids, (), (), ids, low_count)
        usable = tuple(citation.chunk_id for citation in citations.citations if citation.chunk_id in relevant and not citation.low_structure_confidence)
        limited = tuple(citation.chunk_id for citation in citations.citations if citation.chunk_id in relevant and citation.low_structure_confidence)
        excluded = tuple(citation_id for citation_id in ids if citation_id not in relevant)
        if decision is SufficiencyDecision.SUFFICIENT and usable:
            return self._result(decision, "citable_evidence_available", ids, usable, limited, excluded, low_count)
        return self._result(SufficiencyDecision.PARTIAL, "limited_citable_evidence", ids, (), tuple((*usable, *limited)), excluded, low_count)

    @staticmethod
    def _result(decision: SufficiencyDecision, reason: str, ids: tuple[str, ...], usable: tuple[str, ...], limited: tuple[str, ...], excluded: tuple[str, ...], low_count: int) -> RetrievalSufficiencyResult:
        return RetrievalSufficiencyResult(decision, reason, len(ids), len(usable), low_count, len(limited), len(excluded), ids, usable, limited, excluded, decision is not SufficiencyDecision.INSUFFICIENT, decision is not SufficiencyDecision.SUFFICIENT, decision is SufficiencyDecision.INSUFFICIENT)
