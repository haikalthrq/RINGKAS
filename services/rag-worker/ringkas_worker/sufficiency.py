from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
            _raise_safe(
                SufficiencyValidationError("assessment citation ID must be a UUID")
            )
        if str(parsed) != self.citation_id:
            _raise_safe(
                SufficiencyValidationError("assessment citation ID must be canonical")
            )
        if (
            isinstance(self.order, bool)
            or not isinstance(self.order, int)
            or self.order <= 0
        ):
            _raise_safe(SufficiencyValidationError("assessment order must be positive"))
        if not isinstance(self.relevance, EvidenceRelevance):
            _raise_safe(SufficiencyValidationError("assessment relevance is invalid"))


@dataclass(frozen=True, slots=True)
class EvidenceAssessmentResult:
    assessments: tuple[CitationRelevanceAssessment, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.assessments, tuple) or any(
            not isinstance(assessment, CitationRelevanceAssessment)
            for assessment in self.assessments
        ):
            _raise_safe(
                SufficiencyValidationError("assessment result contains invalid records")
            )
        orders = tuple(assessment.order for assessment in self.assessments)
        if orders != tuple(range(1, len(self.assessments) + 1)):
            _raise_safe(
                SufficiencyValidationError(
                    "assessment orders must be contiguous and one-based"
                )
            )
        ids = tuple(assessment.citation_id for assessment in self.assessments)
        if len(set(ids)) != len(ids):
            _raise_safe(
                SufficiencyValidationError("assessment citation IDs must be unique")
            )


@runtime_checkable
class EvidenceRelevanceAssessor(Protocol):
    def assess(
        self, query: str, citations: CitationBuildResult
    ) -> EvidenceAssessmentResult: ...


class SufficiencyDecision(str, Enum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class RetrievalSufficiencyResult:
    decision: SufficiencyDecision
    reason_code: str
    citation_count: int
    usable_citation_count: int
    low_confidence_citation_count: int
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
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            _raise_safe(
                SufficiencyValidationError("sufficiency reason code must be nonblank")
            )
        for value in (
            self.citation_count,
            self.usable_citation_count,
            self.low_confidence_citation_count,
            self.limited_citation_count,
            self.excluded_citation_count,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _raise_safe(
                    SufficiencyValidationError(
                        "sufficiency counts must be nonnegative integers"
                    )
                )
        if self.low_confidence_citation_count > self.citation_count:
            _raise_safe(
                SufficiencyValidationError(
                    "low-confidence count exceeds citation count"
                )
            )
        identity_lists = (
            self.citation_ids,
            self.usable_citation_ids,
            self.limited_citation_ids,
            self.excluded_citation_ids,
        )
        if any(not isinstance(values, tuple) for values in identity_lists):
            _raise_safe(
                SufficiencyValidationError("citation identity lists must be tuples")
            )
        for values in identity_lists:
            for value in values:
                try:
                    parsed = UUID(value)
                except (AttributeError, TypeError, ValueError):
                    _raise_safe(
                        SufficiencyValidationError("citation identity must be a UUID")
                    )
                if str(parsed) != value:
                    _raise_safe(
                        SufficiencyValidationError(
                            "citation identity must be canonical"
                        )
                    )
            if len(set(values)) != len(values):
                _raise_safe(
                    SufficiencyValidationError("citation identity lists must be unique")
                )
        if len(self.citation_ids) != self.citation_count:
            _raise_safe(
                SufficiencyValidationError("citation count does not match identities")
            )
        if (
            len(self.usable_citation_ids) != self.usable_citation_count
            or len(self.limited_citation_ids) != self.limited_citation_count
            or len(self.excluded_citation_ids) != self.excluded_citation_count
        ):
            _raise_safe(
                SufficiencyValidationError("eligibility counts do not match identities")
            )
        if (
            set(self.usable_citation_ids) & set(self.limited_citation_ids)
            or set(self.usable_citation_ids) & set(self.excluded_citation_ids)
            or set(self.limited_citation_ids) & set(self.excluded_citation_ids)
        ):
            _raise_safe(
                SufficiencyValidationError("citation eligibility partitions overlap")
            )
        if set(self.usable_citation_ids) | set(self.limited_citation_ids) | set(
            self.excluded_citation_ids
        ) != set(self.citation_ids):
            _raise_safe(
                SufficiencyValidationError(
                    "citation eligibility partition is incomplete"
                )
            )
        positions = {value: index for index, value in enumerate(self.citation_ids)}
        if any(
            tuple(sorted(values, key=positions.get)) != values
            for values in identity_lists[1:]
        ):
            _raise_safe(
                SufficiencyValidationError("citation eligibility order is invalid")
            )
        if not all(
            isinstance(value, bool)
            for value in (
                self.may_answer_substantively,
                self.requires_limitation,
                self.requires_refusal,
            )
        ):
            _raise_safe(SufficiencyValidationError("sufficiency flags must be boolean"))
        if self.decision is SufficiencyDecision.SUFFICIENT:
            if (
                not self.usable_citation_ids
                or self.reason_code != "citable_evidence_available"
                or not self.may_answer_substantively
                or self.requires_limitation
                or self.requires_refusal
            ):
                _raise_safe(
                    SufficiencyValidationError("invalid sufficient result semantics")
                )
        elif self.decision is SufficiencyDecision.PARTIAL:
            if (
                self.usable_citation_ids
                or not self.limited_citation_ids
                or self.reason_code != "limited_citable_evidence"
                or not self.may_answer_substantively
                or not self.requires_limitation
                or self.requires_refusal
            ):
                _raise_safe(
                    SufficiencyValidationError("invalid partial result semantics")
                )
        elif (
            self.reason_code
            not in {
                "no_citable_evidence",
                "relevance_assessment_unavailable",
                "no_relevant_evidence",
            }
            or self.usable_citation_ids
            or self.limited_citation_ids
            or len(self.excluded_citation_ids) != self.citation_count
            or self.may_answer_substantively
            or not self.requires_limitation
            or not self.requires_refusal
        ):
            _raise_safe(
                SufficiencyValidationError("invalid insufficient result semantics")
            )


@runtime_checkable
class RetrievalSufficiencyEvaluator(Protocol):
    def evaluate(
        self,
        query: str,
        final_retrieval: FinalRetrievalResult,
        citations: CitationBuildResult,
    ) -> RetrievalSufficiencyResult: ...


class QualitativeRetrievalSufficiencyEvaluator:
    def __init__(self, assessor: EvidenceRelevanceAssessor | None = None) -> None:
        if assessor is not None and not isinstance(assessor, EvidenceRelevanceAssessor):
            _raise_safe(
                SufficiencyValidationError("relevance assessor has invalid type")
            )
        self._assessor = assessor

    def evaluate(
        self,
        query: str,
        final_retrieval: FinalRetrievalResult,
        citations: CitationBuildResult,
    ) -> RetrievalSufficiencyResult:
        self._validate_retrieval_and_citations(query, final_retrieval, citations)
        citation_ids = tuple(citation.chunk_id for citation in citations.citations)
        if not citation_ids:
            return self._result(
                SufficiencyDecision.INSUFFICIENT,
                "no_citable_evidence",
                citation_ids,
                (),
                (),
                (),
                False,
                True,
                True,
                0,
            )
        if self._assessor is None:
            return self._result(
                SufficiencyDecision.INSUFFICIENT,
                "relevance_assessment_unavailable",
                citation_ids,
                (),
                (),
                citation_ids,
                False,
                True,
                True,
                sum(
                    citation.low_structure_confidence
                    for citation in citations.citations
                ),
            )
        try:
            assessment = self._assessor.assess(query, citations)
        except Exception:
            error = SufficiencyValidationError("relevance assessment failed")
        else:
            error = None
        if error is not None:
            _raise_safe(error)
        self._validate_assessment(assessment, citation_ids)
        by_id = {item.citation_id: item for item in assessment.assessments}
        usable: list[str] = []
        limited: list[str] = []
        excluded: list[str] = []
        for citation in citations.citations:
            item = by_id[citation.chunk_id]
            if (
                item.relevance is EvidenceRelevance.RELEVANT
                and not citation.low_structure_confidence
            ):
                usable.append(citation.chunk_id)
            elif item.relevance in {EvidenceRelevance.RELEVANT, EvidenceRelevance.WEAK}:
                limited.append(citation.chunk_id)
            else:
                excluded.append(citation.chunk_id)
        if usable:
            return self._result(
                SufficiencyDecision.SUFFICIENT,
                "citable_evidence_available",
                citation_ids,
                tuple(usable),
                tuple(limited),
                tuple(excluded),
                True,
                False,
                False,
                sum(c.low_structure_confidence for c in citations.citations),
            )
        if limited:
            return self._result(
                SufficiencyDecision.PARTIAL,
                "limited_citable_evidence",
                citation_ids,
                (),
                tuple(limited),
                tuple(excluded),
                True,
                True,
                False,
                sum(c.low_structure_confidence for c in citations.citations),
            )
        return self._result(
            SufficiencyDecision.INSUFFICIENT,
            "no_relevant_evidence",
            citation_ids,
            (),
            (),
            tuple(excluded),
            False,
            True,
            True,
            sum(c.low_structure_confidence for c in citations.citations),
        )

    def _validate_retrieval_and_citations(
        self,
        query: str,
        final_retrieval: FinalRetrievalResult,
        citations: CitationBuildResult,
    ) -> None:
        if not isinstance(query, str) or not query.strip():
            _raise_safe(SufficiencyValidationError("query must be nonblank"))
        if not isinstance(final_retrieval, FinalRetrievalResult) or not isinstance(
            citations, CitationBuildResult
        ):
            _raise_safe(
                SufficiencyValidationError(
                    "retrieval and citation results must have valid types"
                )
            )
        try:
            candidates = tuple(final_retrieval.candidates)
        except (AttributeError, TypeError, ValueError):
            _raise_safe(
                SufficiencyValidationError(
                    "final retrieval candidates must be iterable"
                )
            )
        if any(
            not isinstance(candidate, FinalRetrievalCandidate)
            for candidate in candidates
        ):
            _raise_safe(
                SufficiencyValidationError("final retrieval candidate has invalid type")
            )
        for expected_rank, candidate in enumerate(candidates, 1):
            if (
                isinstance(candidate.rank, bool)
                or not isinstance(candidate.rank, int)
                or candidate.rank != expected_rank
            ):
                _raise_safe(
                    SufficiencyValidationError(
                        "final retrieval ranks must be contiguous and one-based"
                    )
                )
        candidate_ids: list[str] = []
        for candidate in candidates:
            try:
                parsed = UUID(candidate.chunk_id)
            except (AttributeError, TypeError, ValueError):
                _raise_safe(
                    SufficiencyValidationError(
                        "final retrieval chunk ID must be a UUID"
                    )
                )
            if str(parsed) != candidate.chunk_id:
                _raise_safe(
                    SufficiencyValidationError(
                        "final retrieval chunk ID must be canonical"
                    )
                )
            candidate_ids.append(candidate.chunk_id)
        candidate_ids = tuple(candidate_ids)
        citation_ids = tuple(citation.chunk_id for citation in citations.citations)
        if len(set(candidate_ids)) != len(candidate_ids):
            _raise_safe(
                SufficiencyValidationError(
                    "final retrieval contains duplicate chunk IDs"
                )
            )
        if candidate_ids != citation_ids:
            _raise_safe(
                SufficiencyValidationError(
                    "retrieval and citation identities do not align"
                )
            )

    def _validate_assessment(
        self, assessment: object, citation_ids: tuple[str, ...]
    ) -> None:
        if not isinstance(assessment, EvidenceAssessmentResult):
            _raise_safe(
                SufficiencyValidationError("relevance assessment has invalid type")
            )
        assessment_ids = tuple(item.citation_id for item in assessment.assessments)
        if assessment_ids != citation_ids:
            _raise_safe(
                SufficiencyValidationError(
                    "relevance assessment identities do not align"
                )
            )

    @staticmethod
    def _result(
        decision,
        reason,
        all_ids,
        usable,
        limited,
        excluded,
        may_answer,
        limitation,
        refusal,
        low_count,
    ):
        return RetrievalSufficiencyResult(
            decision,
            reason,
            len(all_ids),
            len(usable),
            low_count,
            len(limited),
            len(excluded),
            tuple(all_ids),
            tuple(usable),
            tuple(limited),
            tuple(excluded),
            may_answer,
            limitation,
            refusal,
        )
