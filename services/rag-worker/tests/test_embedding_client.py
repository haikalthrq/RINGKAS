import asyncio
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


def settings(base_url: str = "https://nim.example.test") -> NvidiaNimEmbeddingSettings:
    return NvidiaNimEmbeddingSettings(SecretStr("api-key-secret"), "embedding-model-tbd", base_url)


def response_handler(payload: object, seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload, request=request)

    return handler


def valid_payload() -> dict[str, object]:
    return {"data": [{"index": 0, "embedding": [1, 2.5]}], "model": "provider-model", "usage": {"prompt_tokens": 2, "total_tokens": 2}}


def test_protocol_implementation_and_single_input_request() -> None:
    seen: list[httpx.Request] = []
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(response_handler(valid_payload(), seen))) as client:
        assert isinstance(client, EmbeddingClient)
        result = client.embed(["  source text  "])

    assert str(seen[0].url) == "https://nim.example.test/v1/embeddings"
    assert seen[0].method == "POST"
    assert seen[0].headers["authorization"] == "Bearer api-key-secret"
    assert seen[0].headers["accept"] == "application/json"
    assert seen[0].headers["content-type"] == "application/json"
    assert seen[0].read().decode() == '{"model":"embedding-model-tbd","input":["  source text  "]}'
    assert result.dimension == 2
    assert result.vectors[0].values == (1.0, 2.5)
    assert result.model == "provider-model"
    assert result.usage is not None and result.usage.total_tokens == 2


def test_multiple_inputs_are_sent_once_and_reordered() -> None:
    seen: list[httpx.Request] = []
    payload = {"data": [{"index": 1, "embedding": [2]}, {"index": 0, "embedding": [1]}]}
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(response_handler(payload, seen))) as client:
        result = client.embed(["first", "second"], input_type="passage", truncate="END")

    body = seen[0].read().decode()
    assert body == '{"model":"embedding-model-tbd","input":["first","second"],"input_type":"passage","truncate":"END"}'
    assert [vector.values for vector in result.vectors] == [(1.0,), (2.0,)]


def test_optional_fields_are_omitted_by_default() -> None:
    seen: list[httpx.Request] = []
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(response_handler(valid_payload(), seen))) as client:
        client.embed(["text"])
    assert "input_type" not in seen[0].read().decode()
    assert "truncate" not in seen[0].read().decode()


@pytest.mark.parametrize("name", ["NVIDIA_NIM_API_KEY", "NVIDIA_NIM_EMBEDDING_MODEL", "NVIDIA_NIM_BASE_URL"])
def test_required_environment_values_fail_closed(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "key")
    monkeypatch.setenv("NVIDIA_NIM_EMBEDDING_MODEL", "model")
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://nim.example.test")
    monkeypatch.delenv(name, raising=False)
    with pytest.raises(EmbeddingConfigurationError):
        NvidiaNimEmbeddingSettings.from_environment()


@pytest.mark.parametrize(
    "value",
    ["", "ftp://nim.example.test", "nim.example.test", "https://user:password@nim.example.test", "https://nim.example.test?token=secret", "https://nim.example.test/#secret"],
)
def test_unsafe_base_urls_are_rejected_without_echoing_secrets(value: str) -> None:
    with pytest.raises(EmbeddingConfigurationError) as error:
        settings(value)
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert "password" not in rendered
    assert "token=secret" not in rendered


def test_base_url_joining_supports_v1_root_and_normalizes_slashes() -> None:
    seen: list[httpx.Request] = []
    with NvidiaNimEmbeddingClient(settings("http://nim.example.test/v1///"), transport=httpx.MockTransport(response_handler(valid_payload(), seen))) as client:
        client.embed(["text"])
    assert str(seen[0].url) == "http://nim.example.test/v1/embeddings"


@pytest.mark.parametrize("base_url", ["https://nim.example.test", "https://nim.example.test/"])
def test_base_url_root_is_supported(base_url: str) -> None:
    seen: list[httpx.Request] = []
    with NvidiaNimEmbeddingClient(settings(base_url), transport=httpx.MockTransport(response_handler(valid_payload(), seen))) as client:
        client.embed(["text"])
    assert str(seen[0].url) == "https://nim.example.test/v1/embeddings"


@pytest.mark.parametrize("base_url", ["https://nim.example.test/api", "https://nim.example.test/foo", "https://nim.example.test/v1/embeddings"])
def test_unrelated_base_url_paths_are_rejected(base_url: str) -> None:
    with pytest.raises(EmbeddingConfigurationError):
        settings(base_url)


def test_settings_repr_hides_api_key() -> None:
    configured = settings()
    assert "api-key-secret" not in repr(configured)
    assert "api-key-secret" not in str(configured)


@pytest.mark.parametrize("texts", [[], [""], ["  "], ["valid", ""]])
def test_empty_or_blank_inputs_are_rejected(texts: list[str]) -> None:
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(texts)


@pytest.mark.parametrize("texts", ["text", b"text", bytearray(b"text")])
def test_scalar_inputs_are_rejected_before_network_access(texts: object) -> None:
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called")

    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(fail_if_called)) as client:
        with pytest.raises(EmbeddingResponseError) as error:
            client.embed(texts)  # type: ignore[arg-type]
    assert error.value.__cause__ is None and error.value.__context__ is None


def test_list_and_tuple_inputs_remain_supported() -> None:
    handler = response_handler({"data": [{"index": 0, "embedding": [1]}]}, [])
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(handler)) as client:
        assert client.embed(["text"]).dimension == 1
        assert client.embed(("text",)).dimension == 1


@pytest.mark.parametrize("field", ["input_type", "truncate"])
@pytest.mark.parametrize("value", ["", "  ", 1, True, b"passage"])
def test_optional_request_fields_must_be_nonblank_strings(field: str, value: object) -> None:
    kwargs = {field: value}
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(["text"], **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 0, "embedding": []}],
        [{"index": 0, "embedding": [True]}],
        [{"index": 0, "embedding": [float("nan")]}],
        [{"index": 0, "embedding": [float("inf")]}],
        [{"index": 0, "embedding": [1]}, {"index": 0, "embedding": [2]}],
        [{"index": -1, "embedding": [1]}],
        [{"index": 1, "embedding": [1]}],
        [{"index": "0", "embedding": [1]}],
        [{"index": 0, "embedding": [1]}, {"index": 1, "embedding": [1, 2]}],
    ],
)
def test_invalid_vectors_and_indexes_are_rejected(data: list[dict[str, object]]) -> None:
    payload = {"data": data}
    has_nonfinite = any(
        isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")})
        for item in data
        for value in item.get("embedding", [])
    )
    if has_nonfinite:
        raw = '{"data":[{"index":0,"embedding":[NaN]}]}' if data[0]["embedding"][0] != float("inf") else '{"data":[{"index":0,"embedding":[Infinity]}]}'
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=raw.encode(), request=request))
    else:
        transport = httpx.MockTransport(response_handler(payload, []))
    with NvidiaNimEmbeddingClient(settings(), transport=transport) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(["first"] if len(data) == 1 else ["first", "second"])


@pytest.mark.parametrize("payload", [None, [], {"data": "wrong"}, {"data": [{"index": 0}]}])
def test_malformed_json_shapes_are_rejected(payload: object) -> None:
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(response_handler(payload, []))) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(["text"])


def test_invalid_json_is_typed_and_does_not_retain_body_or_input() -> None:
    secret = "response-body-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=f"invalid {secret}".encode(), request=request)

    input_text = "private chunk text"
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmbeddingResponseError) as error:
            client.embed([input_text])
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert secret not in rendered
    assert input_text not in rendered
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, EmbeddingAuthenticationError), (403, EmbeddingAuthenticationError), (429, EmbeddingRateLimitError), (500, EmbeddingProviderError)],
)
def test_provider_statuses_are_typed(status: int, expected: type[Exception]) -> None:
    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(lambda request: httpx.Response(status, request=request))) as client:
        with pytest.raises(expected) as error:
            client.embed(["text"])
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_timeout_and_transport_errors_are_typed_and_sanitized() -> None:
    secret = "transport-secret"

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(secret, request=request)

    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(EmbeddingTimeoutError) as error:
            client.embed(["private chunk"])
    assert secret not in str(error.value)
    assert error.value.__cause__ is None and error.value.__context__ is None

    def failed(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(secret, request=request)

    with NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(failed)) as client:
        with pytest.raises(EmbeddingTransportError):
            client.embed(["private chunk"])


def test_request_construction_failure_is_typed_and_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "request-construction-secret"
    client = NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200)))

    def fail(*args: object, **kwargs: object) -> httpx.Request:
        raise RuntimeError(secret)

    monkeypatch.setattr(client._client, "build_request", fail)
    try:
        with pytest.raises(EmbeddingTransportError) as error:
            client.embed(["text"])
    finally:
        client.close()
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert secret not in rendered
    assert error.value.__cause__ is None and error.value.__context__ is None


def test_embed_after_close_is_typed_and_sanitized() -> None:
    client = NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    client.close()
    with pytest.raises(EmbeddingTransportError) as error:
        client.embed(["text"])
    assert error.value.__cause__ is None and error.value.__context__ is None


@pytest.mark.parametrize("timeout", [True, False, "10", 0, -1, float("nan"), float("inf"), float("-inf")])
def test_direct_timeout_values_are_strictly_validated(timeout: object) -> None:
    with pytest.raises(EmbeddingConfigurationError) as error:
        NvidiaNimEmbeddingSettings(
            SecretStr("key"), "model", "https://nim.example.test", timeout, 60  # type: ignore[arg-type]
        )
    assert error.value.__cause__ is None and error.value.__context__ is None


@pytest.mark.parametrize("name", ["NVIDIA_NIM_EMBEDDING_CONNECT_TIMEOUT_SECONDS", "NVIDIA_NIM_EMBEDDING_READ_TIMEOUT_SECONDS"])
@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_environment_nonfinite_timeout_values_are_rejected(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "key")
    monkeypatch.setenv("NVIDIA_NIM_EMBEDDING_MODEL", "model")
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://nim.example.test")
    monkeypatch.setenv(name, value)
    with pytest.raises(EmbeddingConfigurationError) as error:
        NvidiaNimEmbeddingSettings.from_environment()
    assert value not in str(error.value)


@pytest.mark.parametrize("value", ["not-a-number", "9" * 5000])
def test_environment_timeout_conversion_errors_are_sanitized(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "key")
    monkeypatch.setenv("NVIDIA_NIM_EMBEDDING_MODEL", "model")
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://nim.example.test")
    monkeypatch.setenv("NVIDIA_NIM_EMBEDDING_CONNECT_TIMEOUT_SECONDS", value)
    with pytest.raises(EmbeddingConfigurationError) as error:
        NvidiaNimEmbeddingSettings.from_environment()
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert value not in rendered
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_extremely_large_direct_timeout_is_sanitized() -> None:
    value = 10**4000
    with pytest.raises(EmbeddingConfigurationError) as error:
        NvidiaNimEmbeddingSettings(SecretStr("key"), "model", "https://nim.example.test", value, 60)
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert str(value) not in rendered
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_extremely_large_integer_vector_is_a_typed_response_error() -> None:
    huge_integer = str(10**4000)
    content = f'{{"data":[{{"index":0,"embedding":[{huge_integer}]}}]}}'.encode()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=content, request=request))
    with NvidiaNimEmbeddingClient(settings(), transport=transport) as client:
        with pytest.raises(EmbeddingResponseError) as error:
            client.embed(["text"])
    assert error.value.__cause__ is None and error.value.__context__ is None


def test_client_cleanup_is_deterministic() -> None:
    client = NvidiaNimEmbeddingClient(settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, json=valid_payload(), request=request)))
    client.close()
    with pytest.raises(EmbeddingTransportError):
        client.embed(["text"])


def cloudflare_settings() -> CloudflareWorkersAiEmbeddingSettings:
    return CloudflareWorkersAiEmbeddingSettings("account-id", SecretStr("cloudflare-token"), "@cf/qwen/qwen3-embedding-0.6b")


def test_cloudflare_single_and_batched_requests_use_documented_contract() -> None:
    seen: list[httpx.Request] = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        data = [[1, 2.5]] if request.content == b'{"text":"single"}' else [[1, 2.5], [3, 4.5]]
        return httpx.Response(200, json={"result": {"data": data}, "success": True}, request=request)

    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(handler)) as client:
        first = client.embed(["single"])
        second = client.embed(["first", "second"])

    assert str(seen[0].url) == "https://api.cloudflare.com/client/v4/accounts/account-id/ai/run/@cf/qwen/qwen3-embedding-0.6b"
    assert seen[0].headers["authorization"] == "Bearer cloudflare-token"
    assert seen[0].read().decode() == '{"text":"single"}'
    assert seen[1].read().decode() == '{"text":["first","second"]}'
    assert first.vectors[0].values == (1.0, 2.5)
    assert [vector.values for vector in second.vectors] == [(1.0, 2.5), (3.0, 4.5)]
    assert first.model == "@cf/qwen/qwen3-embedding-0.6b"


@pytest.mark.parametrize("name", ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL"])
def test_cloudflare_required_environment_values_fail_closed(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL", "@cf/qwen/qwen3-embedding-0.6b")
    monkeypatch.delenv(name, raising=False)
    with pytest.raises(EmbeddingConfigurationError):
        CloudflareWorkersAiEmbeddingSettings.from_environment()


@pytest.mark.parametrize(
    ("payload", "input_count"),
    [
        ({"result": {"data": []}}, 1),
        ({"result": {"data": [[1], [2, 3]]}}, 2),
        ({"result": {"data": [[True]]}}, 1),
        ({"result": {"data": [[float("nan")]]}}, 1),
        ({"result": {"data": [[float("inf")]]}}, 1),
        ({"data": [[1]]}, 1),
    ],
)
def test_cloudflare_malformed_or_inconsistent_vectors_are_rejected(payload: object, input_count: int) -> None:
    data = payload.get("result", {}).get("data", []) if isinstance(payload, dict) else []
    value = data[0][0] if isinstance(data, list) and data and isinstance(data[0], list) and data[0] else None
    if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
        raw = b'{"result":{"data":[[NaN]]}}' if value != float("inf") else b'{"result":{"data":[[Infinity]]}}'
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=raw, request=request))
    else:
        transport = httpx.MockTransport(response_handler(payload, []))
    with CloudflareWorkersAiEmbeddingClient(
        cloudflare_settings(),
        transport=transport,
    ) as client:
        with pytest.raises(EmbeddingResponseError):
            client.embed(["text"] * input_count)


def test_cloudflare_identical_vectors_are_accepted_in_positional_order() -> None:
    payload = {"result": {"data": [[1, 2], [1, 2]]}}
    with CloudflareWorkersAiEmbeddingClient(
        cloudflare_settings(), transport=httpx.MockTransport(response_handler(payload, []))
    ) as client:
        result = client.embed(["first", "second"])

    assert [vector.index for vector in result.vectors] == [0, 1]
    assert [vector.values for vector in result.vectors] == [(1.0, 2.0), (1.0, 2.0)]


@pytest.mark.parametrize("value", ["", " ", "wrong-model"])
def test_cloudflare_model_is_approved_identifier(value: str) -> None:
    with pytest.raises(EmbeddingConfigurationError):
        CloudflareWorkersAiEmbeddingSettings("account", SecretStr("token"), value)


def test_cloudflare_status_timeout_and_cancellation_are_typed() -> None:
    for status, expected in ((401, EmbeddingAuthenticationError), (429, EmbeddingRateLimitError), (500, EmbeddingProviderError)):
        with CloudflareWorkersAiEmbeddingClient(
            cloudflare_settings(), transport=httpx.MockTransport(lambda request, status=status: httpx.Response(status, request=request))
        ) as client:
            with pytest.raises(expected):
                client.embed(["text"])

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret timeout", request=request)

    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(EmbeddingTimeoutError):
            client.embed(["private text"])

    def cancelled(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError("private cancellation")

    with CloudflareWorkersAiEmbeddingClient(cloudflare_settings(), transport=httpx.MockTransport(cancelled)) as client:
        with pytest.raises(EmbeddingCancellationError):
            client.embed(["private text"])
