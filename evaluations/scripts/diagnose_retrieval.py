import json
import os
from pathlib import Path

from ringkas_worker.query_service import QueryEngine


DATASET_PATH = Path(os.getenv("EVALUATION_DATASET", "/evaluation/evaluation_dataset.json"))
OUTPUT_PATH = Path(os.getenv("RETRIEVAL_DIAGNOSTIC", "/evaluation/retrieval_diagnostic.json"))
CHECKPOINT_PATH = Path(os.getenv("RETRIEVAL_DIAGNOSTIC_CHECKPOINT", "/evaluation/retrieval_diagnostic_checkpoint.json"))
LIMIT = int(os.getenv("EVALUATION_LIMIT", "0"))


def rank(candidates: object, expected_chunk_id: str) -> int | None:
    for candidate in candidates:
        if candidate.chunk_id == expected_chunk_id:
            return candidate.rank
    return None


def main() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    records = dataset["records"]
    if LIMIT > 0:
        records = records[:LIMIT]
    results: list[dict[str, object]] = []
    if CHECKPOINT_PATH.exists():
        results = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))["results"]
        print(f"resuming from {len(results)}/{len(records)}", flush=True)

    engine = QueryEngine.from_environment()
    try:
        for index, record in enumerate(records[len(results) :], start=len(results) + 1):
            expected_chunk_id = record["evidence"]["chunk_id"]
            try:
                dense = engine._dense.retrieve(record["question_text"])
                sparse = engine._sparse.retrieve(engine._sparse_encoder.encode_query(record["question_text"]))
                fused = engine._fusion.fuse(dense, sparse)
                results.append(
                    {
                        "question_id": record["question_id"],
                        "question_type": record["question_type"],
                        "document_id": record["evidence"]["document_id"],
                        "expected_chunk_id": expected_chunk_id,
                        "dense_rank": rank(dense.candidates, expected_chunk_id),
                        "sparse_rank": rank(sparse.candidates, expected_chunk_id),
                        "rrf_rank": rank(fused.candidates, expected_chunk_id),
                        "dense_count": len(dense.candidates),
                        "sparse_count": len(sparse.candidates),
                        "rrf_count": len(fused.candidates),
                        "error": None,
                    }
                )
            except Exception as error:
                results.append(
                    {
                        "question_id": record["question_id"],
                        "question_type": record["question_type"],
                        "document_id": record["evidence"]["document_id"],
                        "expected_chunk_id": expected_chunk_id,
                        "dense_rank": None,
                        "sparse_rank": None,
                        "rrf_rank": None,
                        "dense_count": 0,
                        "sparse_count": 0,
                        "rrf_count": 0,
                        "error": type(error).__name__,
                    }
                )
            if index % 10 == 0:
                CHECKPOINT_PATH.write_text(json.dumps({"results": results}, ensure_ascii=False), encoding="utf-8")
                print(f"checkpoint {index}/{len(records)}", flush=True)

        payload = {"dataset_capacity": len(records), "results": results}
        OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"completed {len(results)}/{len(records)}", flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
