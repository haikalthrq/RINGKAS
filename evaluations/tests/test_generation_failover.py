from __future__ import annotations

import importlib.util
import io
import json
import logging
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_factual_responses.py"
SPEC = importlib.util.spec_from_file_location("factual_response_generation", SCRIPT_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    configured = logging.getLogger("test-generation-failover")
    configured.handlers.clear()
    configured.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(stream)
    configured.addHandler(handler)
    return configured, stream


def target(provider: str, index: int | None, endpoint: str) -> object:
    return module.GenerationTarget(provider, "configured-model", endpoint, "secret-token", index)


def cloudflare_pool(size: int) -> object:
    return module.CloudflareAccountPool.from_values([(f"account-{index}", f"token-{index}") for index in range(size)])


def response(text: str = "OK") -> dict[str, object]:
    return {"choices": [{"message": {"content": text}}]}


def http_error(status: int) -> HTTPError:
    return HTTPError("https://provider.invalid", status, "sanitized", {}, io.BytesIO(b"provider secret"))


def test_cloudflare_429_advances_primary_secondary_tertiary() -> None:
    logger_instance, _ = logger()
    calls: list[str] = []
    outcomes = {"account-0": http_error(429), "account-1": http_error(429), "account-2": response()}

    def request(endpoint, _payload, _headers, **_kwargs):
        calls.append(endpoint)
        outcome = next(outcome for account, outcome in outcomes.items() if account in endpoint)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    pool = module.GenerationPool(
        cloudflare_pool(3),
        "configured-model",
        [],
        request,
    )
    text, selected = pool.generate("question", ["context"], logger_instance)

    assert text == "OK" and selected.account_index == 2
    assert len(calls) == 3 and all(f"account-{index}" in calls[index] for index in range(3))
    calls.clear()
    pool.generate("question", ["context"], logger_instance)
    assert len(calls) == 1 and "account-2" in calls[-1]


def test_evaluator_uses_shared_canonical_account_pool(monkeypatch) -> None:
    values = {
        "CLOUDFLARE_ACCOUNT_ID": "primary",
        "CLOUDFLARE_API_TOKEN": "primary-token",
        "CLOUDFLARE_SECONDARY_ACCOUNT_ID": "secondary",
        "CLOUDFLARE_SECONDARY_API_TOKEN": "secondary-token",
        "CLOUDFLARE_TERTIARY_ACCOUNT_ID": "tertiary",
        "CLOUDFLARE_TERTIARY_API_TOKEN": "tertiary-token",
        "CLOUDFLARE_WORKERS_AI_GENERATION_MODEL": "generation-model",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    configured = module.configured_generation_pool()

    assert [account.index for account in configured.cloudflare_pool.accounts] == [0, 1, 2]
    assert configured.cloudflare_model == "generation-model"


def test_cloudflare_timeout_advances_to_secondary() -> None:
    logger_instance, _ = logger()

    def request(endpoint, _payload, _headers, **_kwargs):
        if "account-0" in endpoint:
            raise TimeoutError("secret timeout")
        return response()

    pool = module.GenerationPool(
        cloudflare_pool(2),
        "configured-model",
        [],
        request,
    )
    _, selected = pool.generate("question", ["context"], logger_instance)

    assert selected.account_index == 1


def test_all_cloudflare_accounts_use_nvidia_fallback() -> None:
    logger_instance, _ = logger()

    def request(endpoint, _payload, _headers, **_kwargs):
        if "account-" in endpoint:
            raise http_error(503)
        return response("NVIDIA")

    pool = module.GenerationPool(
        cloudflare_pool(3),
        "configured-model",
        [target("nvidia_nim", None, "nvidia")],
        request,
    )
    text, selected = pool.generate("question", ["context"], logger_instance)

    assert text == "NVIDIA" and selected.provider == "nvidia_nim"
    assert [attempt["account_index"] for attempt in pool.last_attempts[:3]] == [0, 1, 2]


def test_nvidia_primary_failure_uses_secondary_model() -> None:
    logger_instance, _ = logger()
    calls: list[str] = []

    def request(endpoint, payload, _headers, **_kwargs):
        calls.append(payload["model"])
        if payload["model"] in {"configured-model", "mistral-model"}:
            raise http_error(503)
        return response("secondary NVIDIA")

    pool = module.GenerationPool(
        cloudflare_pool(1),
        "configured-model",
        [module.GenerationTarget("nvidia_nim", "mistral-model", "nvidia-primary", "secret-token", None), module.GenerationTarget("nvidia_nim", "nvidia-secondary", "nvidia-secondary", "secret-token", None)],
        request,
    )

    text, selected = pool.generate("question", ["context"], logger_instance)

    assert text == "secondary NVIDIA" and selected.model == "nvidia-secondary"
    assert calls == ["configured-model", "mistral-model", "nvidia-secondary"]


def test_all_generation_targets_fail_without_provider_secret() -> None:
    logger_instance, stream = logger()

    def request(_endpoint, _payload, _headers, **_kwargs):
        raise http_error(503)

    pool = module.GenerationPool(
        cloudflare_pool(1),
        "configured-model",
        [target("nvidia_nim", None, "nvidia-primary")],
        request,
    )
    with pytest.raises(module.GenerationProviderExhaustedError):
        pool.generate("question", ["context"], logger_instance)

    assert "provider secret" not in stream.getvalue()
    assert "secret-token" not in stream.getvalue()


def test_checkpoint_resume_returns_only_saved_successes(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(json.dumps({"dataset_sha256": "sha", "responses": [{"question_id": "q-0001"}], "failures": [{"question_id": "q-0002"}]}))

    responses, failures = module.load_checkpoint(checkpoint, "sha")

    assert [item["question_id"] for item in responses] == ["q-0001"]
    assert [item["question_id"] for item in failures] == ["q-0002"]
    assert module.load_checkpoint(checkpoint, "different") == ([], [])


def test_no_synthetic_context_fallback_and_secrets_are_not_logged() -> None:
    logger_instance, stream = logger()

    def request(_endpoint, _payload, _headers, **_kwargs):
        raise http_error(429)

    pool = module.GenerationPool(cloudflare_pool(1), "configured-model", [], request)
    try:
        pool.generate("question", ["context"], logger_instance)
    except Exception:
        pass

    assert module.usable_contexts({"citations": []}) == []
    assert "secret-token" not in stream.getvalue()
    assert "provider secret" not in stream.getvalue()
