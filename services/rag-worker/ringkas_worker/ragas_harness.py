from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ringkas_worker.evaluation_dataset import DATASET_CAPACITY_EXPANDED, DATASET_PATH, EvaluationDataset, load_dataset


DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "evaluation_sample_responses.json"
DEFAULT_MODEL = "@cf/openai/gpt-oss-120b"
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"
DEFAULT_EVALUATOR_PROVIDER = "cloudflare"
DEFAULT_DEEPSEEK_REASONING_EFFORT = "high"
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
class DeepSeekTarget:
    api_key: str
    base_url: str


@dataclass(frozen=True)
class LiveConfig:
    evaluator_provider: str
    model: str
    base_url: str
    reasoning_effort: str | None
    timeout_seconds: int
    max_retries: int
    max_workers: int
    preflight_samples: int
    max_tokens: int
    temperature: float
    accounts: tuple[CloudflareAccount, ...]
    deepseek_target: DeepSeekTarget | None = None

    def fingerprint(self, ragas_version: str) -> dict[str, Any]:
        return {
            "execution_architecture": "supervised_subprocess_metric_v1",
            "model": self.model,
            "provider": self.evaluator_provider,
            # Do not persist endpoint details, which may include a private gateway URL.
            "base_url": "sha256:" + hashlib.sha256(self.base_url.encode("utf-8")).hexdigest(),
            "reasoning_effort": self.reasoning_effort,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_workers": self.max_workers,
            "ragas_version": ragas_version,
            "temperature": self.temperature,
        }


@dataclass(frozen=True)
class MetricProcessConfig:
    evaluator_provider: str
    model: str
    timeout_seconds: int
    max_tokens: int
    temperature: float
    reasoning_effort: str | None


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
    evaluator_provider = os.getenv("RAGAS_EVALUATOR_PROVIDER", DEFAULT_EVALUATOR_PROVIDER).strip()
    if evaluator_provider not in {"cloudflare", "deepseek"}:
        raise ValueError("RAGAS_EVALUATOR_PROVIDER must be cloudflare or deepseek")
    common = {
        "timeout_seconds": _positive_env("RAGAS_LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        "max_retries": _positive_env("RAGAS_LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES),
        "max_workers": _positive_env("RAGAS_LLM_MAX_WORKERS", DEFAULT_MAX_WORKERS),
        "preflight_samples": _positive_env("RAGAS_LLM_PREFLIGHT_SAMPLES", DEFAULT_PREFLIGHT_SAMPLES),
        "max_tokens": _positive_env("RAGAS_LLM_MAX_TOKENS"),
        "temperature": _positive_float_env("RAGAS_LLM_TEMPERATURE", DEFAULT_TEMPERATURE),
    }
    if evaluator_provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        base_url = os.getenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
        reasoning_effort = os.getenv(
            "RAGAS_DEEPSEEK_REASONING_EFFORT", DEFAULT_DEEPSEEK_REASONING_EFFORT
        ).strip()
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for the DeepSeek RAGAS evaluator")
        if not base_url:
            raise ValueError("DEEPSEEK_API_BASE_URL must be non-empty for the DeepSeek RAGAS evaluator")
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("RAGAS_DEEPSEEK_REASONING_EFFORT must be low, medium, or high")
        config = LiveConfig(
            evaluator_provider=evaluator_provider,
            model=os.getenv("DEEPSEEK_RAGAS_MODEL", DEFAULT_DEEPSEEK_MODEL).strip(),
            base_url=base_url,
            reasoning_effort=reasoning_effort,
            accounts=(),
            deepseek_target=DeepSeekTarget(api_key, base_url),
            **common,
        )
    else:
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
        config = LiveConfig(
            evaluator_provider=evaluator_provider,
            model=os.getenv("RAGAS_LLM_MODEL", DEFAULT_MODEL).strip(),
            base_url="https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
            reasoning_effort=None,
            accounts=tuple(accounts),
            **common,
        )
    if config.max_workers != 1:
        raise ValueError("RAGAS_LLM_MAX_WORKERS must be 1 for supervised metric execution")
    if config.preflight_samples != DEFAULT_PREFLIGHT_SAMPLES:
        raise ValueError(f"RAGAS_LLM_PREFLIGHT_SAMPLES must be {DEFAULT_PREFLIGHT_SAMPLES}")
    return config


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


def _finite_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _validated_partial_metrics(value: Any, selected_ids: set[str]) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        raise ValueError("RAGAS checkpoint contains invalid partial metrics.")
    partial: dict[str, dict[str, float]] = {}
    for question_id, metrics in value.items():
        if question_id not in selected_ids or not isinstance(metrics, dict):
            raise ValueError("RAGAS checkpoint contains invalid partial metrics.")
        if not set(metrics).issubset(METRIC_NAMES):
            raise ValueError("RAGAS checkpoint contains invalid partial metrics.")
        partial[question_id] = {}
        for metric_name, metric_value in metrics.items():
            if not _finite_value(metric_value):
                raise ValueError("RAGAS checkpoint contains incomplete or non-finite metrics.")
            partial[question_id][metric_name] = float(metric_value)
    return partial


def _finite_metric_count(partial: dict[str, dict[str, float]]) -> int:
    return sum(len(metrics) for metrics in partial.values())


def _complete_rows(partial: dict[str, dict[str, float]], question_ids: list[str]) -> list[dict[str, Any]]:
    return [
        {"question_id": question_id, **partial[question_id]}
        for question_id in question_ids
        if question_id in partial and set(partial[question_id]) == set(METRIC_NAMES)
    ]


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    if isinstance(value, int):
        return value
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value
    if error.__cause__ is not None and isinstance(error.__cause__, Exception):
        return _status_code(error.__cause__)
    return None


def _retryable_account_error(error: Exception) -> bool:
    status = _status_code(error)
    if status is not None:
        return status in {401, 403, 408, 429} or 500 <= status <= 599
    names = {
        "APIConnectionError",
        "APITimeoutError",
        "RequestError",
        "RateLimitError",
        "InstructorRetryException",
    }
    if error.__class__.__name__ in names:
        return True
    if error.__cause__ is not None and error.__cause__.__class__.__name__ in names:
        return True
    return isinstance(error, (httpx.RequestError, TimeoutError, ConnectionError, OSError))


def _cloudflare_base_url(account_id: str) -> str:
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"


def _report_provider(config: LiveConfig) -> str:
    return "cloudflare_workers_ai_openai_compatible" if config.evaluator_provider == "cloudflare" else "deepseek_openai_compatible"


def _evaluate_one_metric(
    sample: dict[str, Any], metric_name: str, config: MetricProcessConfig, target: CloudflareAccount | DeepSeekTarget
) -> float:
    OpenAI, RagasEvaluationDataset, evaluate, llm_factory, metrics, RunConfig = _load_ragas_components()
    client = OpenAI(
        api_key=target.api_token if isinstance(target, CloudflareAccount) else target.api_key,
        base_url=_cloudflare_base_url(target.account_id) if isinstance(target, CloudflareAccount) else target.base_url,
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    try:
        llm_arguments: dict[str, Any] = {
            "provider": "openai",
            "client": client,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        if config.reasoning_effort is not None:
            llm_arguments["reasoning_effort"] = config.reasoning_effort
        evaluator_llm = llm_factory(
            config.model,
            **llm_arguments,
        )
        result = evaluate(
            dataset=RagasEvaluationDataset.from_list([sample]),
            metrics=[metrics[metric_name]],
            llm=evaluator_llm,
            run_config=RunConfig(
                # One Ragas attempt; parent-owned retries control account sequencing.
                max_retries=1,
                max_workers=1,
            ),
            raise_exceptions=True,
            show_progress=False,
        )
        rows = result.to_pandas().to_dict(orient="records")
        if len(rows) != 1:
            raise ValueError("RAGAS metric result count was invalid")
        return float(rows[0][metric_name])
    finally:
        client.close()


@dataclass(frozen=True)
class MetricAttempt:
    value: float | None = None
    failure: str | None = None


def _terminate_process_group(process: Any) -> None:
    """Stop the worker and anything it started without exposing its output."""
    killpg = getattr(os, "killpg", None)
    sigterm = getattr(signal, "SIGTERM", 15)
    sigkill = getattr(signal, "SIGKILL", 9)
    try:
        if killpg is not None:
            killpg(process.pid, sigterm)
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=1)
        return
    except (subprocess.TimeoutExpired, OSError):
        pass
    try:
        if killpg is not None:
            killpg(process.pid, sigkill)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=1)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _secure_json_file(directory: Path, payload: dict[str, Any]) -> Path:
    descriptor, name = tempfile.mkstemp(dir=directory, prefix="ragas-metric-", suffix=".json")
    path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
    except Exception:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _secure_empty_file(directory: Path) -> Path:
    descriptor, name = tempfile.mkstemp(dir=directory, prefix="ragas-result-", suffix=".json")
    os.fchmod(descriptor, 0o600)
    os.close(descriptor)
    return Path(name)


def _read_metric_result(path: Path) -> MetricAttempt:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return MetricAttempt(failure="process")
    if not isinstance(payload, dict):
        return MetricAttempt(failure="process")
    if payload.get("status") == "ok" and set(payload) == {"status", "value"} and _finite_value(payload.get("value")):
        return MetricAttempt(value=float(payload["value"]))
    if payload.get("status") in {"retryable", "nonretryable"} and set(payload) == {"status"}:
        return MetricAttempt(failure=payload["status"])
    return MetricAttempt(failure="nonfinite")


def _run_metric_attempt(
    sample: dict[str, Any],
    metric_name: str,
    config: LiveConfig,
    target: CloudflareAccount | DeepSeekTarget,
    *,
    subprocess_runner: Any = subprocess.Popen,
    ipc_directory: Path,
) -> MetricAttempt:
    process_config = MetricProcessConfig(
        evaluator_provider=config.evaluator_provider,
        model=config.model,
        timeout_seconds=config.timeout_seconds,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        reasoning_effort=config.reasoning_effort,
    )
    checkpoint_directory = Path(tempfile.mkdtemp(prefix="ragas-worker-", dir=ipc_directory))
    try:
        input_path = _secure_json_file(
            checkpoint_directory,
            {
                "sample": sample,
                "metric_name": metric_name,
                "config": {
                    "evaluator_provider": process_config.evaluator_provider,
                    "model": process_config.model,
                    "timeout_seconds": process_config.timeout_seconds,
                    "max_tokens": process_config.max_tokens,
                    "temperature": process_config.temperature,
                    "reasoning_effort": process_config.reasoning_effort,
                },
            },
        )
        output_path = _secure_empty_file(checkpoint_directory)
        environment = {"PATH": os.environ.get("PATH", "")}
        for var in ("SYSTEMROOT", "SystemRoot", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE"):
            if var in os.environ:
                environment[var] = os.environ[var]
        if isinstance(target, CloudflareAccount):
            environment.update({"RINGKAS_RAGAS_ACCOUNT_ID": target.account_id, "RINGKAS_RAGAS_API_TOKEN": target.api_token})
        else:
            environment.update({"RINGKAS_RAGAS_DEEPSEEK_API_KEY": target.api_key, "RINGKAS_RAGAS_DEEPSEEK_BASE_URL": target.base_url})
        command = [sys.executable, "-m", "ringkas_worker.ragas_metric_worker", str(input_path), str(output_path)]
        try:
            process = subprocess_runner(
                command,
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            return MetricAttempt(failure="process")
        try:
            return_code = process.wait(timeout=config.timeout_seconds)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            return MetricAttempt(failure="timeout")
        except Exception:
            _terminate_process_group(process)
            return MetricAttempt(failure="process")
        if return_code != 0:
            return MetricAttempt(failure="process")
        return _read_metric_result(output_path)
    finally:
        for path in checkpoint_directory.iterdir():
            path.unlink(missing_ok=True)
        checkpoint_directory.rmdir()


def _evaluate_metric_with_failover(
    sample: dict[str, Any],
    metric_name: str,
    config: LiveConfig,
    attempt_runner: Any,
) -> MetricAttempt:
    targets: tuple[CloudflareAccount | DeepSeekTarget, ...] = config.accounts or ((config.deepseek_target,) if config.deepseek_target else ())
    for account in targets:
        for _ in range(config.max_retries):
            result = attempt_runner(sample, metric_name, config, account)
            if result.value is not None and _finite_value(result.value):
                return result
            if result.failure == "nonretryable":
                return result
    return MetricAttempt(failure="accounts_exhausted")


def _ragas_version() -> str:
    try:
        from importlib.metadata import version

        return version("ragas")
    except Exception:
        return "unknown"


def run_live(
    dataset_path: Path,
    responses_path: Path,
    checkpoint_path: Path | None = None,
    *,
    preflight_only: bool = False,
    attempt_runner: Any = _run_metric_attempt,
) -> dict[str, Any]:
    try:
        dataset = load_dataset(dataset_path)
        responses = _load_responses(responses_path)
        _validate_links(dataset, responses)
        if dataset.dataset_status != "ready" or dataset.capacity != DATASET_CAPACITY_EXPANDED:
            return _blocked("The evaluation dataset is not a ready 1000-record verified dataset.")
        config = _live_config()
        if not config.model:
            return _blocked("RAGAS evaluator model must be non-empty.")
        samples = _stratified_samples(dataset, responses)
    except ValueError as error:
        return _blocked(str(error))
    except (OSError, json.JSONDecodeError):
        return _blocked("Evaluation inputs are unreadable.")

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

    try:
        partial = _validated_partial_metrics(checkpoint.get("partial_metrics", {}), set(selected_ids)) if checkpoint else {}
    except ValueError as error:
        return _blocked(str(error), 0)
    use_subprocess_worker = attempt_runner is _run_metric_attempt
    if use_subprocess_worker and not _ragas_available():
        return _blocked("Optional RAGAS evaluation dependencies are unavailable.", _finite_metric_count(partial))
    if use_subprocess_worker:
        def execute_attempt(sample: dict[str, Any], metric_name: str, live_config: LiveConfig, account: CloudflareAccount | DeepSeekTarget) -> MetricAttempt:
            return _run_metric_attempt(
                sample,
                metric_name,
                live_config,
                account,
                ipc_directory=checkpoint_path.parent,
            )
    else:
        execute_attempt = attempt_runner
    preflight_ids = selected_ids[: config.preflight_samples]
    preflight_complete = all(
        set(partial.get(question_id, {})) == set(METRIC_NAMES) for question_id in preflight_ids
    )
    state = {
        "fingerprint": fingerprint,
        "selected_sample_ids": selected_ids,
        "selected_sample_ids_hash": selected_hash,
        "partial_metrics": partial,
        "preflight_complete": preflight_complete,
    }

    if not preflight_complete:
        for sample in samples[: config.preflight_samples]:
            question_metrics = partial.setdefault(sample["question_id"], {})
            for metric_name in METRIC_NAMES:
                if metric_name in question_metrics:
                    continue
                result = _evaluate_metric_with_failover(sample, metric_name, config, execute_attempt)
                if result.value is None or not _finite_value(result.value):
                    return _blocked("RAGAS evaluator preflight failed.", _finite_metric_count(partial))
                question_metrics[metric_name] = float(result.value)
                _write_checkpoint(checkpoint_path, state)
        state["preflight_complete"] = True
        _write_checkpoint(checkpoint_path, state)

    if preflight_only:
        rows = _complete_rows(partial, preflight_ids)
        if len(rows) != config.preflight_samples or _finite_metric_count(partial) < config.preflight_samples * len(METRIC_NAMES):
            return _blocked("RAGAS evaluator preflight failed.", _finite_metric_count(partial))
        return {
            "evaluation_label": LIVE_LABEL,
            "status": "preflight_validated",
            "sample_count": len(rows),
            "metric_count": config.preflight_samples * len(METRIC_NAMES),
            "resumed": resumed,
            "evaluator": {
                "model": config.model,
                "provider": _report_provider(config),
                "account_count": len(config.accounts),
                "timeout_seconds": config.timeout_seconds,
                "max_retries": config.max_retries,
                "max_workers": config.max_workers,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
                "reasoning_effort": config.reasoning_effort,
            },
            "selected_sample_ids_hash": selected_hash,
            "metrics": sorted(rows, key=lambda row: row["question_id"]),
        }

    for sample in samples[config.preflight_samples :]:
        question_metrics = partial.setdefault(sample["question_id"], {})
        for metric_name in METRIC_NAMES:
            if metric_name in question_metrics:
                continue
            result = _evaluate_metric_with_failover(sample, metric_name, config, execute_attempt)
            if result.value is None or not _finite_value(result.value):
                return _blocked("RAGAS evaluator failed.", _finite_metric_count(partial))
            question_metrics[metric_name] = float(result.value)
            _write_checkpoint(checkpoint_path, state)

    rows = _complete_rows(partial, selected_ids)
    if len(rows) != 100 or _finite_metric_count(partial) != 100 * len(METRIC_NAMES):
        return _blocked("RAGAS baseline metrics are incomplete or non-finite.", _finite_metric_count(partial))
    return {
        "evaluation_label": BASELINE_LABEL,
        "status": "completed",
        "external_services": "Cloudflare Workers AI OpenAI-compatible evaluator"
        if config.evaluator_provider == "cloudflare"
        else "DeepSeek OpenAI-compatible evaluator",
        "sample_count": len(samples),
        "resumed": resumed,
        "evaluator": {
            "model": config.model,
            "provider": _report_provider(config),
            "account_count": len(config.accounts),
            "timeout_seconds": config.timeout_seconds,
            "max_retries": config.max_retries,
            "max_workers": config.max_workers,
            "preflight_samples": config.preflight_samples,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "reasoning_effort": config.reasoning_effort,
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
    from ragas.metrics._context_precision import context_precision
    from ragas.metrics._context_recall import context_recall
    from ragas.metrics._faithfulness import faithfulness
    from ragas.run_config import RunConfig

    metrics = {
        "faithfulness": faithfulness,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    return OpenAI, RagasEvaluationDataset, evaluate, llm_factory, metrics, RunConfig


def _ragas_available() -> bool:
    return importlib.util.find_spec("ragas") is not None and importlib.util.find_spec("openai") is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RINGKAS RAGAS evaluation harness")
    parser.add_argument("--mode", choices=("sample", "live"), default="sample")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--responses", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args(argv)
    result = run_sample(args.dataset, args.responses) if args.mode == "sample" else run_live(
        args.dataset,
        args.responses,
        args.checkpoint,
        preflight_only=args.preflight_only,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["status"] in {"fixture_validated", "preflight_validated", "completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
