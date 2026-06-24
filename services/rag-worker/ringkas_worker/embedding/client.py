from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol, Self, runtime_checkable

import httpx

from ringkas_worker.embedding.config import NvidiaNimEmbeddingSettings
from ringkas_worker.embedding.errors import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingResponseError,
    EmbeddingTimeoutError,
    EmbeddingTransportError,
    raise_sanitized,
)


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    index: int
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingUsage:
    prompt_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    vectors: tuple[EmbeddingVector, ...]
    dimension: int
    model: str | None = None
    usage: EmbeddingUsage | None = None


@runtime_checkable
class EmbeddingClient(Protocol):
    def embed(self, texts: Sequence[str], *, input_type: str | None = None, truncate: str | None = None) -> EmbeddingBatchResult: ...


class NvidiaNimEmbeddingClient:
    def __init__(self, settings: NvidiaNimEmbeddingSettings, *, transport: httpx.BaseTransport | None = None) -> None:
        if not isinstance(settings, NvidiaNimEmbeddingSettings):
            raise_sanitized(EmbeddingConfigurationError("embedding settings have an invalid type"))
        self._settings = settings
        self._endpoint = f"{settings.base_url}/embeddings"
        timeout = httpx.Timeout(settings.read_timeout_seconds, connect=settings.connect_timeout_seconds)
        self._client = httpx.Client(timeout=timeout, transport=transport)

    @classmethod
    def from_environment(cls, *, transport: httpx.BaseTransport | None = None) -> Self:
        return cls(NvidiaNimEmbeddingSettings.from_environment(), transport=transport)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def embed(self, texts: Sequence[str], *, input_type: str | None = None, truncate: str | None = None) -> EmbeddingBatchResult:
        if isinstance(texts, (str, bytes, bytearray)) or not isinstance(texts, Sequence):
            raise_sanitized(EmbeddingResponseError("embedding inputs must be a sequence of strings"))
        values = tuple(texts)
        if not values:
            raise_sanitized(EmbeddingResponseError("embedding input must not be empty"))
        if any(not isinstance(text, str) or not text.strip() for text in values):
            raise_sanitized(EmbeddingResponseError("embedding inputs must be nonblank strings"))
        for name, value in (("input_type", input_type), ("truncate", truncate)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise_sanitized(EmbeddingResponseError(f"{name} must be a nonblank string"))

        payload: dict[str, Any] = {"model": self._settings.model, "input": list(values)}
        if input_type is not None:
            payload["input_type"] = input_type
        if truncate is not None:
            payload["truncate"] = truncate
        request: httpx.Request | None = None
        request_failed = False
        try:
            request = self._client.build_request(
                "POST",
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._settings.api_key.get_secret_value()}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except Exception:
            request_failed = True
        if request_failed:
            raise_sanitized(EmbeddingTransportError("NVIDIA NIM embedding request construction failed"))

        response: httpx.Response | None = None
        timeout = transport_failed = False
        try:
            assert request is not None
            response = self._client.send(request)
        except httpx.TimeoutException:
            timeout = True
        except httpx.RequestError:
            transport_failed = True
        except Exception:
            transport_failed = True
        if timeout:
            raise_sanitized(EmbeddingTimeoutError("NVIDIA NIM embedding request timed out"))
        if transport_failed:
            raise_sanitized(EmbeddingTransportError("NVIDIA NIM embedding request failed"))
        assert response is not None
        if response.status_code in {401, 403}:
            raise_sanitized(EmbeddingAuthenticationError("NVIDIA NIM embedding authentication failed"))
        if response.status_code == 429:
            raise_sanitized(EmbeddingRateLimitError("NVIDIA NIM embedding provider rate limit reached"))
        if not response.is_success:
            raise_sanitized(EmbeddingProviderError(response.status_code))
        invalid_json = False
        try:
            payload = response.json()
        except ValueError:
            invalid_json = True
        if invalid_json:
            raise_sanitized(EmbeddingResponseError("NVIDIA NIM embedding response was not valid JSON"))
        return _parse_response(payload, len(values))


def _parse_response(payload: Any, input_count: int) -> EmbeddingBatchResult:
    invalid = False
    try:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError
        items = payload["data"]
        if len(items) != input_count:
            raise ValueError
        parsed: dict[int, tuple[float, ...]] = {}
        for item in items:
            if not isinstance(item, dict) or isinstance(item.get("index"), bool) or not isinstance(item.get("index"), int):
                raise ValueError
            index = item["index"]
            raw_vector = item.get("embedding")
            if index in parsed or not isinstance(raw_vector, list) or not raw_vector:
                raise ValueError
            vector = tuple(_finite_number(value) for value in raw_vector)
            parsed[index] = vector
        if set(parsed) != set(range(input_count)):
            raise ValueError
        dimension = len(parsed[0])
        if dimension == 0 or any(len(vector) != dimension for vector in parsed.values()):
            raise ValueError
        vectors = tuple(EmbeddingVector(index, parsed[index]) for index in range(input_count))
        model = payload.get("model") if isinstance(payload.get("model"), str) and payload.get("model").strip() else None
        usage = _parse_usage(payload.get("usage"))
        return EmbeddingBatchResult(vectors, dimension, model, usage)
    except (TypeError, ValueError, KeyError):
        invalid = True
    if invalid:
        raise_sanitized(EmbeddingResponseError("NVIDIA NIM embedding response schema is invalid"))
    raise AssertionError("unreachable")


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        raise ValueError
    if not math.isfinite(converted):
        raise ValueError
    return converted


def _parse_usage(value: Any) -> EmbeddingUsage | None:
    if not isinstance(value, dict):
        return None
    prompt = value.get("prompt_tokens")
    total = value.get("total_tokens")
    if any(item is not None and (isinstance(item, bool) or not isinstance(item, int) or item < 0) for item in (prompt, total)):
        return None
    return EmbeddingUsage(prompt, total)
