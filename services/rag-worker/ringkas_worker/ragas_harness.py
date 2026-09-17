from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ringkas_worker.evaluation_dataset import DATASET_CAPACITY_EXPANDED, DATASET_PATH, EvaluationDataset, load_dataset


DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "evaluation_sample_responses.json"
DEFAULT_MODEL = "@cf/openai/gpt-oss-120b"
DEFAULT_BATCH_SIZE = 25
DEFAULT_PREFLIGHT_SAMPLES = 20
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_WORKERS = 1
DEFAULT_TEMPERATURE = 0.1
BASELINE_LABEL = "initial MVP baseline"
FIXTURE_LABEL = "deterministic harness validation"
LIVE_LABEL = "live RAGAS evaluation"
METRIC_NAMES = ("faithfulness", "context_precision", "context_recall")


@dataclass(frozen=True)
class CloudflareAccount:
    account_id: str
    api_token: str


@dataclass(frozen=True)
class LiveConfig:
    model: str
    timeout_seconds: int
    max_retries: int
    max_workers: int
    batch_size: int
    preflight_samples: int
    max_tokens: int
    temperature: float
    accounts: tuple[CloudflareAccount, ...]

    def fingerprint(self, ragas_version: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": "cloudflare_workers_ai_openai_compatible",
            "output_cap": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_workers": self.max_workers,
            "batch_size": self.batch_size,
            "ragas_version": ragas_version,
            "temperature": self.temperature,
        }


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


def _positive_env(name: str, default: int | None = None) -> int:
    raw = os.getenv(name, str(default) if default is not None else "").strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number") from error
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number")
    return value


def _live_config() -> LiveConfig:
    accounts: list[CloudflareAccount] = []
    for suffix in ("", "_SECONDARY", "_TERTIARY"):
        account_id = os.getenv(f"CLOUDFLARE{suffix}_ACCOUNT_ID", "").strip()
        api_token = os.getenv(f"CLOUDFLARE{suffix}_API_TOKEN", "").strip()
        if bool(account_id) != bool(api_token):
            raise ValueError("Cloudflare account failover credentials must be configured as complete pairs")
        if account_id:
            accounts.append(CloudflareAccount(account_id, api_token))
    if not accounts:
        raise ValueError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required")
    return LiveConfig(
        model=os.getenv("RAGAS_LLM_MODEL", DEFAULT_MODEL).strip(),
        timeout_seconds=_positive_env("RAGAS_LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        max_retries=_positive_env("RAGAS_LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES),
        max_workers=_positive_env("RAGAS_LLM_MAX_WORKERS", DEFAULT_MAX_WORKERS),
        batch_size=_positive_env("RAGAS_LLM_BATCH_SIZE", DEFAULT_BATCH_SIZE),
        preflight_samples=_positive_env("RAGAS_LLM_PREFLIGHT_SAMPLES", DEFAULT_PREFLIGHT_SAMPLES),
        max_tokens=_positive_env("RAGAS_LLM_MAX_TOKENS"),
        temperature=_positive_float_env("RAGAS_LLM_TEMPERATURE", DEFAULT_TEMPERATURE),
        accounts=tuple(accounts),
    )


def _stratified_samples(dataset: EvaluationDataset, responses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    response_by_id = {record["question_id"]: record for record in responses}
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in dataset.records:
        if record.verification_status == "verified" and record.question_id in response_by_id:
            groups.setdefault(record.question_type, []).append(response_by_id[record.question_id])
    if sum(len(group) for group in groups.values()) != DATASET_CAPACITY_EXPANDED:
        raise ValueError("A live RAGAS baseline requires 1000 linked verified responses")

    # Stable hash ordering keeps the representative 100 independent of input file order.
    for group in groups.values():
        group.sort(key=lambda record: hashlib.sha256(record["question_id"].encode("utf-8")).hexdigest())
    quotas = {question_type: min(len(group), 100 // len(groups)) for question_type, group in groups.items()}
    remaining = 100 - sum(quotas.values())
    while remaining:
        progressed = False
        for question_type in sorted(groups):
            if remaining and quotas[question_type] < len(groups[question_type]):
                quotas[question_type] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            raise ValueError("Not enough verified responses for a 100-record RAGAS baseline")
    selected = [record for question_type in sorted(groups) for record in groups[question_type][:quotas[question_type]]]
    return sorted(selected, key=lambda record: record["question_id"])


def _selected_ids_hash(samples: list[dict[str, Any]]) -> tuple[list[str], str]:
    ids = [sample["question_id"] for sample in samples]
    encoded = json.dumps(ids, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return ids, hashlib.sha256(encoded).hexdigest()


def _blocked(reason: str, count: int = 0) -> dict[str, Any]:
    return {"status": "blocked", "reason": reason, "count": count}


def _checkpoint_path(responses_path: Path) -> Path:
    return responses_path.with_suffix(".ragas_checkpoint.json")


def _read_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("RAGAS checkpoint is unreadable") from error
    if not isinstance(payload, dict):
        raise ValueError("RAGAS checkpoint is invalid")
    return payload


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
        json.dump(payload, output, ensure_ascii=True, sort_keys=True, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
        temporary_name = output.name
    os.replace(temporary_name, path)


def _finite_metrics(rows: list[dict[str, Any]], expected_ids: set[str]) -> bool:
    if len(rows) != len(expected_ids):
        return False
    found_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("question_id"), str):
            return False
        found_ids.add(row["question_id"])
        for metric in METRIC_NAMES:
            value = row.get(metric)
            if isinstance(value, bool):
                return False
            try:
                if not math.isfinite(float(value)):
                    return False
            except (TypeError, ValueError):
                return False
    return found_ids == expected_ids


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _retryable_account_error(error: Exception) -> bool:
    status = _status_code(error)
    if status is not None:
        return status in {401, 403, 408, 429} or 500 <= status <= 599
    return isinstance(error, (httpx.RequestError, TimeoutError, ConnectionError, OSError)) or error.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "RequestError",
    }


def _cloudflare_base_url(account_id: str) -> str:
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"


def _evaluate_batch(
    components: tuple[Any, ...], samples: list[dict[str, Any]], config: LiveConfig, account: CloudflareAccount
) -> list[dict[str, Any]]:
    OpenAI, RagasEvaluationDataset, evaluate, llm_factory, Faithfulness, ContextPrecision, ContextRecall, RunConfig = components
    # The client timeout cancels the HTTP request itself; RunConfig is retained for RAGAS scheduling.
    client = OpenAI(api_key=account.api_token, base_url=_cloudflare_base_url(account.account_id), timeout=config.timeout_seconds, max_retries=0)
    try:
        evaluator_llm = llm_factory(
            config.model,
            provider="openai",
            client=client,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        result = evaluate(
            dataset=RagasEvaluationDataset.from_list(samples),
            metrics=[Faithfulness(llm=evaluator_llm), ContextPrecision(llm=evaluator_llm), ContextRecall(llm=evaluator_llm)],
            llm=evaluator_llm,
            run_config=RunConfig(
                timeout=config.timeout_seconds,
                max_retries=config.max_retries,
                max_workers=config.max_workers,
            ),
        )
        rows = result.to_pandas().to_dict(orient="records")
        for sample, row in zip(samples, rows, strict=True):
            row["question_id"] = sample["question_id"]
        return rows
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _evaluate_with_failover(
    components: tuple[Any, ...], samples: list[dict[str, Any]], config: LiveConfig
) -> list[dict[str, Any]]:
    expected_ids = {sample["question_id"] for sample in samples}
    for account in config.accounts:
        for _ in range(config.max_retries):
            try:
                rows = _evaluate_batch(components, samples, config, account)
            except Exception as error:
                if not _retryable_account_error(error):
                    raise
                continue
            if _finite_metrics(rows, expected_ids):
                return rows
    raise RuntimeError("all Cloudflare evaluator accounts failed")


def _ragas_version() -> str:
    try:
        from importlib.metadata import version

        return version("ragas")
    except Exception:
        return "unknown"


def run_live(dataset_path: Path, responses_path: Path, checkpoint_path: Path | None = None) -> dict[str, Any]:
    try:
        dataset = load_dataset(dataset_path)
        responses = _load_responses(responses_path)
        _validate_links(dataset, responses)
        if dataset.dataset_status != "ready" or dataset.capacity != DATASET_CAPACITY_EXPANDED:
            return _blocked("The evaluation dataset is not a ready 1000-record verified dataset.")
        config = _live_config()
        if not config.model:
            return _blocked("RAGAS_LLM_MODEL must be non-empty.")
        samples = _stratified_samples(dataset, responses)
    except ValueError as error:
        return _blocked(str(error))
    except (OSError, json.JSONDecodeError):
        return _blocked("Evaluation inputs are unreadable.")

    try:
        components = _load_ragas_components()
    except ImportError:
        return _blocked("Optional RAGAS evaluation dependencies are unavailable.", len(samples))

    selected_ids, selected_hash = _selected_ids_hash(samples)
    fingerprint = config.fingerprint(_ragas_version())
    checkpoint_path = checkpoint_path or _checkpoint_path(responses_path)
    try:
        checkpoint = _read_checkpoint(checkpoint_path)
    except ValueError as error:
        return _blocked(str(error), len(samples))
    resumed = checkpoint is not None
    if checkpoint is not None and (
        checkpoint.get("fingerprint") != fingerprint
        or checkpoint.get("selected_sample_ids") != selected_ids
        or checkpoint.get("selected_sample_ids_hash") != selected_hash
    ):
        return _blocked("RAGAS checkpoint fingerprint does not match this baseline.", len(samples))

    rows = list(checkpoint.get("metrics", [])) if checkpoint else []
    if not _finite_metrics(rows, {row["question_id"] for row in rows}):
        return _blocked("RAGAS checkpoint contains incomplete or non-finite metrics.", len(samples))
    completed_ids = {row["question_id"] for row in rows}
    state = {
        "fingerprint": fingerprint,
        "selected_sample_ids": selected_ids,
        "selected_sample_ids_hash": selected_hash,
        "metrics": rows,
        "preflight_complete": bool(checkpoint and checkpoint.get("preflight_complete")),
    }

    if not state["preflight_complete"]:
        for sample in samples[: config.preflight_samples]:
            if sample["question_id"] in completed_ids:
                continue
            try:
                batch_rows = _evaluate_with_failover(components, [sample], config)
            except Exception:
                return _blocked("RAGAS evaluator preflight failed.", len(rows))
            if not _finite_metrics(batch_rows, {sample["question_id"]}):
                return _blocked("RAGAS evaluator preflight returned incomplete or non-finite metrics.", len(rows))
            rows.extend(batch_rows)
            completed_ids.add(sample["question_id"])
        state["metrics"] = rows
        state["preflight_complete"] = True
        _write_checkpoint(checkpoint_path, state)

    pending = [sample for sample in samples if sample["question_id"] not in completed_ids]
    for start in range(0, len(pending), config.batch_size):
        batch = pending[start : start + config.batch_size]
        try:
            batch_rows = _evaluate_with_failover(components, batch, config)
        except Exception:
            return _blocked("RAGAS evaluator batch failed.", len(rows))
        if not _finite_metrics(batch_rows, {sample["question_id"] for sample in batch}):
            return _blocked("RAGAS evaluator returned incomplete or non-finite metrics.", len(rows))
        rows.extend(batch_rows)
        completed_ids.update(row["question_id"] for row in batch_rows)
        state["metrics"] = rows
        _write_checkpoint(checkpoint_path, state)

    if not _finite_metrics(rows, set(selected_ids)):
        return _blocked("RAGAS baseline metrics are incomplete or non-finite.", len(rows))
    return {
        "evaluation_label": BASELINE_LABEL,
        "status": "completed",
        "external_services": "Cloudflare Workers AI OpenAI-compatible evaluator",
        "sample_count": len(samples),
        "resumed": resumed,
        "evaluator": {
            "model": config.model,
            "provider": "cloudflare_workers_ai_openai_compatible",
            "account_count": len(config.accounts),
            "timeout_seconds": config.timeout_seconds,
            "max_retries": config.max_retries,
            "max_workers": config.max_workers,
            "batch_size": config.batch_size,
            "preflight_samples": config.preflight_samples,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "ragas_version": fingerprint["ragas_version"],
        },
        "selected_sample_ids": selected_ids,
        "selected_sample_ids_hash": selected_hash,
        "metrics": sorted(rows, key=lambda row: row["question_id"]),
        "limitations": ["Automated metrics are baseline-only and do not prove comprehensive accuracy."],
    }


def _load_ragas_components() -> tuple[Any, ...]:
    from openai import OpenAI
    from ragas import EvaluationDataset as RagasEvaluationDataset, evaluate
    from ragas.llms import llm_factory
    from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness
    from ragas.run_config import RunConfig

    return OpenAI, RagasEvaluationDataset, evaluate, llm_factory, Faithfulness, ContextPrecision, ContextRecall, RunConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RINGKAS RAGAS evaluation harness")
    parser.add_argument("--mode", choices=("sample", "live"), default="sample")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--responses", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args(argv)
    result = run_sample(args.dataset, args.responses) if args.mode == "sample" else run_live(args.dataset, args.responses, args.checkpoint)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] in {"fixture_validated", "completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
