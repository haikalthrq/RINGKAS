from __future__ import annotations

import csv
from pathlib import Path


AUDIT_ROW_COUNT = 20
REQUIRED_COLUMNS = (
    "question_id",
    "audit_status",
    "citation_correctness",
    "groundedness",
    "number_accuracy",
    "period_accuracy",
    "region_accuracy",
    "unit_accuracy",
    "definition_accuracy",
    "page_correctness",
    "source_correctness",
    "reviewer_verdict",
    "reviewer_notes",
)


def validate_audit_template(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
            raise ValueError("manual audit template columns do not match the required audit fields")
        rows = list(reader)

    if len(rows) != AUDIT_ROW_COUNT:
        raise ValueError(f"manual audit template must contain exactly {AUDIT_ROW_COUNT} rows")
    question_ids = [row["question_id"] for row in rows]
    valid_ids = {f"q-{index:03d}" for index in range(1, 101)}
    if len(set(question_ids)) != AUDIT_ROW_COUNT or not set(question_ids).issubset(valid_ids):
        raise ValueError("manual audit rows must link 20 unique evaluation question IDs")
    if any(row["audit_status"] != "pending" for row in rows):
        raise ValueError("manual audit template must remain pending until a human completes it")
    return rows
