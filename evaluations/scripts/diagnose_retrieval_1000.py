#!/usr/bin/env python3
"""Run resumable dense, sparse, and RRF rank diagnostics on the private RAG engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ringkas_worker.query_service import QueryEngine


EVALUATIONS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = EVALUATIONS_DIR / "evaluation_dataset.json"
DEFAULT_OUTPUT = EVALUATIONS_DIR / "retrieval_diagnostic_1000.json"
DEFAULT_CHECKPOINT = EVALUATIONS_DIR / "retrieval_diagnostic_1000_checkpoint.json"
DEFAULT_LOG = EVALUATIONS_DIR / "retrieval_diagnostic_1000.log"
SOURCES = ("dense", "sparse", "rrf")
RECALL_KS = (1, 5, 10, 20, 30)


def atomic_write(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def rank(candidates: Iterable[Any], expected_chunk_id: str) -> tuple[int | None, str | None]:
    for candidate in candidates:
        if candidate.chunk_id == expected_chunk_id:
            return candidate.rank, candidate.qdrant_point_id
    return None, None


def error_category(error: BaseException) -> str:
    name = error.__class__.__name__.casefold()
    if "ratelimit" in name or "rate_limit" in name or "429" in str(error):
        return "provider_rate_limit"
    if "transport" in name or "timeout" in name or "connection" in name:
        return "transport"
    if "provider" in name or "embedding" in name or "encoding" in name:
        return "provider"
    return "other"


def retryable(category: str) -> bool:
    return category in {"provider_rate_limit", "provider", "transport"}


def query_with_backoff(engine: QueryEngine, question: str, logger: logging.Logger) -> tuple[Any, Any, Any, int]:
    last_error: BaseException | None = None
    for attempt in range(4):
        try:
            dense = engine._dense.retrieve(question)
            sparse = engine._sparse.retrieve(engine._sparse_encoder.encode_query(question))
            fused = engine._fusion.fuse(dense, sparse)
            return dense, sparse, fused, attempt
        except Exception as error:
            last_error = error
            category = error_category(error)
            if not retryable(category) or attempt == 3:
                raise
            delay = min(60, 2**attempt)
            logger.warning("retry category=%s attempt=%d delay_seconds=%d", category, attempt + 1, delay)
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def rank_metrics(results: list[dict[str, Any]], source: str) -> dict[str, Any]:
    ranks = [result.get(f"{source}_rank") for result in results]
    observed = [value for value in ranks if isinstance(value, int)]
    return {
        "sample_count": len(results),
        "hit_count": len(observed),
        "miss_count": len(results) - len(observed),
        "recall_at": {str(k): sum(1 for value in ranks if isinstance(value, int) and value <= k) / len(results) if results else 0.0 for k in RECALL_KS},
        "mrr": sum(1.0 / value for value in observed) / len(results) if results else 0.0,
        "mean_rank": statistics.mean(observed) if observed else None,
        "median_rank": statistics.median(observed) if observed else None,
        "rank_observation_count": len(observed),
    }


def grouped_metrics(results: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        groups.setdefault(str(result.get(field)), []).append(result)
    return {key: {source: rank_metrics(group, source) for source in SOURCES} for key, group in sorted(groups.items())}


def build_metrics(results: list[dict[str, Any]], failures: Counter[str], self_retrieval: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sample_count": len(results),
        "overall": {source: rank_metrics(results, source) for source in SOURCES},
        "by_question_type": grouped_metrics(results, "question_type"),
        "by_document": grouped_metrics(results, "expected_document_id"),
        "by_publication_year": grouped_metrics(results, "publication_year"),
        "failure_counts": dict(sorted(failures.items())),
        "total_failures": sum(failures.values()),
        "self_retrieval": {
            "sample_count": len(self_retrieval),
            "vector_nonzero_count": sum(1 for item in self_retrieval if item.get("vector_nonzero")),
            "records": self_retrieval,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()
    logging.basicConfig(filename=args.log, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("retrieval-diagnostic")

    dataset_bytes = args.dataset.read_bytes()
    dataset = json.loads(dataset_bytes)
    records = dataset.get("records", [])
    if dataset.get("dataset_status") != "ready" or dataset.get("capacity") != 1000 or len(records) != 1000:
        raise SystemExit("dataset must be ready with exactly 1000 records")
    dataset_sha256 = hashlib.sha256(dataset_bytes).hexdigest()

    results: list[dict[str, Any]] = []
    if args.checkpoint.exists():
        checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
        if checkpoint.get("dataset_sha256") == dataset_sha256:
            results = [result for result in checkpoint.get("results", []) if not result.get("error_category")]
            logger.info("resuming completed=%d total=%d", len(results), len(records))
        else:
            logger.warning("ignoring checkpoint for a different dataset")
    completed_ids = {result.get("question_id") for result in results if not result.get("error_category")}
    failures: Counter[str] = Counter(result.get("error_category") for result in results if result.get("error_category"))

    engine = QueryEngine.from_environment()
    self_retrieval: list[dict[str, Any]] = []
    try:
        for record in records[:20]:
            item = {
                "question_id": record["question_id"],
                "expected_qdrant_point_id": record["ground_truth"]["expected_qdrant_point_id"],
                "vector_nonzero": False,
                "vector_dimension": None,
                "dense_rank": None,
                "error_category": None,
            }
            try:
                point = engine._dense._qdrant_client.retrieve(
                    collection_name=engine._dense._settings.collection_name,
                    ids=[record["ground_truth"]["expected_qdrant_point_id"]],
                    with_payload=False,
                    with_vectors=True,
                )[0]
                vector = point.vector
                if isinstance(vector, dict):
                    vector = vector.get("dense")
                item["vector_dimension"] = len(vector) if isinstance(vector, (list, tuple)) else None
                item["vector_nonzero"] = bool(vector) and any(float(value) != 0.0 for value in vector)
                dense = engine._dense.retrieve(record["evidence"]["excerpt"])
                item["dense_rank"], _ = rank(dense.candidates, record["ground_truth"]["expected_chunk_id"])
            except Exception as error:
                item["error_category"] = error_category(error)
                logger.error("self_retrieval question_id=%s category=%s", record["question_id"], item["error_category"])
            self_retrieval.append(item)

        for index, record in enumerate(records, 1):
            if record["question_id"] in completed_ids:
                continue
            base = {
                "question_id": record["question_id"],
                "question_type": record["question_type"],
                "expected_document_id": record["ground_truth"]["expected_document_id"],
                "expected_chunk_id": record["ground_truth"]["expected_chunk_id"],
                "expected_qdrant_point_id": record["ground_truth"]["expected_qdrant_point_id"],
                "publication_year": record["evidence"]["publication_year"],
                "dense_rank": None,
                "sparse_rank": None,
                "rrf_rank": None,
                "dense_qdrant_point_id": None,
                "sparse_qdrant_point_id": None,
                "rrf_qdrant_point_id": None,
                "dense_candidate_count": 0,
                "sparse_candidate_count": 0,
                "rrf_candidate_count": 0,
                "retry_count": 0,
                "error_category": None,
                "error_class": None,
            }
            try:
                dense, sparse, fused, retries = query_with_backoff(engine, record["question_text"], logger)
                base["dense_rank"], base["dense_qdrant_point_id"] = rank(dense.candidates, base["expected_chunk_id"])
                base["sparse_rank"], base["sparse_qdrant_point_id"] = rank(sparse.candidates, base["expected_chunk_id"])
                base["rrf_rank"], base["rrf_qdrant_point_id"] = rank(fused.candidates, base["expected_chunk_id"])
                base["dense_candidate_count"] = len(dense.candidates)
                base["sparse_candidate_count"] = len(sparse.candidates)
                base["rrf_candidate_count"] = len(fused.candidates)
                base["retry_count"] = retries
            except Exception as error:
                base["error_category"] = error_category(error)
                base["error_class"] = error.__class__.__name__
                failures[base["error_category"]] += 1
                logger.error("question_id=%s category=%s class=%s", record["question_id"], base["error_category"], base["error_class"])
            results.append(base)
            if index % 10 == 0 or index == len(records):
                atomic_write(args.checkpoint, {"dataset_sha256": dataset_sha256, "results": results})
                logger.info("checkpoint=%d/%d", index, len(records))
    finally:
        engine.close()

    results.sort(key=lambda item: item["question_id"])
    metrics = build_metrics(results, failures, self_retrieval)
    output = {
        "status": "passed" if len(results) == 1000 and not failures else "completed_with_failures",
        "dataset_sha256": dataset_sha256,
        "dataset_capacity": len(records),
        "results": results,
        "metrics": metrics,
    }
    atomic_write(args.output, output)
    print(json.dumps({"status": output["status"], "records": len(results), "failures": sum(failures.values())}, sort_keys=True))
    return 0 if output["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
