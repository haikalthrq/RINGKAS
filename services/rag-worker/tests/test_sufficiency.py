from dataclasses import replace
import traceback
from uuid import uuid4

import pytest

from ringkas_worker.citations import (
    CitationBuildResult,
    CitationPayload,
    CitationValidationError,
)
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult
from ringkas_worker.sufficiency import (
    CitationRelevanceAssessment,
    EvidenceAssessmentResult,
    EvidenceRelevance,
    QualitativeRetrievalSufficiencyEvaluator,
    RetrievalSufficiencyResult,
    SufficiencyDecision,
    SufficiencyValidationError,
)


def citation(low=False, order=1):
    chunk_id = str(uuid4())
    return CitationPayload(
        chunk_id,
        order,
        chunk_id,
        str(uuid4()),
        "Title",
        2025,
        "Region",
        "province",
        None,
        None,
        None,
        None,
        "https://bps.test",
        None,
        "excerpt",
        low,
    )


def retrieval(citations):
    return FinalRetrievalResult(
        10,
        tuple(
            FinalRetrievalCandidate(
                index,
                0.5,
                item.chunk_id,
                item.document_id,
                str(uuid4()),
                1,
                None,
                0.5,
                None,
                item.title,
                item.publication_year,
                item.region,
                item.region_level,
                item.topic,
                item.page_start,
                item.page_end,
                item.section_heading,
                0,
                "text_layer",
                item.low_structure_confidence,
                item.source_url,
                item.pdf_url,
            )
            for index, item in enumerate(citations, 1)
        ),
    )


class FakeAssessor:
    def __init__(self, relevance):
        self.relevance = relevance

    def assess(self, _query, citations):
        return EvidenceAssessmentResult(
            tuple(
                CitationRelevanceAssessment(
                    citation.chunk_id, citation.order, relevance
                )
                for citation, relevance in zip(citations.citations, self.relevance)
            )
        )


def evaluate(citations, relevance=None):
    assessor = None if relevance is None else FakeAssessor(relevance)
    return QualitativeRetrievalSufficiencyEvaluator(assessor).evaluate(
        "user query", retrieval(citations), CitationBuildResult(tuple(citations))
    )


def test_empty_and_unassessed_evidence_fail_closed():
    empty = evaluate(())
    assert empty.decision is SufficiencyDecision.INSUFFICIENT
    assert empty.requires_refusal and empty.requires_limitation
    item = citation()
    unavailable = evaluate((item,))
    assert unavailable.reason_code == "relevance_assessment_unavailable"
    assert unavailable.excluded_citation_ids == (item.chunk_id,)
    assert unavailable.requires_refusal


@pytest.mark.parametrize(
    ("relevance", "low", "decision"),
    [
        (EvidenceRelevance.RELEVANT, False, SufficiencyDecision.SUFFICIENT),
        (EvidenceRelevance.RELEVANT, True, SufficiencyDecision.PARTIAL),
        (EvidenceRelevance.WEAK, False, SufficiencyDecision.PARTIAL),
        (EvidenceRelevance.IRRELEVANT, False, SufficiencyDecision.INSUFFICIENT),
        (EvidenceRelevance.UNCLEAR, False, SufficiencyDecision.INSUFFICIENT),
    ],
)
def test_qualitative_policy(relevance, low, decision):
    item = citation(low)
    result = evaluate((item,), (relevance,))
    assert result.decision is decision
    assert result.citation_count == 1
    assert set(
        result.usable_citation_ids
        + result.limited_citation_ids
        + result.excluded_citation_ids
    ) == {item.chunk_id}
    if decision is SufficiencyDecision.SUFFICIENT:
        assert (
            result.may_answer_substantively
            and not result.requires_limitation
            and not result.requires_refusal
        )
    elif decision is SufficiencyDecision.PARTIAL:
        assert (
            result.may_answer_substantively
            and result.requires_limitation
            and not result.requires_refusal
        )
    else:
        assert (
            not result.may_answer_substantively
            and result.requires_limitation
            and result.requires_refusal
        )


def test_mixed_assessments_preserve_order_and_eligibility():
    items = tuple(citation(False, index) for index in range(1, 5))
    result = evaluate(
        items,
        (
            EvidenceRelevance.RELEVANT,
            EvidenceRelevance.WEAK,
            EvidenceRelevance.IRRELEVANT,
            EvidenceRelevance.UNCLEAR,
        ),
    )
    assert result.decision is SufficiencyDecision.SUFFICIENT
    assert result.usable_citation_ids == (items[0].chunk_id,)
    assert result.limited_citation_ids == (items[1].chunk_id,)
    assert result.excluded_citation_ids == (items[2].chunk_id, items[3].chunk_id)


def test_assessment_alignment_and_invalid_inputs_fail_safely():
    item = citation()
    evaluator = QualitativeRetrievalSufficiencyEvaluator(
        FakeAssessor((EvidenceRelevance.RELEVANT,))
    )
    with pytest.raises(SufficiencyValidationError):
        evaluator.evaluate(
            "query", FinalRetrievalResult(10, ()), CitationBuildResult((item,))
        )
    with pytest.raises(CitationValidationError):
        evaluator.evaluate(
            "query", retrieval((item,)), CitationBuildResult((replace(item, order=2),))
        )
    with pytest.raises(SufficiencyValidationError):
        EvidenceAssessmentResult(
            (CitationRelevanceAssessment(item.chunk_id, 1, "relevant"),)
        )


def test_score_changes_do_not_change_qualitative_decision():
    item = citation()
    baseline_retrieval = retrieval((item,))
    changed = FinalRetrievalResult(
        10,
        (
            replace(
                baseline_retrieval.candidates[0],
                rrf_score=-999,
                dense_score=999,
                sparse_score=-999,
            ),
        ),
    )
    assessor = FakeAssessor((EvidenceRelevance.RELEVANT,))
    evaluator = QualitativeRetrievalSufficiencyEvaluator(assessor)
    baseline = evaluator.evaluate(
        "query", baseline_retrieval, CitationBuildResult((item,))
    )
    assert (
        evaluator.evaluate("query", changed, CitationBuildResult((item,))).decision
        is baseline.decision
    )
    assert not hasattr(baseline, "rrf_score")


def test_assessor_failure_does_not_expose_query_or_excerpt():
    class BrokenAssessor:
        def assess(self, _query, _citations):
            raise RuntimeError("user query private excerpt")

    item = citation()
    evaluator = QualitativeRetrievalSufficiencyEvaluator(BrokenAssessor())
    query = "user query"
    with pytest.raises(SufficiencyValidationError) as caught:
        evaluator.evaluate(query, retrieval((item,)), CitationBuildResult((item,)))
    assert "user query" not in "".join(traceback.format_exception(caught.value))
    assert "private excerpt" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_unavailable_assessor_counts_only_structural_low_confidence():
    normal, low = citation(False, 1), citation(True, 2)
    result = evaluate((normal, low))
    assert result.low_confidence_citation_count == 1
    assert result.excluded_citation_ids == (normal.chunk_id, low.chunk_id)
    assert result.requires_refusal


def test_malformed_retrieval_candidates_are_typed():
    item = citation()
    evaluator = QualitativeRetrievalSufficiencyEvaluator()
    with pytest.raises(SufficiencyValidationError):
        evaluator.evaluate(
            "query", FinalRetrievalResult(10, None), CitationBuildResult(())
        )
    malformed_id = replace(retrieval((item,)).candidates[0], chunk_id=[])
    with pytest.raises(SufficiencyValidationError):
        evaluator.evaluate(
            "query",
            FinalRetrievalResult(10, (malformed_id,)),
            CitationBuildResult((item,)),
        )
    boolean_rank = replace(retrieval((item,)).candidates[0], rank=True)
    with pytest.raises(SufficiencyValidationError):
        evaluator.evaluate(
            "query",
            FinalRetrievalResult(10, (boolean_rank,)),
            CitationBuildResult((item,)),
        )


def test_sufficiency_result_partition_and_semantics_are_mandatory():
    first, second = str(uuid4()), str(uuid4())
    valid = RetrievalSufficiencyResult(
        SufficiencyDecision.SUFFICIENT,
        "citable_evidence_available",
        2,
        1,
        0,
        1,
        0,
        (first, second),
        (first,),
        (second,),
        (),
        True,
        False,
        False,
    )
    assert valid.citation_ids == (first, second)
    for changes in (
        {"usable_citation_ids": (second, first)},
        {"citation_count": 1},
        {"usable_citation_count": 0},
    ):
        with pytest.raises(SufficiencyValidationError):
            replace(valid, **changes)
    with pytest.raises(SufficiencyValidationError):
        RetrievalSufficiencyResult(
            SufficiencyDecision.SUFFICIENT,
            "citable_evidence_available",
            1,
            0,
            0,
            0,
            1,
            (first,),
            (),
            (),
            (first,),
            True,
            False,
            False,
        )
