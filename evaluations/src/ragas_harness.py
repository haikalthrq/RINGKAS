from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ringkas_worker.evaluation_dataset import DATASET_PATH, EvaluationDataset, load_dataset


DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "evaluation_sample_responses.json"
BASELINE_LABEL = "initial MVP baseline"
FIXTURE_LABEL = "deterministic harness validation"
LIVE_LABEL = "live RAGAS evaluation"


def _load_responses(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("response fixture must contain a non-empty records array")
    required = {"question_id", "user_input", "response", "reference", "retrieved_contexts"}
    for record in records:
        if not isinstance(record, dict) or not required.issubset(record):
            raise ValueError("each response fixture record must contain the RAGAS fields")
        if not isinstance(record["retrieved_contexts"], list):
            raise ValueError("retrieved_contexts must be a list")
    return records


def _validate_links(dataset: EvaluationDataset, responses: list[dict[str, Any]]) -> None:
    ids = {record.question_id for record in dataset.records}
    response_ids = [record["question_id"] for record in responses]
    if len(response_ids) != len(set(response_ids)) or not set(response_ids).issubset(ids):
        raise ValueError("response fixture question IDs must uniquely link to the evaluation dataset")


def run_sample(dataset_path: Path = DATASET_PATH, responses_path: Path = DEFAULT_FIXTURE_PATH) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    responses = _load_responses(responses_path)
    _validate_links(dataset, responses)
    return {
        "evaluation_label": FIXTURE_LABEL,
        "status": "fixture_validated",
        "external_services": "none",
        "dataset_capacity": dataset.capacity,
        "response_fixture_count": len(responses),
        "metrics": None,
        "limitations": [
            "This deterministic synthetic fixture does not produce RAGAS scores.",
            "A baseline requires a completed live RAGAS evaluation.",
        ],
    }


def run_live(dataset_path: Path, responses_path: Path) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    responses = _load_responses(responses_path)
    _validate_links(dataset, responses)
    if dataset.dataset_status != "ready":
        return {
            "evaluation_label": LIVE_LABEL,
            "status": "blocked",
            "reason": "The evaluation dataset is not ready and fully verified.",
            "metrics": None,
        }
    verified_ids = {record.question_id for record in dataset.records if record.verification_status == "verified"}
    samples = [record for record in responses if record["question_id"] in verified_ids]
    if not samples:
        return {
            "evaluation_label": LIVE_LABEL,
            "status": "blocked",
            "reason": "No linked evaluation records are marked verified.",
            "metrics": None,
        }

    api_key = os.getenv("RAGAS_LLM_API_KEY", "")
    model = os.getenv("RAGAS_LLM_MODEL", "")
    base_url = os.getenv("RAGAS_LLM_BASE_URL", "")
    provider = os.getenv("RAGAS_LLM_PROVIDER", "")
    if not all(value.strip() for value in (api_key, model, base_url, provider)):
        return {
            "evaluation_label": LIVE_LABEL,
            "status": "blocked",
            "reason": "RAGAS_LLM_API_KEY, RAGAS_LLM_MODEL, RAGAS_LLM_BASE_URL, and RAGAS_LLM_PROVIDER are required for live evaluation.",
            "metrics": None,
        }

    try:
        OpenAI, RagasEvaluationDataset, evaluate, llm_factory, Faithfulness, ContextPrecision, ContextRecall = (
            _load_ragas_components()
        )
    except ImportError as error:
        return {
            "evaluation_label": LIVE_LABEL,
            "status": "blocked",
            "reason": f"Optional RAGAS evaluation dependencies are unavailable: {error.__class__.__name__}.",
            "metrics": None,
        }

    client = OpenAI(api_key=api_key, base_url=base_url)
    evaluator_llm = llm_factory(model, provider=provider, client=client)
    ragas_dataset = RagasEvaluationDataset.from_list(samples)
    result = evaluate(
        dataset=ragas_dataset,
        metrics=[
            Faithfulness(llm=evaluator_llm),
            ContextPrecision(llm=evaluator_llm),
            ContextRecall(llm=evaluator_llm),
        ],
        llm=evaluator_llm,
    )
    return {
        "evaluation_label": BASELINE_LABEL,
        "status": "completed",
        "external_services": "live evaluator",
        "sample_count": len(samples),
        "metrics": result.to_pandas().to_dict(orient="records"),
        "limitations": ["Automated metrics are baseline-only and do not prove comprehensive accuracy."],
    }


def _load_ragas_components() -> tuple[Any, ...]:
    from openai import OpenAI
    from ragas import EvaluationDataset as RagasEvaluationDataset, evaluate
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness

    return OpenAI, RagasEvaluationDataset, evaluate, llm_factory, Faithfulness, ContextPrecision, ContextRecall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RINGKAS RAGAS evaluation harness")
    parser.add_argument("--mode", choices=("sample", "live"), default="sample")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--responses", type=Path, default=DEFAULT_FIXTURE_PATH)
    args = parser.parse_args(argv)
    result = run_sample(args.dataset, args.responses) if args.mode == "sample" else run_live(args.dataset, args.responses)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] in {"fixture_validated", "completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
