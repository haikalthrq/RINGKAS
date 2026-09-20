from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from ringkas_worker.ragas_harness import (
    CloudflareAccount,
    METRIC_NAMES,
    MetricProcessConfig,
    _evaluate_one_metric,
    _retryable_account_error,
)


def _finite_value(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def _write_result(path: Path, payload: dict[str, Any]) -> None:
    # The parent pre-creates this 0600 file in its private IPC directory.
    with path.open("w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        output.flush()
        os.fsync(output.fileno())


def run(input_path: Path, output_path: Path) -> int:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"sample", "metric_name", "config"}:
            raise ValueError
        metric_name = payload["metric_name"]
        config_data = payload["config"]
        if metric_name not in METRIC_NAMES or not isinstance(payload["sample"], dict) or not isinstance(config_data, dict):
            raise ValueError
        config = MetricProcessConfig(
            model=str(config_data["model"]),
            timeout_seconds=int(config_data["timeout_seconds"]),
            max_tokens=int(config_data["max_tokens"]),
            temperature=float(config_data["temperature"]),
        )
        account = CloudflareAccount(
            os.environ["RINGKAS_RAGAS_ACCOUNT_ID"],
            os.environ["RINGKAS_RAGAS_API_TOKEN"],
        )
        if (
            not account.account_id
            or not account.api_token
            or not config.model
            or config.timeout_seconds <= 0
            or config.max_tokens <= 0
            or not math.isfinite(config.temperature)
            or config.temperature <= 0
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        _write_result(output_path, {"status": "nonretryable"})
        return 0

    try:
        value = _evaluate_one_metric(payload["sample"], metric_name, config, account)
    except Exception as error:
        _write_result(output_path, {"status": "retryable" if _retryable_account_error(error) else "nonretryable"})
        return 0
    if not _finite_value(value):
        _write_result(output_path, {"status": "nonretryable"})
        return 0
    _write_result(output_path, {"status": "ok", "value": float(value)})
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 2:
        return 2
    return run(Path(arguments[0]), Path(arguments[1]))


if __name__ == "__main__":
    raise SystemExit(main())
