import asyncio
import json
import math
import traceback

import httpx
import pytest
from pydantic import SecretStr

from ringkas_worker.embedding import (
    CloudflareWorkersAiEmbeddingClient,
    CloudflareWorkersAiEmbeddingSettings,
    EmbeddingAuthenticationError,
    EmbeddingCancellationError,
    EmbeddingClient,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingResponseError,
    EmbeddingTimeoutError,
    EmbeddingTransportError,
    NvidiaNimEmbeddingClient,
    NvidiaNimEmbeddingSettings,
)


def nim_settings(base_url: str = "https://nim.example.test") -> NvidiaNimEmbeddingSettings:
    return NvidiaNimEmbeddingSettings(SecretStr("nim-token"), "embedding-model", base_url)


def cloudflare_settings() -> CloudflareWorkersAiEmbeddingSettings:
    return CloudflareWorkersAiEmbeddingSettings("account-id", SecretStr("cloudflare-token"), "@cf/qwen/qwen3-embedding-0.6b")


def json_handler(payload: object, seen: list[httpx.Request] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=payload, request=request)

    return handler


def test_nvidia_behavior_remains_unchanged() -> None:
    payload = {"data": [{"index": 1, "embedding": [2]}, {"index": 0, "embedding": [1]}], "model": "provider"}
    seen: list[httpx.Request] = []
    with NvidiaNimEmbeddingClient(
        nim_settings(), transport=httpx.MockTransport(json_handler(payload, seen))
    ) as client:
        assert isinstance(client, EmbeddingClient)
        result = client.embed(["first", "second"], input_type="passage", truncate="END")
    assert str(seen[0].url) == "https://nim.example.test/v1/embeddings"
    assert seen[0].headers["authorization"] == "Bearer nim-token"
    assert json.loads(seen[0].content)["input_type"] == "passage"
    assert [vector.values for vector in result.vectors] == [(1.0,), (2.0,)]


@pytest.mark.parametrize("value", ["", "ftp://nim.example.test", "https://user:password@nim.example.test"])
def test_nvidia_configuration_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(EmbeddingConfigurationError):
        NvidiaNimEmbeddingSettings(SecretStr("token"), "model", value)


def test_cloudflare_endpoint_auth_and_input_forms() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        count = 1 if isinstance(body["text"], str) else len(body["text"])
        return httpx.Response(200, json={"success": True, "result": {"data": [[1] for _ in range(count)]}}, request=request)

    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(handler)) as client:
        assert client.embed(["single"]).vectors[0].values == (1.0,)
        assert len(client.embed(["first", "second"]).vectors) == 2

    assert str(seen[0].url) == "https://api.cloudflare.com/client/v4/accounts/account-id/ai/run/@cf/qwen/qwen3-embedding-0.6b"
    assert seen[0].headers["authorization"] == "Bearer cloudflare-token"
    assert json.loads(seen[0].content)["text"] == "single"
    assert json.loads(seen[1].content)["text"] == ["first", "second"]


def test_cloudflare_internal_batching_preserves_order_and_indexes() -> None:
    texts = [f"text-{index}" for index in range(CloudflareWorkersAiEmbeddingClient.INTERNAL_BATCH_SIZE + 2)]
    request_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        submitted = json.loads(request.content)["text"]
        submitted = [submitted] if isinstance(submitted, str) else submitted
        request_sizes.append(len(submitted))
        data = [[int(text.rsplit("-", 1)[1])] for text in submitted]
        return httpx.Response(200, json={"success": True, "result": {"data": data}}, request=request)

    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(handler)) as client:
        result = client.embed(texts)

    assert request_sizes == [CloudflareWorkersAiEmbeddingClient.INTERNAL_BATCH_SIZE, 2]
    assert [vector.index for vector in result.vectors] == list(range(len(texts)))
    assert [vector.values for vector in result.vectors] == [(float(index),) for index in range(len(texts))]


@pytest.mark.parametrize("texts", [[], [""], ["  "], ["valid", ""]])
def test_cloudflare_empty_or_blank_inputs_are_rejected(texts: list[str]) -> None:
    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(texts)


@pytest.mark.parametrize("texts", ["text", b"text", bytearray(b"text"), [1]])
def test_cloudflare_non_sequence_inputs_are_rejected(texts: object) -> None:
    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(texts)  # type: ignore[arg-type]


def test_cloudflare_undocumented_fields_are_rejected() -> None:
    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(["text"], input_type="passage")


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, EmbeddingAuthenticationError), (403, EmbeddingAuthenticationError), (429, EmbeddingRateLimitError), (500, EmbeddingProviderError)],
)
def test_cloudflare_status_mapping(status: int, expected: type[Exception]) -> None:
    with CloudflareWorkersAiEmbeddingClient(
        cloudflare_settings(), transport=httpx.MockTransport(lambda request: httpx.Response(status, request=request))
    ) as client:
        with pytest.raises(expected):
            client.embed(["text"])


def test_cloudflare_timeout_transport_and_cancellation_mapping() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private-timeout", request=request)

    def transport_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private-transport", request=request)

    def cancelled(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError("private-cancel")

    for handler, expected in ((timeout, EmbeddingTimeoutError), (transport_failure, EmbeddingTransportError), (cancelled, EmbeddingCancellationError)):
        with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(expected):
                client.embed(["text"])


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"success": False, "result": {"data": [[1]]}},
        {"success": True, "errors": ["provider-error"], "result": {"data": [[1]]}},
        {"success": True, "result": None},
        {"success": True, "result": {"data": "wrong"}},
    ],
)
def test_cloudflare_invalid_json_or_envelope_is_rejected(payload: object) -> None:
    transport = (
        httpx.MockTransport(lambda request: httpx.Response(200, content=b"private-raw-response", request=request))
        if payload is None
        else httpx.MockTransport(json_handler(payload))
    )
    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=transport) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(["text"])


@pytest.mark.parametrize(
    "data",
    [
        [],
        [[]],
        [[True]],
        [[float("nan")]],
        [[float("inf")]],
        [[1], [2, 3]],
    ],
)
def test_cloudflare_invalid_vectors_are_rejected(data: list[object]) -> None:
    if data and data[0] and isinstance(data[0][0], float) and not math.isfinite(data[0][0]):  # type: ignore[index]
        raw = b'{"success":true,"result":{"data":[[NaN]]}}' if math.isnan(data[0][0]) else b'{"success":true,"result":{"data":[[Infinity]]}}'  # type: ignore[index]
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=raw, request=request))
        input_count = 1
    else:
        transport = httpx.MockTransport(json_handler({"success": True, "errors": [], "result": {"data": data}}))
        input_count = 2 if len(data) == 2 else 1
    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=transport) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(["text"] * input_count)


def test_cloudflare_cross_batch_dimension_mismatch_is_rejected() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        submitted = json.loads(request.content)["text"]
        count = len(submitted) if isinstance(submitted, list) else 1
        values = [[1] for _ in range(count)] if calls == 1 else [[1, 2] for _ in range(count)]
        return httpx.Response(200, json={"success": True, "result": {"data": values}}, request=request)

    texts = ["text"] * (CloudflareWorkersAiEmbeddingClient.INTERNAL_BATCH_SIZE + 1)
    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(texts)
    assert calls == 2


def test_cloudflare_errors_do_not_include_secret_or_text() -> None:
    document_text = "private-document-text"
    raw_marker = "private-raw-response"
    with CloudflareWorkersAiEmbeddingClient(
        cloudflare_settings(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=raw_marker.encode(), request=request)),
    ) as client:
        with pytest.raises(EmbeddingResponseError) as error:
            client.embed([document_text])
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert "cloudflare-token" not in rendered
    assert document_text not in rendered
    assert raw_marker not in rendered


def test_cloudflare_context_manager_and_use_after_close() -> None:
    client = CloudflareWorkersAiEmbeddingClient(
        cloudflare_settings(), transport=httpx.MockTransport(json_handler({"success": True, "result": {"data": [[1]]}}))
    )
    with client:
        assert client.embed(["text"]).dimension == 1
    client.close()
    with pytest.raises(EmbeddingTransportError):
        client.embed(["text"])


def test_cloudflare_model_mismatch_is_rejected() -> None:
    with pytest.raises(EmbeddingConfigurationError):
        CloudflareWorkersAiEmbeddingSettings("account-id", SecretStr("cloudflare-token"), "other-model")


@pytest.mark.parametrize("name", ["CLOUDFLARE_WORKERS_AI_EMBEDDING_CONNECT_TIMEOUT_SECONDS", "CLOUDFLARE_WORKERS_AI_EMBEDDING_READ_TIMEOUT_SECONDS"])
def test_cloudflare_invalid_timeout_environment_is_typed(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "secret-token")
    monkeypatch.setenv("CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL", "@cf/qwen/qwen3-embedding-0.6b")
    monkeypatch.setenv(name, "not-a-timeout")
    with pytest.raises(EmbeddingConfigurationError) as error:
        CloudflareWorkersAiEmbeddingSettings.from_environment()
    assert "secret-token" not in str(error.value)
