from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


DATASET_PATH = Path(__file__).resolve().parents[1] / "evaluation_dataset.json"
DATASET_CAPACITY = 1000
APPROVED_QUESTION_TYPES = frozenset(
    {"definition", "number", "period", "region", "methodology", "document_search"}
)
QuestionType = Literal["definition", "number", "period", "region", "methodology", "document_search"]


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID | None = None
    chunk_id: UUID | None = None
    qdrant_point_id: str | None = None
    document_title: str | None = None
    publication_year: int | None = Field(default=None, gt=0)
    region: str | None = None
    page_start: int | None = Field(default=None, gt=0)
    page_end: int | None = Field(default=None, gt=0)
    source_url: AnyHttpUrl | None = None
    excerpt: str | None = None


class GroundTruthReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_document_id: UUID
    expected_chunk_id: UUID
    expected_qdrant_point_id: str
    expected_page_start: int = Field(gt=0)
    expected_page_end: int = Field(gt=0)


class EvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(pattern=r"^q-[0-9]{4}$")
    question_text: str = ""
    question_type: QuestionType = "definition"
    topic: str = ""
    reference_answer: str = ""
    evidence: EvidenceReference = Field(default_factory=EvidenceReference)
    ground_truth: GroundTruthReference | None = None
    verification_status: Literal["pending", "verified", "rejected"] = "pending"
    reviewer_notes: str = ""

    @model_validator(mode="after")
    def verified_records_require_grounded_evidence(self) -> EvaluationRecord:
        if self.verification_status != "verified":
            return self

        required = (
            self.question_text,
            self.question_type,
            self.topic,
            self.reference_answer,
            self.evidence.document_id,
            self.evidence.chunk_id,
            self.evidence.qdrant_point_id,
            self.evidence.document_title,
            self.evidence.publication_year,
            self.evidence.region,
            self.evidence.page_start,
            self.evidence.page_end,
            self.evidence.source_url,
            self.evidence.excerpt,
            self.ground_truth,
        )
        if any(value is None or (isinstance(value, str) and not value.strip()) for value in required):
            raise ValueError("verified evaluation records require complete grounded evidence")
        return self


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    dataset_status: Literal["pending_automated_validation", "ready"]
    capacity: int = Field(gt=0)
    records: list[EvaluationRecord]

    @model_validator(mode="after")
    def validate_capacity_and_ids(self) -> EvaluationDataset:
        if self.capacity != DATASET_CAPACITY or len(self.records) != self.capacity:
            raise ValueError(f"evaluation dataset must contain exactly {DATASET_CAPACITY} records")
        width = 4
        expected_ids = [f"q-{index:0{width}d}" for index in range(1, self.capacity + 1)]
        ids = [record.question_id for record in self.records]
        if ids != expected_ids:
            raise ValueError(f"evaluation question IDs must be stable and contiguous from {expected_ids[0]} to {expected_ids[-1]}")
        if self.dataset_status == "ready":
            if any(record.verification_status != "verified" for record in self.records):
                raise ValueError(f"ready evaluation datasets require all {self.capacity} records to be verified")
            if not APPROVED_QUESTION_TYPES.issubset(record.question_type for record in self.records):
                raise ValueError("ready evaluation datasets must cover every approved question type")
        return self


def load_dataset(path: Path = DATASET_PATH) -> EvaluationDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationDataset.model_validate(payload)
