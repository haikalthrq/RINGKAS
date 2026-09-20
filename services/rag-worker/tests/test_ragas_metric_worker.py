import json
from pathlib import Path

import ringkas_worker.ragas_metric_worker as worker


def _input(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "sample": {"question_id": "q-1"},
                "metric_name": "faithfulness",
                "config": {"model": "test-model", "timeout_seconds": 120, "max_tokens": 16000, "temperature": 0.1},
            }
        ),
        encoding="utf-8",
    )


def test_worker_writes_only_finite_metric_result(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    _input(input_path)
    monkeypatch.setenv("RINGKAS_RAGAS_ACCOUNT_ID", "account")
    monkeypatch.setenv("RINGKAS_RAGAS_API_TOKEN", "token")
    monkeypatch.setattr(worker, "_evaluate_one_metric", lambda *args: 0.75)

    assert worker.run(input_path, output_path) == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"status": "ok", "value": 0.75}


def test_worker_sanitizes_provider_failures(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    _input(input_path)
    monkeypatch.setenv("RINGKAS_RAGAS_ACCOUNT_ID", "account")
    monkeypatch.setenv("RINGKAS_RAGAS_API_TOKEN", "token")

    def fails(*args):
        raise RuntimeError("provider token must not leave the worker")

    monkeypatch.setattr(worker, "_evaluate_one_metric", fails)
    monkeypatch.setattr(worker, "_retryable_account_error", lambda error: True)

    assert worker.run(input_path, output_path) == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {"status": "retryable"}
