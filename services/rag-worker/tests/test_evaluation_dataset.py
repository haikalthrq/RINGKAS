import json

import pytest
from pydantic import ValidationError

from ringkas_worker.evaluation_dataset import DATASET_PATH, EvaluationDataset, EvaluationRecord, load_dataset


FACTUAL_DATASET_PATH = DATASET_PATH.parents[2] / "evaluations" / "evaluation_dataset.json"


def test_template_has_exactly_100_pending_stable_slots() -> None:
    dataset = load_dataset(DATASET_PATH)
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))

    assert len(payload["records"]) == 100
    assert "record_template" not in payload
    assert len(dataset.records) == 100
    assert dataset.records[0].question_id == "q-001"
    assert dataset.records[-1].question_id == "q-100"
    assert all(record.verification_status == "pending" for record in dataset.records)


def test_verified_record_requires_complete_grounded_evidence() -> None:
    with pytest.raises(ValidationError, match="complete grounded evidence"):
        EvaluationRecord(question_id="q-001", question_type="definition", verification_status="verified")


def test_verified_record_cannot_keep_pending_question_type() -> None:
    with pytest.raises(ValidationError, match="approved question type"):
        EvaluationRecord(
            question_id="q-001",
            question_text="Question",
            topic="Topic",
            reference_answer="Answer",
            evidence={
                "document_id": "00000000-0000-0000-0000-000000000001",
                "chunk_id": "00000000-0000-0000-0000-000000000002",
                "document_title": "Title",
                "publication_year": 2024,
                "region": "DKI Jakarta",
                "page_start": 1,
                "page_end": 1,
                "source_url": "https://example.com/source.pdf",
                "excerpt": "Evidence",
            },
            verification_status="verified",
        )


def test_ready_dataset_requires_all_records_verified() -> None:
    pending = load_dataset(DATASET_PATH)

    with pytest.raises(ValidationError, match="all 100 records"):
        EvaluationDataset.model_validate({**pending.model_dump(mode="json"), "dataset_status": "ready"})


def test_pending_record_does_not_invent_evidence() -> None:
    record = EvaluationRecord(question_id="q-001")

    assert record.evidence.document_id is None
    assert record.evidence.source_url is None


def test_factual_dataset_has_complete_ground_truth_contract() -> None:
    dataset = load_dataset(FACTUAL_DATASET_PATH)

    assert dataset.dataset_status == "ready"
    assert dataset.capacity == 1000
    assert len(dataset.records) == 1000
    assert all(record.verification_status == "verified" for record in dataset.records)
    assert all(record.evidence.qdrant_point_id for record in dataset.records)
    assert all(record.ground_truth is not None for record in dataset.records)
