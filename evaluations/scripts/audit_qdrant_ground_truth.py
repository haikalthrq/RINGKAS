#!/usr/bin/env python3
"""Audit every factual dataset ground-truth point against the live Qdrant collection."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient


EVALUATIONS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = EVALUATIONS_DIR / "evaluation_dataset.json"
DEFAULT_OUTPUT = EVALUATIONS_DIR / "qdrant_ground_truth_audit_1000.json"
COLLECTION = os.getenv("QDRANT_COLLECTION_NAME", "ringkas_chunks_cf_qwen3_embedding_v2")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://qdrant:6333"))
    args = parser.parse_args()

    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    failures: list[dict[str, Any]] = []
    if payload.get("dataset_status") != "ready" or payload.get("capacity") != 1000 or len(records) != 1000:
        failures.append({"question_id": None, "error": "dataset is not a ready 1000-record dataset"})

    point_ids = [str(record.get("ground_truth", {}).get("expected_qdrant_point_id", "")) for record in records]
    client = QdrantClient(url=args.qdrant_url, api_key=os.getenv("QDRANT_API_KEY") or None)
    points: dict[str, Any] = {}
    try:
        for start in range(0, len(point_ids), 128):
            batch = point_ids[start : start + 128]
            for point in client.retrieve(collection_name=COLLECTION, ids=batch, with_payload=True, with_vectors=False):
                points[str(point.id)] = point
    finally:
        client.close()

    audited = 0
    for record in records:
        question_id = record.get("question_id")
        evidence = record.get("evidence", {})
        ground_truth = record.get("ground_truth", {})
        point_id = str(ground_truth.get("expected_qdrant_point_id", ""))
        point = points.get(point_id)
        errors: list[str] = []
        if point is None:
            errors.append("qdrant point does not exist")
        else:
            audited += 1
            point_payload = point.payload or {}
            expected = {
                "chunk_id": ground_truth.get("expected_chunk_id"),
                "document_id": ground_truth.get("expected_document_id"),
                "page_start": ground_truth.get("expected_page_start"),
                "page_end": ground_truth.get("expected_page_end"),
            }
            actual = {field: point_payload.get(field) for field in expected}
            for field in expected:
                if str(actual[field]) != str(expected[field]):
                    errors.append(f"payload {field} differs from ground truth")
            if str(point.id) != point_id:
                errors.append("returned point ID differs from ground truth")
            if str(point_payload.get("chunk_id")) != str(evidence.get("chunk_id")):
                errors.append("payload chunk_id differs from evidence")
        if errors:
            failures.append({"question_id": question_id, "errors": errors})

    report = {
        "status": "passed" if not failures else "failed",
        "dataset_capacity": len(records),
        "collection": COLLECTION,
        "points_requested": len(point_ids),
        "points_found": len(points),
        "records_audited": audited,
        "failures": len(failures),
        "rejected_records": failures,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "records": len(records), "failures": len(failures)}, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
