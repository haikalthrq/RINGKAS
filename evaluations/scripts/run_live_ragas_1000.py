#!/usr/bin/env python3
"""Run the live RAGAS harness and always write a truthful sanitized report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EVALUATIONS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = EVALUATIONS_DIR / "evaluation_dataset.json"
DEFAULT_RESPONSES = EVALUATIONS_DIR / "responses.json"
DEFAULT_OUTPUT = EVALUATIONS_DIR / "ragas_report.json"


def blocked(error_class: str, reason: str) -> dict[str, object]:
    return {
        "evaluation_label": "live RAGAS evaluation",
        "status": "blocked",
        "sample_count": 0,
        "metrics": None,
        "error_class": error_class,
        "reason": reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--responses", type=Path, default=DEFAULT_RESPONSES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        responses = json.loads(args.responses.read_text(encoding="utf-8"))
        dataset_records = dataset.get("records", [])
        response_records = responses.get("records", [])
        expected_ids = [f"q-{index:04d}" for index in range(1, 1001)]
        if dataset.get("dataset_status") != "ready" or dataset.get("capacity") != 1000 or len(dataset_records) != 1000:
            report = blocked("DatasetValidationError", "dataset is not ready with exactly 1000 records")
        elif len(response_records) != 1000 or [record.get("question_id") for record in response_records] != expected_ids:
            report = blocked("ResponseValidationError", "responses do not contain exactly q-0001 through q-1000")
        elif any(
            response.get("user_input") != dataset_record.get("question_text")
            or response.get("reference") != dataset_record.get("reference_answer")
            or not response.get("retrieved_contexts")
            for dataset_record, response in zip(dataset_records, response_records, strict=True)
        ):
            report = blocked("ResponseValidationError", "response fields do not match the current factual dataset")
        else:
            from ringkas_worker.ragas_harness import run_live

            report = run_live(args.dataset, args.responses)
            report["sample_count"] = 1000 if report.get("status") == "completed" else report.get("sample_count", 0)
    except ImportError as error:
        report = blocked(error.__class__.__name__, "pinned RAGAS dependencies are unavailable")
    except Exception as error:
        report = blocked(error.__class__.__name__, "live RAGAS execution raised a sanitized exception")
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report.get("status"), "sample_count": report.get("sample_count", 0)}, sort_keys=True))
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
