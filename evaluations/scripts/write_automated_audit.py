#!/usr/bin/env python3
"""Write a 1,000-row machine audit of the regenerated response contract."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


EVALUATIONS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = EVALUATIONS_DIR / "evaluation_dataset.json"
DEFAULT_RESPONSES = EVALUATIONS_DIR / "responses.json"
DEFAULT_OUTPUT = EVALUATIONS_DIR / "automated_audit_report.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--responses", type=Path, default=DEFAULT_RESPONSES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    response_payload = json.loads(args.responses.read_text(encoding="utf-8"))
    records = dataset.get("records", [])
    responses = response_payload.get("records", [])
    response_by_id = {record.get("question_id"): record for record in responses}
    expected_ids = [f"q-{index:04d}" for index in range(1, 1001)]
    if dataset.get("dataset_status") != "ready" or dataset.get("capacity") != 1000 or len(records) != 1000:
        raise SystemExit("dataset must be ready with exactly 1000 records")
    if len(responses) > 1000 or len(response_by_id) != len(responses) or any(question_id not in expected_ids for question_id in response_by_id):
        raise SystemExit("responses contain duplicate or invalid question IDs")

    fields = ("question_id", "question_type", "audit_status", "user_input_matches", "reference_matches", "response_present", "retrieved_context_count", "retrieved_chunk_ids", "retrieved_document_ids", "source_sufficiency", "provider", "synthetic_fallback_context")
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            response = response_by_id.get(record["question_id"])
            if response is None:
                writer.writerow({
                    "question_id": record["question_id"],
                    "question_type": record["question_type"],
                    "audit_status": "failed",
                    "user_input_matches": "false",
                    "reference_matches": "false",
                    "response_present": "false",
                    "retrieved_context_count": 0,
                    "retrieved_chunk_ids": "[]",
                    "retrieved_document_ids": "[]",
                    "source_sufficiency": "not_generated",
                    "provider": "not_generated",
                    "synthetic_fallback_context": "false",
                })
                continue
            user_matches = response.get("user_input") == record["question_text"]
            reference_matches = response.get("reference") == record["reference_answer"]
            contexts = response.get("retrieved_contexts")
            present = isinstance(response.get("response"), str) and bool(response["response"].strip())
            no_fallback = isinstance(contexts, list) and len(contexts) > 0
            writer.writerow({
                "question_id": record["question_id"],
                "question_type": record["question_type"],
                "audit_status": "passed" if user_matches and reference_matches and present and no_fallback else "failed",
                "user_input_matches": str(user_matches).lower(),
                "reference_matches": str(reference_matches).lower(),
                "response_present": str(present).lower(),
                "retrieved_context_count": len(contexts) if isinstance(contexts, list) else 0,
                "retrieved_chunk_ids": json.dumps(response.get("retrieved_chunk_ids", []), ensure_ascii=False),
                "retrieved_document_ids": json.dumps(response.get("retrieved_document_ids", []), ensure_ascii=False),
                "source_sufficiency": response.get("source_sufficiency"),
                "provider": response.get("provider"),
                "synthetic_fallback_context": str(not no_fallback).lower(),
            })
    passed = len(responses) == 1000 and all(response.get("question_id") in response_by_id for response in records)
    print(json.dumps({"status": "passed" if passed else "blocked", "rows": 1000, "generated_responses": len(responses), "output": str(args.output)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
