from dataclasses import replace
from uuid import uuid4

import pytest

from ringkas_worker.citations import CitationBuildResult, CitationPayload
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult
from ringkas_worker.sufficiency import (
    CitationRelevanceAssessment,
    EvidenceAssessmentResult,
    EvidenceRelevance,
    LexicalEvidenceRelevanceAssessor,
    QualitativeRetrievalSufficiencyEvaluator,
    RetrievalSufficiencyResult,
    SufficiencyDecision,
    SufficiencyValidationError,
)


def citation(excerpt, order=1, *, low=False, title="Title", year=2025, region="Region"):
    chunk = str(uuid4())
    return CitationPayload(chunk, order, chunk, str(uuid4()), title, year, region, "province", None, None, None, None, "https://bps.test", None, excerpt, low)


def retrieval(citations, *, rrf=0.5, dense_rank=1, dense_score=0.5):
    return FinalRetrievalResult(10, tuple(
        FinalRetrievalCandidate(index, rrf, item.chunk_id, item.document_id, str(uuid4()), dense_rank, None, dense_score, None, item.title, item.publication_year, item.region, item.region_level, item.topic, item.page_start, item.page_end, item.section_heading, 0, "text_layer", item.low_structure_confidence, item.source_url, item.pdf_url)
        for index, item in enumerate(citations, 1)
    ))


def evaluate(query, *items, assessor=None, retrieval_result=None):
    built = CitationBuildResult(tuple(items))
    return QualitativeRetrievalSufficiencyEvaluator(assessor).evaluate(query, retrieval_result or retrieval(items), built)


def assert_partial(value, limited=(), excluded=()):
    assert value.decision is SufficiencyDecision.PARTIAL
    assert value.reason_code == "limited_citable_evidence"
    assert value.usable_citation_ids == ()
    assert value.limited_citation_ids == limited
    assert value.excluded_citation_ids == excluded
    assert value.may_answer_substantively is True
    assert value.requires_limitation is True
    assert value.requires_refusal is False


def assert_insufficient(value, reason, ids):
    assert value.decision is SufficiencyDecision.INSUFFICIENT
    assert value.reason_code == reason
    assert value.usable_citation_ids == ()
    assert value.limited_citation_ids == ()
    assert value.excluded_citation_ids == ids
    assert value.may_answer_substantively is False
    assert value.requires_limitation is True
    assert value.requires_refusal is True


def test_strong_excerpt_overlap_is_partial_not_sufficient():
    item = citation("Jumlah penduduk Jakarta tahun 2024 adalah 11 juta jiwa.")
    assert_partial(evaluate("Berapa jumlah penduduk Jakarta tahun 2024?", item), (item.chunk_id,))


def test_weak_meaningful_overlap_is_partial():
    item = citation("Penduduk Jakarta dibahas dalam laporan.")
    assert_partial(evaluate("Berapa jumlah penduduk Jakarta tahun 2024?", item), (item.chunk_id,))


def test_irrelevant_excerpt_is_insufficient():
    item = citation("Curah hujan wilayah lain tercatat.")
    assert_insufficient(evaluate("Berapa jumlah penduduk Jakarta?", item), "no_relevant_evidence", (item.chunk_id,))


def test_empty_citations_use_empty_reason():
    assert_insufficient(evaluate("query"), "no_citable_evidence", ())


def test_metadata_only_match_is_insufficient():
    item = citation("Curah hujan tercatat.", title="Jumlah Penduduk Jakarta 2024", year=2024, region="Jakarta")
    assert_insufficient(evaluate("Berapa jumlah penduduk Jakarta 2024?", item), "no_relevant_evidence", (item.chunk_id,))


def test_numeric_definition_comparison_trend_causal_and_impact_are_partial():
    cases = (
        ("Berapa jumlah penduduk Jakarta?", "Jumlah penduduk Jakarta adalah 11 juta jiwa."),
        ("Apa definisi kemiskinan?", "Kemiskinan adalah kondisi ketidakmampuan memenuhi kebutuhan dasar."),
        ("Bandingkan Jakarta dan Bekasi.", "Jakarta 11 juta dan Bekasi 2 juta."),
        ("Bagaimana tren kemiskinan?", "Kemiskinan 2023 5 persen dan 2024 4 persen."),
        ("Mengapa kemiskinan meningkat?", "Kemiskinan meningkat karena harga pangan."),
        ("Apa dampak banjir terhadap kemiskinan?", "Banjir berdampak terhadap kemiskinan."),
    )
    for query, excerpt in cases:
        item = citation(excerpt)
        assert_partial(evaluate(query, item), (item.chunk_id,))


def test_historical_false_sufficient_examples_remain_partial():
    excerpts = (
        "Jumlah penduduk tercantum pada halaman ke-12.",
        "Jumlah penduduk tercantum pada Tabel No. 3.",
        "Kemiskinan dibahas, metode survei adalah pencacahan.",
        "Kemiskinan Jakarta meningkat, sedangkan banjir terjadi karena hujan.",
        "Jakarta dan Bekasi dibahas, metode memakai 12 sampel.",
        "Metode survei 2023 memakai 5 tahap, kemiskinan Jakarta 2024 sebesar 4 persen.",
    )
    for excerpt in excerpts:
        item = citation(excerpt)
        assert evaluate("Berapa jumlah penduduk Jakarta?", item).decision is not SufficiencyDecision.SUFFICIENT


def test_only_limited_and_excluded_partitions_are_emitted():
    relevant = citation("Penduduk Jakarta tercatat.", 1)
    weak = citation("Penduduk dibahas.", 2)
    unclear = citation("", 3) if False else citation("Dokumen lain.", 3)
    value = evaluate("Penduduk Jakarta", relevant, weak, unclear)
    assert value.usable_citation_ids == ()
    assert value.limited_citation_ids == (relevant.chunk_id, weak.chunk_id)
    assert value.excluded_citation_ids == (unclear.chunk_id,)


def test_low_structure_is_limited_and_counted():
    item = citation("Jumlah penduduk Jakarta tercatat.", low=True)
    value = evaluate("Penduduk Jakarta", item)
    assert_partial(value, (item.chunk_id,))
    assert value.low_structure_confidence_citation_count == 1


def test_score_changes_do_not_change_complete_result():
    item = citation("Penduduk Jakarta tercatat.")
    baseline = evaluate("Penduduk Jakarta", item)
    changed = evaluate("Penduduk Jakarta", item, retrieval_result=retrieval((item,), rrf=-999, dense_score=999))
    assert changed == baseline


class FixedAssessor:
    def __init__(self, values):
        self.values = values

    def assess(self, _query, citations):
        return EvidenceAssessmentResult(tuple(CitationRelevanceAssessment(c.chunk_id, c.order, value) for c, value in zip(citations.citations, self.values)))


def test_malformed_assessor_result_fails_closed():
    class Broken:
        def assess(self, _query, _citations):
            return "bad"

    item = citation("Penduduk Jakarta tercatat.")
    assert_insufficient(evaluate("Penduduk Jakarta", item, assessor=Broken()), "relevance_assessment_unavailable", (item.chunk_id,))


def test_assessor_exception_fails_closed_without_private_text():
    class Broken:
        def assess(self, _query, _citations):
            raise RuntimeError("private query excerpt")

    item = citation("Penduduk Jakarta tercatat.")
    value = evaluate("private query", item, assessor=Broken())
    assert_insufficient(value, "relevance_assessment_unavailable", (item.chunk_id,))
    assert "private" not in repr(value)


def test_unclear_and_irrelevant_are_excluded():
    items = (citation("Penduduk Jakarta tercatat.", 1), citation("Curah hujan tercatat.", 2))
    value = evaluate("Penduduk Jakarta", *items, assessor=FixedAssessor((EvidenceRelevance.UNCLEAR, EvidenceRelevance.IRRELEVANT)))
    assert_insufficient(value, "no_relevant_evidence", tuple(item.chunk_id for item in items))


def test_default_and_class_factory_use_relevance_only():
    item = citation("Jumlah penduduk Jakarta adalah 11 juta jiwa.")
    for evaluator in (QualitativeRetrievalSufficiencyEvaluator(), QualitativeRetrievalSufficiencyEvaluator.default()):
        value = evaluator.evaluate("Berapa jumlah penduduk Jakarta?", retrieval((item,)), CitationBuildResult((item,)))
        assert_partial(value, (item.chunk_id,))


def result(**changes):
    first, second = str(uuid4()), str(uuid4())
    values = dict(decision=SufficiencyDecision.PARTIAL, reason_code="limited_citable_evidence", citation_count=2, usable_citation_count=0, low_structure_confidence_citation_count=0, limited_citation_count=1, excluded_citation_count=1, citation_ids=(first, second), usable_citation_ids=(), limited_citation_ids=(first,), excluded_citation_ids=(second,), may_answer_substantively=True, requires_limitation=True, requires_refusal=False)
    values.update(changes)
    return RetrievalSufficiencyResult(**values)


def test_result_contract_rejects_invalid_ids_counts_flags_and_partitions():
    with pytest.raises(SufficiencyValidationError):
        result(citation_ids=("bad",), citation_count=1, limited_citation_count=0, limited_citation_ids=(), excluded_citation_count=0, excluded_citation_ids=())
    with pytest.raises(SufficiencyValidationError):
        result(citation_count=True)
    with pytest.raises(SufficiencyValidationError):
        result(low_structure_confidence_citation_count=3)
    value = result()
    with pytest.raises(SufficiencyValidationError):
        replace(value, limited_citation_ids=value.excluded_citation_ids)
    with pytest.raises(SufficiencyValidationError):
        replace(value, requires_refusal=True)


def test_result_contract_preserves_future_sufficient_semantics():
    first = str(uuid4())
    value = RetrievalSufficiencyResult(SufficiencyDecision.SUFFICIENT, "citable_evidence_available", 1, 1, 0, 0, 0, (first,), (first,), (), (), True, False, False)
    assert value.decision is SufficiencyDecision.SUFFICIENT


def test_empty_reason_is_bidirectional():
    with pytest.raises(SufficiencyValidationError):
        RetrievalSufficiencyResult(SufficiencyDecision.INSUFFICIENT, "no_relevant_evidence", 0, 0, 0, 0, 0, (), (), (), (), False, True, True)
    first = str(uuid4())
    with pytest.raises(SufficiencyValidationError):
        RetrievalSufficiencyResult(SufficiencyDecision.INSUFFICIENT, "no_citable_evidence", 1, 0, 0, 0, 1, (first,), (), (), (first,), False, True, True)


def test_retrieval_contract_rejects_malformed_candidates():
    item = citation("Penduduk Jakarta tercatat.")
    evaluator = QualitativeRetrievalSufficiencyEvaluator()
    for retrieval_result in (
        FinalRetrievalResult(0, ()),
        FinalRetrievalResult(10, None),
        FinalRetrievalResult(10, (object(),)),
        FinalRetrievalResult(10, (replace(retrieval((item,)).candidates[0], rank=True),)),
        FinalRetrievalResult(10, (replace(retrieval((item,)).candidates[0], dense_rank=None, dense_score=None),)),
        FinalRetrievalResult(10, (replace(retrieval((item,)).candidates[0], document_id="bad"),)),
    ):
        with pytest.raises(SufficiencyValidationError):
            evaluator.evaluate("query", retrieval_result, CitationBuildResult((item,)) if retrieval_result.candidates else CitationBuildResult(()))


def test_retrieval_contract_rejects_nonfinite_scores_and_metadata():
    item = citation("Penduduk Jakarta tercatat.")
    base = retrieval((item,)).candidates[0]
    for candidate in (replace(base, dense_score=float("nan")), replace(base, sparse_rank=1, sparse_score=float("inf")), replace(base, page_end=2)):
        with pytest.raises(SufficiencyValidationError):
            QualitativeRetrievalSufficiencyEvaluator().evaluate("query", FinalRetrievalResult(10, (candidate,)), CitationBuildResult((item,)))


def assert_validation(candidate, message, *, limit=10, item=None):
    item = item or CitationPayload(candidate.chunk_id, 1, candidate.chunk_id, candidate.document_id, candidate.title, candidate.publication_year, candidate.region, candidate.region_level, candidate.topic, candidate.page_start, candidate.page_end, candidate.section_heading, candidate.source_url, candidate.pdf_url, "Penduduk Jakarta tercatat.", candidate.low_structure_confidence)
    with pytest.raises(SufficiencyValidationError, match=message) as caught:
        QualitativeRetrievalSufficiencyEvaluator().evaluate("private query", FinalRetrievalResult(limit, (candidate,)), CitationBuildResult((item,)))
    rendered = repr(caught.value)
    assert "private query" not in rendered
    assert "excerpt" not in rendered
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize("score", [True, "0.5", float("nan"), float("inf"), float("-inf"), 10**4000])
def test_invalid_rrf_score_is_sanitized(score):
    item = citation("Penduduk Jakarta tercatat.")
    assert_validation(replace(retrieval((item,)).candidates[0], rrf_score=score), "final retrieval score is invalid")


@pytest.mark.parametrize("field", ["dense_score", "sparse_score"])
def test_huge_source_score_is_sanitized(field):
    item = citation("Penduduk Jakarta tercatat.")
    candidate = retrieval((item,)).candidates[0]
    changes = {field: 10**4000}
    if field == "sparse_score":
        changes["sparse_rank"] = 1
    assert_validation(replace(candidate, **changes), "final retrieval score is invalid")


def test_candidate_publication_year_float_is_sanitized():
    item = citation("Penduduk Jakarta tercatat.")
    assert_validation(replace(retrieval((item,)).candidates[0], publication_year=2025.0), "final retrieval publication year is invalid", item=item)


def test_candidate_publication_year_boolean_is_sanitized():
    item = citation("Penduduk Jakarta tercatat.")
    assert_validation(replace(retrieval((item,)).candidates[0], publication_year=True), "final retrieval publication year is invalid", item=item)


@pytest.mark.parametrize("field", ["page_start", "page_end"])
def test_candidate_boolean_page_is_sanitized(field):
    item = citation("Penduduk Jakarta tercatat.")
    assert_validation(replace(retrieval((item,)).candidates[0], **{field: True}), f"final retrieval {field.replace('_', ' ')} is invalid", item=item)


@pytest.mark.parametrize("value", [-1, True])
def test_candidate_chunk_index_is_sanitized(value):
    item = citation("Penduduk Jakarta tercatat.")
    assert_validation(replace(retrieval((item,)).candidates[0], chunk_index=value), "final retrieval chunk index is invalid", item=item)


def test_candidate_nonboolean_low_structure_flag_is_sanitized():
    item = citation("Penduduk Jakarta tercatat.")
    assert_validation(replace(retrieval((item,)).candidates[0], low_structure_confidence=1), "final retrieval extraction metadata is invalid", item=item)


@pytest.mark.parametrize("field", ["title", "region", "region_level", "source_url"])
def test_candidate_required_text_type_is_sanitized(field):
    item = citation("Penduduk Jakarta tercatat.")
    message = "final retrieval source URL is invalid" if field == "source_url" else f"final retrieval {field.replace('_', ' ')} is invalid"
    assert_validation(replace(retrieval((item,)).candidates[0], **{field: 1}), message, item=item)


def test_requested_limit_above_default_top_k_is_accepted():
    item = citation("Penduduk Jakarta tercatat.")
    value = QualitativeRetrievalSufficiencyEvaluator().evaluate("Penduduk Jakarta", FinalRetrievalResult(11, retrieval((item,)).candidates), CitationBuildResult((item,)))
    assert_partial(value, (item.chunk_id,))


def test_nonpositive_requested_limits_remain_invalid():
    item = citation("Penduduk Jakarta tercatat.")
    candidate = retrieval((item,)).candidates
    for limit in (0, -1, True, "11"):
        with pytest.raises(SufficiencyValidationError, match="final retrieval requested limit is invalid"):
            QualitativeRetrievalSufficiencyEvaluator().evaluate("query", FinalRetrievalResult(limit, candidate), CitationBuildResult((item,)))


def test_extraction_method_is_type_checked_before_equality():
    class HostileText:
        def __eq__(self, _other):
            raise RuntimeError("private extraction text")

        def __str__(self):
            raise RuntimeError("private string")

    item = citation("Penduduk Jakarta tercatat.")
    candidate = replace(retrieval((item,)).candidates[0], extraction_method=HostileText())
    assert_validation(candidate, "final retrieval extraction metadata is invalid", item=item)


def test_extraction_method_spoofing_subclass_is_rejected():
    class SpoofedText(str):
        def __eq__(self, _other):
            return True

    item = citation("Penduduk Jakarta tercatat.")
    candidate = replace(retrieval((item,)).candidates[0], extraction_method=SpoofedText("not_text_layer"))
    assert_validation(candidate, "final retrieval extraction metadata is invalid", item=item)


def test_hostile_string_subclass_is_rejected_before_string_methods():
    calls = []

    class HostileString(str):
        def strip(self):
            calls.append("strip")
            raise RuntimeError("private strip")

        def replace(self, *_args):
            calls.append("replace")
            raise RuntimeError("private replace")

        def __eq__(self, _other):
            calls.append("eq")
            raise RuntimeError("private equality")

        def __str__(self):
            calls.append("str")
            raise RuntimeError("private string")

    item = citation("Penduduk Jakarta tercatat.")
    candidate = replace(retrieval((item,)).candidates[0], title=HostileString("Title"))
    assert_validation(candidate, "final retrieval title is invalid", item=item)
    assert calls == []


class HostileInt(int):
    def __lt__(self, _other):
        raise RuntimeError("private less-than")

    def __eq__(self, _other):
        raise RuntimeError("private equality")

    def __int__(self):
        raise RuntimeError("private int")

    def __float__(self):
        raise RuntimeError("private float")


def test_hostile_integer_subclasses_are_rejected_before_operations():
    item = citation("Penduduk Jakarta tercatat.")
    candidate = retrieval((item,)).candidates[0]
    cases = (
        (FinalRetrievalResult(HostileInt(10), (candidate,)), "final retrieval requested limit is invalid"),
        (FinalRetrievalResult(10, (replace(candidate, rank=HostileInt(1)),)), "final retrieval ranks are invalid"),
        (FinalRetrievalResult(10, (replace(candidate, publication_year=HostileInt(2025)),)), "final retrieval publication year is invalid"),
        (FinalRetrievalResult(10, (replace(candidate, page_start=HostileInt(1)),)), "final retrieval page start is invalid"),
        (FinalRetrievalResult(10, (replace(candidate, chunk_index=HostileInt(0)),)), "final retrieval chunk index is invalid"),
    )
    for retrieval_result, message in cases:
        with pytest.raises(SufficiencyValidationError, match=message) as caught:
            QualitativeRetrievalSufficiencyEvaluator().evaluate("private query", retrieval_result, CitationBuildResult((item,)))
        assert "private" not in repr(caught.value)
        assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_hostile_float_subclass_is_rejected_before_conversion():
    class HostileFloat(float):
        def __float__(self):
            raise RuntimeError("private float")

    item = citation("Penduduk Jakarta tercatat.")
    candidate = replace(retrieval((item,)).candidates[0], rrf_score=HostileFloat(0.5))
    assert_validation(candidate, "final retrieval score is invalid", item=item)


def test_numeric_conversion_object_is_sanitized():
    class HostileNumber:
        def __float__(self):
            raise RuntimeError("private score")

        def __str__(self):
            raise RuntimeError("private score text")

    item = citation("Penduduk Jakarta tercatat.")
    candidate = replace(retrieval((item,)).candidates[0], rrf_score=HostileNumber())
    assert_validation(candidate, "final retrieval score is invalid", item=item)


def test_no_normal_evaluator_path_emits_sufficient():
    item = citation("Jumlah penduduk Jakarta adalah 11 juta jiwa.")
    value = evaluate("Berapa jumlah penduduk Jakarta?", item)
    assert value.decision is not SufficiencyDecision.SUFFICIENT
