from dataclasses import replace
from uuid import uuid4

import pytest

from ringkas_worker.citations import CitationBuildResult, CitationPayload
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult
from ringkas_worker.sufficiency import CitationRelevanceAssessment, EvidenceAssessmentResult, EvidenceRelevance, LexicalEvidenceRelevanceAssessor, QualitativeRetrievalSufficiencyEvaluator, SufficiencyDecision


def citation(excerpt, order=1, *, title="Publikasi", year=2025, region="DKI Jakarta", low=False):
    chunk_id = str(uuid4())
    return CitationPayload(chunk_id, order, chunk_id, str(uuid4()), title, year, region, "province", None, None, None, None, "https://bps.test", None, excerpt, low)


def retrieval(citations, score=0.5):
    return FinalRetrievalResult(10, tuple(FinalRetrievalCandidate(index, score, item.chunk_id, item.document_id, str(uuid4()), 1, None, score, None, item.title, item.publication_year, item.region, item.region_level, item.topic, item.page_start, item.page_end, item.section_heading, 0, "text_layer", item.low_structure_confidence, item.source_url, item.pdf_url) for index, item in enumerate(citations, 1)))


def evaluate(query, *items, score=0.5, assessor=None):
    citations = CitationBuildResult(tuple(items))
    return QualitativeRetrievalSufficiencyEvaluator(assessor).evaluate(query, retrieval(citations.citations, score), citations)


def test_metadata_only_matches_are_insufficient():
    item = citation("Curah hujan bulanan meningkat.", title="Jumlah Penduduk Jakarta 2024", year=2024, region="Jakarta")
    assert evaluate("Berapa jumlah penduduk Jakarta tahun 2024?", item).decision is SufficiencyDecision.INSUFFICIENT


def test_numeric_evidence_and_period_requirements():
    item = citation("Jumlah penduduk Jakarta pada tahun 2024 adalah 11.000.000 jiwa.")
    no_value = citation("Jumlah penduduk Jakarta pada tahun 2024 tercatat dalam publikasi.")
    metadata_period = citation("Jumlah penduduk Jakarta adalah 11.000.000 jiwa.", year=2024)
    assert evaluate("Menurut publikasi, berapa jumlah penduduk Jakarta pada tahun 2024 dalam jiwa?", item).decision is SufficiencyDecision.SUFFICIENT
    assert evaluate("Berapa jumlah penduduk Jakarta tahun 2024?", no_value).decision is SufficiencyDecision.PARTIAL
    assert evaluate("Berapa jumlah penduduk Jakarta tahun 2024?", metadata_period).decision is SufficiencyDecision.PARTIAL


def test_unit_definition_comparison_trend_and_causality_require_explicit_evidence():
    missing_unit = citation("Jumlah penduduk Jakarta pada tahun 2024 adalah 11000000.")
    named = citation("Tingkat pengangguran terbuka Jakarta dilaporkan setiap tahun.")
    defined = citation("Tingkat pengangguran terbuka adalah persentase angkatan kerja yang tidak bekerja dan sedang mencari pekerjaan.")
    jakarta = citation("Jumlah penduduk Jakarta tahun 2024 adalah 11 juta jiwa.", 1)
    bekasi = citation("Jumlah penduduk Bekasi tahun 2024 adalah 2 juta jiwa.", 2)
    one_period = citation("Tingkat kemiskinan Jakarta tahun 2024 adalah 4 persen.")
    trend = citation("Tingkat kemiskinan Jakarta tahun 2023 adalah 5 persen dan tahun 2024 adalah 4 persen.")
    cause = citation("Kemiskinan Jakarta meningkat karena kenaikan harga pangan pada 2024.")
    assert evaluate("Berapa jumlah penduduk Jakarta tahun 2024 dalam jiwa?", missing_unit).decision is SufficiencyDecision.PARTIAL
    assert evaluate("Apa definisi tingkat pengangguran terbuka?", named).decision is SufficiencyDecision.PARTIAL
    assert evaluate("Apa definisi tingkat pengangguran terbuka?", defined).decision is SufficiencyDecision.SUFFICIENT
    assert evaluate("Bandingkan jumlah penduduk Jakarta dan Bekasi tahun 2024.", jakarta, bekasi).decision is SufficiencyDecision.SUFFICIENT
    assert evaluate("Bandingkan jumlah penduduk Jakarta dan Bekasi tahun 2024.", jakarta).decision is SufficiencyDecision.PARTIAL
    assert evaluate("Bagaimana tren tingkat kemiskinan Jakarta?", one_period).decision is SufficiencyDecision.PARTIAL
    assert evaluate("Bagaimana tren tingkat kemiskinan Jakarta?", trend).decision is SufficiencyDecision.SUFFICIENT
    assert evaluate("Mengapa kemiskinan Jakarta meningkat?", one_period).decision is SufficiencyDecision.PARTIAL
    assert evaluate("Mengapa kemiskinan meningkat?", cause).decision is SufficiencyDecision.SUFFICIENT


def test_normalization_scores_default_malformed_and_ordering():
    first = citation("Jumlah penduduk Jakarta tahun 2024 adalah 11 juta jiwa.", 1)
    second = citation("Curah hujan Jakarta adalah 100 milimeter.", 2, low=True)
    assert evaluate("Apakah menurut publikasi jumlah penduduk Jakarta adalah 11 juta jiwa?", first).decision is SufficiencyDecision.SUFFICIENT
    assert evaluate("Apa jumlah penduduk Jakarta?", citation("Curah hujan Jakarta adalah 100 milimeter.")).decision is SufficiencyDecision.INSUFFICIENT
    assert evaluate("Berapa jumlah penduduk Jakarta tahun 2024 dalam jiwa?", first, second, score=-999).decision is evaluate("Berapa jumlah penduduk Jakarta tahun 2024 dalam jiwa?", first, second, score=999).decision
    result = evaluate("Berapa jumlah penduduk Jakarta tahun 2024 dalam jiwa?", first, second)
    assert result.usable_citation_ids == (first.chunk_id,)
    assert result.excluded_citation_ids == (second.chunk_id,)
    assert result.low_structure_confidence_citation_count == 1
    assert not hasattr(result, "low_confidence_citation_count")
    assert QualitativeRetrievalSufficiencyEvaluator.default().evaluate("Berapa jumlah penduduk Jakarta tahun 2024 dalam jiwa?", retrieval((first,)), CitationBuildResult((first,))).decision is SufficiencyDecision.SUFFICIENT

    class MalformedAssessor:
        def assess(self, _query, _citations):
            return "invalid"

    assert evaluate("Berapa jumlah penduduk Jakarta tahun 2024?", first, assessor=MalformedAssessor()).decision is SufficiencyDecision.INSUFFICIENT


def test_assessment_records_remain_validated():
    item = citation("Jumlah penduduk Jakarta tahun 2024 adalah 11 juta jiwa.")
    with pytest.raises(Exception):
        EvidenceAssessmentResult((CitationRelevanceAssessment(item.chunk_id, 2, EvidenceRelevance.RELEVANT),))
