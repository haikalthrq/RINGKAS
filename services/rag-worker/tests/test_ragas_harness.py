import asyncio
import json
from pathlib import Path

import httpx
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
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "primary")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")
    monkeypatch.setenv("RAGAS_LLM_MODEL", "@cf/openai/gpt-oss-120b")
    monkeypatch.setenv("RAGAS_LLM_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("RAGAS_LLM_MAX_RETRIES", "1")
    monkeypatch.setenv("RAGAS_LLM_MAX_WORKERS", "1")
    monkeypatch.setenv("RAGAS_LLM_BATCH_SIZE", "25")
    monkeypatch.setenv("RAGAS_LLM_PREFLIGHT_SAMPLES", "2")
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


def test_live_completes_with_metadata_using_offline_fakes(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    calls: list[int] = []

    def fake_evaluate(components, samples, config):
        calls.append(len(samples))
        return [{"question_id": sample["question_id"], **{metric: 1.0 for metric in harness.METRIC_NAMES}} for sample in samples]

    monkeypatch.setattr(harness, "_load_ragas_components", lambda: (object(),) * 8)
    monkeypatch.setattr(harness, "_evaluate_batch", fake_evaluate)
    checkpoint = tmp_path / "checkpoint.json"

    result = harness.run_live(dataset_path, responses_path, checkpoint)

    assert result["status"] == "completed"
    assert result["sample_count"] == 100
    assert result["resumed"] is False
    assert result["evaluator"]["model"] == "@cf/openai/gpt-oss-120b"
    assert result["evaluator"]["account_count"] == 1
    assert len(result["selected_sample_ids"]) == 100
    assert len(result["metrics"]) == 100
    assert calls[:2] == [1, 1]


def test_checkpoint_config_mismatch_blocks_resume(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    monkeypatch.setattr(harness, "_load_ragas_components", lambda: (object(),) * 8)
    monkeypatch.setattr(
        harness,
        "_evaluate_batch",
        lambda components, samples, config: [
            {"question_id": sample["question_id"], **{metric: 1.0 for metric in harness.METRIC_NAMES}} for sample in samples
        ],
    )
    checkpoint = tmp_path / "checkpoint.json"
    assert harness.run_live(dataset_path, responses_path, checkpoint)["status"] == "completed"
    monkeypatch.setenv("RAGAS_LLM_BATCH_SIZE", "20")

    result = harness.run_live(dataset_path, responses_path, checkpoint)

    assert result == {
        "status": "blocked",
        "reason": "RAGAS checkpoint fingerprint does not match this baseline.",
        "count": 100,
    }


def test_non_finite_metric_fails_closed(monkeypatch, tmp_path: Path) -> None:
    dataset_path, responses_path = _live_inputs(tmp_path)
    _configure_live(monkeypatch)
    monkeypatch.setattr(harness, "_load_ragas_components", lambda: (object(),) * 8)
    monkeypatch.setattr(
        harness,
        "_evaluate_batch",
        lambda components, samples, config: [
            {"question_id": sample["question_id"], "faithfulness": float("nan"), "context_precision": 1.0, "context_recall": 1.0}
            for sample in samples
        ],
    )

    result = harness.run_live(dataset_path, responses_path, tmp_path / "checkpoint.json")

    assert result == {
        "status": "blocked",
        "reason": "RAGAS evaluator preflight failed.",
        "count": 0,
    }


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.statuses.pop(0), request=request)


def test_cloudflare_transport_fails_over_on_retryable_status() -> None:
    underlying = _RecordingTransport([429, 200])
    transport = harness.CloudflareFailoverTransport(
        (
            harness.CloudflareAccount("primary", "token-primary"),
            harness.CloudflareAccount("secondary", "token-secondary"),
        ),
        1,
        transport=underlying,
    )

    async def send() -> httpx.Response:
        request = httpx.Request("POST", f"{harness.ROUTER_BASE_URL}/chat/completions", content=b"{}")
        return await transport.handle_async_request(request)

    response = asyncio.run(send())

    assert response.status_code == 200
    assert [request.url.path.split("/")[4] for request in underlying.requests] == ["primary", "secondary"]
    assert [request.headers["authorization"] for request in underlying.requests] == ["Bearer token-primary", "Bearer token-secondary"]
    asyncio.run(transport.aclose())


def test_cloudflare_transport_enforces_strict_timeout() -> None:
    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(1)
            return httpx.Response(200, request=request)

    transport = harness.CloudflareFailoverTransport(
        (harness.CloudflareAccount("primary", "token-primary"),), 0.001, transport=SlowTransport()
    )

    async def send() -> None:
        request = httpx.Request("POST", f"{harness.ROUTER_BASE_URL}/chat/completions", content=b"{}")
        with pytest.raises(harness.CloudflareEvaluatorTransportError, match="Cloudflare evaluator request failed"):
            await transport.handle_async_request(request)

    asyncio.run(send())
    asyncio.run(transport.aclose())
