from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import SecretStr

from ringkas_worker.embedding.errors import EmbeddingConfigurationError, raise_sanitized


def _safe_base_url(value: str) -> str:
    invalid = False
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        if parsed.query or parsed.fragment:
            raise ValueError
        if parsed.hostname is None:
            raise ValueError
        # Accessing port catches malformed ports without retaining the URL.
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        invalid = True
    if invalid:
        raise_sanitized(EmbeddingConfigurationError("NVIDIA_NIM_BASE_URL must be a safe absolute HTTP or HTTPS URL"))

    path = parsed.path.rstrip("/")
    if path not in {"", "/v1"}:
        raise_sanitized(EmbeddingConfigurationError("NVIDIA_NIM_BASE_URL must be a service origin or /v1 API root"))
    if not path:
        path = "/v1"
    return urlunsplit(SplitResult(parsed.scheme, parsed.netloc, path, "", ""))


def _validated_timeout(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise_sanitized(EmbeddingConfigurationError(f"{name} must be a finite positive number"))
    conversion_failed = False
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        conversion_failed = True
        converted = 0.0
    if conversion_failed:
        raise_sanitized(EmbeddingConfigurationError(f"{name} must be a finite positive number"))
    if not math.isfinite(converted) or converted <= 0:
        raise_sanitized(EmbeddingConfigurationError(f"{name} must be a finite positive number"))
    return converted


@dataclass(frozen=True, slots=True)
class NvidiaNimEmbeddingSettings:
    """Embedding-only configuration; ordinary worker startup does not require it.

    ``base_url`` is the NVIDIA NIM service origin or its ``/v1`` API root.
    The client appends exactly one ``/embeddings`` segment to this normalized root.
    """

    api_key: SecretStr = field(repr=False)
    model: str
    base_url: str
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, SecretStr) or not self.api_key.get_secret_value().strip():
            raise_sanitized(EmbeddingConfigurationError("NVIDIA_NIM_API_KEY is required"))
        if not isinstance(self.model, str) or not self.model.strip():
            raise_sanitized(EmbeddingConfigurationError("NVIDIA_NIM_EMBEDDING_MODEL is required"))
        normalized = _safe_base_url(self.base_url)
        connect_timeout = _validated_timeout(self.connect_timeout_seconds, "connect timeout")
        read_timeout = _validated_timeout(self.read_timeout_seconds, "read timeout")
        object.__setattr__(self, "connect_timeout_seconds", connect_timeout)
        object.__setattr__(self, "read_timeout_seconds", read_timeout)
        object.__setattr__(self, "base_url", normalized)

    @classmethod
    def from_environment(cls) -> NvidiaNimEmbeddingSettings:
        invalid_timeout = False
        try:
            api_key = os.getenv("NVIDIA_NIM_API_KEY", "")
            model = os.getenv("NVIDIA_NIM_EMBEDDING_MODEL", "")
            base_url = os.getenv("NVIDIA_NIM_BASE_URL", "")
            connect = os.getenv("NVIDIA_NIM_EMBEDDING_CONNECT_TIMEOUT_SECONDS", "10")
            read = os.getenv("NVIDIA_NIM_EMBEDDING_READ_TIMEOUT_SECONDS", "60")
        except TypeError:
            invalid_timeout = True
        if invalid_timeout:
            raise_sanitized(EmbeddingConfigurationError("NVIDIA NIM embedding timeout configuration is invalid"))
        conversion_failed = False
        try:
            connect_value = float(connect)
            read_value = float(read)
        except (OverflowError, TypeError, ValueError):
            conversion_failed = True
            connect_value = read_value = 0.0
        if conversion_failed:
            raise_sanitized(EmbeddingConfigurationError("NVIDIA NIM embedding timeout configuration is invalid"))
        return cls(SecretStr(api_key), model, base_url, connect_value, read_value)

    from_env = from_environment


@dataclass(frozen=True, slots=True)
class CloudflareWorkersAiEmbeddingSettings:
    """Configuration for the approved Cloudflare embedding model."""

    account_id: str
    api_token: SecretStr = field(repr=False)
    model: str
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, str) or not self.account_id.strip():
            raise_sanitized(EmbeddingConfigurationError("CLOUDFLARE_ACCOUNT_ID is required"))
        if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in self.account_id):
            raise_sanitized(EmbeddingConfigurationError("CLOUDFLARE_ACCOUNT_ID is invalid"))
        if not isinstance(self.api_token, SecretStr) or not self.api_token.get_secret_value().strip():
            raise_sanitized(EmbeddingConfigurationError("CLOUDFLARE_API_TOKEN is required"))
        if self.model != "@cf/qwen/qwen3-embedding-0.6b":
            raise_sanitized(EmbeddingConfigurationError("CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL is invalid"))
        object.__setattr__(self, "connect_timeout_seconds", _validated_timeout(self.connect_timeout_seconds, "connect timeout"))
        object.__setattr__(self, "read_timeout_seconds", _validated_timeout(self.read_timeout_seconds, "read timeout"))

    @classmethod
    def from_environment(cls) -> CloudflareWorkersAiEmbeddingSettings:
        conversion_failed = False
        try:
            api_token = SecretStr(os.getenv("CLOUDFLARE_API_TOKEN", ""))
            account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
            model = os.getenv("CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL", "")
            connect = float(os.getenv("CLOUDFLARE_WORKERS_AI_EMBEDDING_CONNECT_TIMEOUT_SECONDS", "10"))
            read = float(os.getenv("CLOUDFLARE_WORKERS_AI_EMBEDDING_READ_TIMEOUT_SECONDS", "60"))
        except (OverflowError, TypeError, ValueError):
            conversion_failed = True
            connect = read = 0.0
        if conversion_failed:
            raise_sanitized(EmbeddingConfigurationError("Cloudflare embedding timeout configuration is invalid"))
        return cls(account_id, api_token, model, connect, read)

    from_env = from_environment
