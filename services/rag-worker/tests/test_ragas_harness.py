import json
from pathlib import Path

import pytest

import ringkas_worker.ragas_harness as harness
from ringkas_worker.evaluation_dataset import APPROVED_QUESTION_TYPES
from ringkas_worker.ragas_harness import DEFAULT_FIXTURE_PATH, run_sample


def test_deterministic_sample_is_explicitly_fixture_validation() -> None:
    result = run_sample(responses_path=DEFAULT_FIXTURE_PATH)

    assert result["status"] == "fixture_validated"
    assert result["evaluation_label"] == "deterministic harness validation"
    assert result["metrics"] is None
    assert result["dataset_capacity"] == 100


def test_sample_output_is_machine_readable(capsys) -> None:
    from ringkas_worker.ragas_harness import main

    assert main(["--mode", "sample"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "fixture_validated"


def _live_inputs(tmp_path: Path) -> tuple[Path, Path]:
    question_types = sorted(APPROVED_QUESTION_TYPES)
    records = []
    responses = []
    for index in range(1, 1001):
        question_id = f"q-{index:04d}"
        question_type = question_types[(index - 1) % len(question_types)]
        records.append(
            {
                "question_id": question_id,
                "question_text": f"Question {index}",
                "question_type": question_type,
                "topic": "Topic",
                "reference_answer": "Answer",
                "evidence": {
                    "document_id": "00000000-0000-0000-0000-000000000001",
                    "chunk_id": "00000000-0000-0000-0000-000000000002",
                    "document_title": "Title",
                    "publication_year": 2024,
                    "region": "DKI Jakarta",
                    "page_start": 1,
                    "page_end": 1,
                    "source_url": "https://example.com/source.pdf",
                    "excerpt": "Evidence",
                },
                "verification_status": "verified",
            }
        )
        responses.append(
            {
                "question_id": question_id,
                "user_input": f"Question {index}",
                "response": "Answer",
                "reference": "Answer",
                "retrieved_contexts": ["Evidence"],
            }
        )
    dataset_path = tmp_path / "dataset.json"
    responses_path = tmp_path / "responses.json"
    dataset_path.write_text(
        json.dumps({"schema_version": "1", "dataset_status": "ready", "capacity": 1000, "records": records}),
        encoding="utf-8",
    )
    responses_path.write_text(json.dumps({"records": responses}), encoding="utf-8")
    return dataset_path, responses_path


def _configure_live(monkeypatch) -> None:
    monkeypatch.setenv("RAGAS_EVALUATOR_PROVIDER", "cloudflare")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "primary")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")
    monkeypatch.setenv("RAGAS_LLM_MODEL", "@cf/openai/gpt-oss-120b")
    monkeypatch.setenv("RAGAS_LLM_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("RAGAS_LLM_MAX_RETRIES", "1")
    monkeypatch.setenv("RAGAS_LLM_MAX_WORKERS", "1")
    monkeypatch.setenv("RAGAS_LLM_PREFLIGHT_SAMPLES", "20")
    monkeypatch.setenv("RAGAS_LLM_MAX_TOKENS", "128")
    monkeypatch.setenv("RAGAS_LLM_TEMPERATURE", "0.1")


def test_stratified_selection_is_deterministic_and_balanced(tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    dataset = harness.load_dataset(dataset_path)
    responses = harness._load_responses(responses_path)

    selected = harness._stratified_samples(dataset, responses)
    reversed_selected = harness._stratified_samples(dataset, list(reversed(responses)))
    selected_types = {record.question_id: record.question_type for record in dataset.records}
    counts: dict[str, int] = {}
    for sample in selected:
        counts[selected_types[sample["question_id"]]] = counts.get(selected_types[sample["question_id"]], 0) + 1

    assert [sample["question_id"] for sample in selected] == [sample["question_id"] for sample in reversed_selected]
    assert len(selected) == 100
    assert max(counts.values()) - min(counts.values()) <= 1


def test_live_config_rejects_parallel_ragas_workers(monkeypatch) -> None:
    _configure_live(monkeypatch)
    monkeypatch.setenv("RAGAS_LLM_MAX_WORKERS", "2")

    with pytest.raises(ValueError, match="must be 1"):
        harness._live_config()


def test_live_config_defaults_to_cloudflare(monkeypatch) -> None:
    _configure_live(monkeypatch)
    monkeypatch.delenv("RAGAS_EVALUATOR_PROVIDER")

    assert harness._live_config().evaluator_provider == "cloudflare"


def test_live_config_selects_deepseek_without_cloudflare_credentials(monkeypatch) -> None:
    monkeypatch.setenv("RAGAS_EVALUATOR_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-token")
    monkeypatch.setenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com/")
    monkeypatch.setenv("DEEPSEEK_RAGAS_MODEL", "deepseek-flash")
    monkeypatch.setenv("RAGAS_DEEPSEEK_REASONING_EFFORT", "high")
    monkeypatch.setenv("RAGAS_LLM_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("RAGAS_LLM_MAX_RETRIES", "1")
    monkeypatch.setenv("RAGAS_LLM_MAX_WORKERS", "1")
    monkeypatch.setenv("RAGAS_LLM_PREFLIGHT_SAMPLES", "20")
    monkeypatch.setenv("RAGAS_LLM_MAX_TOKENS", "128")
    monkeypatch.setenv("RAGAS_LLM_TEMPERATURE", "0.1")

    config = harness._live_config()

    assert config.evaluator_provider == "deepseek"
    assert config.model == "deepseek-flash"
    assert config.reasoning_effort == "high"
    assert config.deepseek_target is not None
    assert config.deepseek_target.base_url == "https://api.deepseek.com"
    assert config.accounts == ()
    assert "api.deepseek.com" not in config.fingerprint("test")["base_url"]


def test_live_config_rejects_deepseek_max_reasoning_effort(monkeypatch) -> None:
    _configure_live(monkeypatch)
    monkeypatch.setenv("RAGAS_EVALUATOR_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-token")
    monkeypatch.setenv("RAGAS_DEEPSEEK_REASONING_EFFORT", "max")

    with pytest.raises(ValueError, match="low, medium, or high"):
        harness._live_config()


def test_live_completes_with_metadata_using_offline_fakes(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    calls: list[tuple[str, str]] = []

    def fake_attempt(sample, metric_name, config, account):
        calls.append((sample["question_id"], metric_name))
        return harness.MetricAttempt(value=1.0)

    checkpoint = tmp_path / "checkpoint.json"

    result = harness.run_live(dataset_path, responses_path, checkpoint, attempt_runner=fake_attempt)

    assert result["status"] == "completed"
    assert result["sample_count"] == 100
    assert result["resumed"] is False
    assert result["evaluator"]["model"] == "@cf/openai/gpt-oss-120b"
    assert result["evaluator"]["account_count"] == 1
    assert len(result["selected_sample_ids"]) == 100
    assert len(result["metrics"]) == 100
    assert len(calls) == 300
    assert calls[:3] == [(result["selected_sample_ids"][0], metric) for metric in harness.METRIC_NAMES]
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert set(saved["fingerprint"]) == {
        "execution_architecture",
        "model",
        "provider",
        "base_url",
        "reasoning_effort",
        "max_tokens",
        "timeout_seconds",
        "max_retries",
        "max_workers",
        "ragas_version",
        "temperature",
    }
    assert saved["selected_sample_ids"] == result["selected_sample_ids"]
    assert saved["selected_sample_ids_hash"] == result["selected_sample_ids_hash"]


def test_checkpoint_config_mismatch_blocks_resume(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    fake_attempt = lambda sample, metric_name, config, account: harness.MetricAttempt(value=1.0)
    checkpoint = tmp_path / "checkpoint.json"
    assert harness.run_live(dataset_path, responses_path, checkpoint, attempt_runner=fake_attempt)["status"] == "completed"
    monkeypatch.setenv("RAGAS_LLM_TIMEOUT_SECONDS", "2")

    result = harness.run_live(dataset_path, responses_path, checkpoint, attempt_runner=fake_attempt)

    assert result == {
        "status": "blocked",
        "reason": "RAGAS checkpoint fingerprint does not match this baseline.",
        "count": 100,
    }


def test_checkpoint_rejects_switching_evaluator_provider(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    checkpoint = tmp_path / "checkpoint.json"
    fake_attempt = lambda sample, metric_name, config, target: harness.MetricAttempt(value=1.0)
    assert harness.run_live(dataset_path, responses_path, checkpoint, attempt_runner=fake_attempt)["status"] == "completed"
    monkeypatch.setenv("RAGAS_EVALUATOR_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-token")

    result = harness.run_live(dataset_path, responses_path, checkpoint, attempt_runner=fake_attempt)

    assert result["reason"] == "RAGAS checkpoint fingerprint does not match this baseline."


def test_checkpoint_resumes_at_next_metric(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    checkpoint = tmp_path / "checkpoint.json"
    first_calls = 0

    def interrupted(sample, metric_name, config, account):
        nonlocal first_calls
        first_calls += 1
        return harness.MetricAttempt(value=1.0) if first_calls <= 4 else harness.MetricAttempt(failure="process")

    first = harness.run_live(dataset_path, responses_path, checkpoint, preflight_only=True, attempt_runner=interrupted)
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))

    resumed_calls: list[tuple[str, str]] = []

    def succeeds(sample, metric_name, config, account):
        resumed_calls.append((sample["question_id"], metric_name))
        return harness.MetricAttempt(value=1.0)

    second = harness.run_live(dataset_path, responses_path, checkpoint, preflight_only=True, attempt_runner=succeeds)

    assert first["status"] == "blocked"
    assert first["count"] == 4
    assert sum(len(metrics) for metrics in saved["partial_metrics"].values()) == 4
    assert saved["preflight_complete"] is False
    assert second["status"] == "preflight_validated"
    assert second["metric_count"] == 60
    assert len(resumed_calls) == 56


def test_preflight_requires_all_sixty_finite_metrics(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    calls = 0

    def fails_last_metric(sample, metric_name, config, account):
        nonlocal calls
        calls += 1
        if calls == 60:
            return harness.MetricAttempt(value=float("nan"))
        return harness.MetricAttempt(value=1.0)

    result = harness.run_live(
        dataset_path,
        responses_path,
        tmp_path / "checkpoint.json",
        preflight_only=True,
        attempt_runner=fails_last_metric,
    )

    assert result == {
        "status": "blocked",
        "reason": "RAGAS evaluator preflight failed.",
        "count": 59,
    }


def test_full_mode_resumes_preflight_and_only_runs_remaining_eighty_samples(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    checkpoint = tmp_path / "checkpoint.json"
    fake_attempt = lambda sample, metric_name, config, account: harness.MetricAttempt(value=1.0)

    preflight = harness.run_live(
        dataset_path, responses_path, checkpoint, preflight_only=True, attempt_runner=fake_attempt
    )
    remaining_calls: list[tuple[str, str]] = []

    def finish(sample, metric_name, config, account):
        remaining_calls.append((sample["question_id"], metric_name))
        return harness.MetricAttempt(value=1.0)

    completed = harness.run_live(dataset_path, responses_path, checkpoint, attempt_runner=finish)

    assert preflight["status"] == "preflight_validated"
    assert completed["status"] == "completed"
    assert completed["resumed"] is True
    assert len(remaining_calls) == 80 * len(harness.METRIC_NAMES)
    assert {question_id for question_id, _ in remaining_calls}.isdisjoint(
        row["question_id"] for row in preflight["metrics"]
    )


def test_metric_falls_back_to_next_account_after_all_primary_attempts(monkeypatch) -> None:
    _configure_live(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_SECONDARY_ACCOUNT_ID", "secondary")
    monkeypatch.setenv("CLOUDFLARE_SECONDARY_API_TOKEN", "secondary-token")
    monkeypatch.setenv("RAGAS_LLM_MAX_RETRIES", "2")
    config = harness._live_config()
    accounts: list[str] = []

    def fake_attempt(sample, metric_name, config, account):
        accounts.append(account.account_id)
        if account.account_id == "primary":
            return harness.MetricAttempt(failure="timeout")
        return harness.MetricAttempt(value=0.75)

    result = harness._evaluate_metric_with_failover(
        {"question_id": "q-1"}, "faithfulness", config, fake_attempt
    )

    assert result.value == 0.75
    assert accounts == ["primary", "primary", "secondary"]


def test_nonfinite_metric_uses_next_account(monkeypatch) -> None:
    _configure_live(monkeypatch)
    monkeypatch.setenv("CLOUDFLARE_SECONDARY_ACCOUNT_ID", "secondary")
    monkeypatch.setenv("CLOUDFLARE_SECONDARY_API_TOKEN", "secondary-token")
    config = harness._live_config()

    def fake_attempt(sample, metric_name, config, account):
        return harness.MetricAttempt(value=float("nan") if account.account_id == "primary" else 0.5)

    result = harness._evaluate_metric_with_failover({"question_id": "q-1"}, "context_recall", config, fake_attempt)

    assert result.value == 0.5


def test_subprocess_worker_uses_private_ipc_and_returns_finite_value(monkeypatch, tmp_path: Path) -> None:
    _configure_live(monkeypatch)
    config = harness._live_config()

    class CompletedProcess:
        pid = 123

        def wait(self, timeout):
            assert timeout == config.timeout_seconds
            return 0

    def fake_popen(command, **kwargs):
        assert command[:3] == [harness.sys.executable, "-m", "ringkas_worker.ragas_metric_worker"]
        assert kwargs["start_new_session"] is True
        assert kwargs["env"]["RINGKAS_RAGAS_ACCOUNT_ID"] == "primary"
        assert kwargs["env"]["RINGKAS_RAGAS_API_TOKEN"] == "test-token"
        input_path, output_path = map(Path, command[3:])
        assert input_path.parent.parent == tmp_path
        assert input_path.stat().st_mode & 0o777 == 0o600
        assert output_path.stat().st_mode & 0o777 == 0o600
        input_payload = input_path.read_text(encoding="utf-8")
        assert "api_token" not in input_payload
        assert "test-token" not in input_payload
        output_path.write_text('{"status":"ok","value":0.5}', encoding="utf-8")
        return CompletedProcess()

    result = harness._run_metric_attempt(
        {"question_id": "q-1"},
        "faithfulness",
        config,
        config.accounts[0],
        subprocess_runner=fake_popen,
        ipc_directory=tmp_path,
    )

    assert result == harness.MetricAttempt(value=0.5)
    assert list(tmp_path.iterdir()) == []


def test_subprocess_worker_routes_deepseek_credentials_only_through_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RAGAS_EVALUATOR_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-test-token")
    monkeypatch.setenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("RAGAS_LLM_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("RAGAS_LLM_MAX_RETRIES", "1")
    monkeypatch.setenv("RAGAS_LLM_MAX_WORKERS", "1")
    monkeypatch.setenv("RAGAS_LLM_PREFLIGHT_SAMPLES", "20")
    monkeypatch.setenv("RAGAS_LLM_MAX_TOKENS", "128")
    monkeypatch.setenv("RAGAS_LLM_TEMPERATURE", "0.1")
    config = harness._live_config()

    class CompletedProcess:
        pid = 123

        def wait(self, timeout):
            return 0

    def fake_popen(command, **kwargs):
        assert kwargs["env"]["RINGKAS_RAGAS_DEEPSEEK_API_KEY"] == "deepseek-test-token"
        assert kwargs["env"]["RINGKAS_RAGAS_DEEPSEEK_BASE_URL"] == "https://api.deepseek.com"
        input_path, output_path = map(Path, command[3:])
        input_payload = input_path.read_text(encoding="utf-8")
        assert "deepseek-test-token" not in input_payload
        assert "api.deepseek.com" not in input_payload
        output_path.write_text('{"status":"ok","value":0.5}', encoding="utf-8")
        return CompletedProcess()

    result = harness._run_metric_attempt(
        {"question_id": "q-1"}, "faithfulness", config, config.deepseek_target,
        subprocess_runner=fake_popen, ipc_directory=tmp_path,
    )

    assert result == harness.MetricAttempt(value=0.5)


def test_hard_timeout_terminates_then_kills_child_process_group(monkeypatch, tmp_path: Path) -> None:
    _configure_live(monkeypatch)
    config = harness._live_config()
    signals: list[int] = []

    class HungProcess:
        pid = 456

        def __init__(self):
            self.waits = 0

        def wait(self, timeout):
            self.waits += 1
            if self.waits < 3:
                raise harness.subprocess.TimeoutExpired("worker", timeout)
            return -9

    def fake_popen(command, **kwargs):
        assert kwargs["start_new_session"] is True
        return HungProcess()

    monkeypatch.setattr(harness.os, "killpg", lambda pid, sig: signals.append(sig))

    result = harness._run_metric_attempt(
        {"question_id": "q-1"},
        "faithfulness",
        config,
        config.accounts[0],
        subprocess_runner=fake_popen,
        ipc_directory=tmp_path,
    )

    assert result.failure == "timeout"
    assert signals == [harness.signal.SIGTERM, harness.signal.SIGKILL]
