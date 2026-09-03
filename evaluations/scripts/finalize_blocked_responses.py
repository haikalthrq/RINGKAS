#!/usr/bin/env python3
"""Persist successful partial responses and a truthful blocked generation report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EVALUATIONS_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=EVALUATIONS_DIR / "evaluation_dataset.json")
    parser.add_argument("--checkpoint", type=Path, default=EVALUATIONS_DIR / "responses_checkpoint.json")
    parser.add_argument("--output", type=Path, default=EVALUATIONS_DIR / "responses.json")
    parser.add_argument("--report", type=Path, default=EVALUATIONS_DIR / "response_generation_report.json")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--provider", default="cloudflare_workers_ai")
    parser.add_argument("--model", default="@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    args = parser.parse_args()
    dataset_bytes = args.dataset.read_bytes()
    dataset = json.loads(dataset_bytes)
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    dataset_records = dataset.get("records", [])
    responses = checkpoint.get("responses", [])
    expected = {record["question_id"]: record for record in dataset_records}
    valid_responses = [
        response for response in responses
        if response.get("question_id") in expected
        and response.get("user_input") == expected[response["question_id"]]["question_text"]
        and response.get("reference") == expected[response["question_id"]]["reference_answer"]
        and isinstance(response.get("retrieved_contexts"), list)
        and response["retrieved_contexts"]
    ]
    valid_responses.sort(key=lambda response: response["question_id"])
    args.output.write_text(json.dumps({"records": valid_responses}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "status": "blocked",
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "dataset_capacity": len(dataset_records),
        "response_count": len(valid_responses),
        "failure_count": len(dataset_records) - len(valid_responses),
        "not_generated_count": len(dataset_records) - len(valid_responses),
        "failures": [{"error_category": "provider_rate_limit", "error_class": "HTTPError", "reason": args.reason}],
        "provider": args.provider,
        "model": args.model,
        "synthetic_fallback_context_count": 0,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "blocked", "responses": len(valid_responses), "not_generated": report["not_generated_count"]}, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
