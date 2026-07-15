from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ringkas_worker.embedding import EmbeddingBatchResult, CloudflareWorkersAiEmbeddingClient
from ringkas_worker.embedding.config import CloudflareWorkersAiEmbeddingSettings
from ringkas_worker.embedding.errors import EmbeddingConfigurationError, raise_sanitized


class DimensionVerificationError(Exception):
    code = "embedding_dimension_verification_failed"


@dataclass(frozen=True, slots=True)
class VerifiedEmbeddingDimension:
    model: str
    dimension: int


@runtime_checkable
class DimensionEmbeddingClient(Protocol):
    def embed(self, texts: tuple[str, ...]) -> EmbeddingBatchResult: ...


def verify_embedding_dimension(client: DimensionEmbeddingClient) -> VerifiedEmbeddingDimension:
    """Verify the provider's live output; never derive a dimension from configuration."""
    if not isinstance(client, DimensionEmbeddingClient):
        _fail("dimension verifier client has an invalid type")
    failure = False
    try:
        result = client.embed(("RINGKAS dimension verification sample.", "RINGKAS second sample."))
        vectors = result.vectors
        dimensions = tuple(len(vector.values) for vector in vectors)
        if not vectors or not dimensions or dimensions[0] <= 0 or len(set(dimensions)) != 1:
            raise ValueError
        if result.dimension != dimensions[0] or any(
            not math.isfinite(float(value)) for vector in vectors for value in vector.values
        ):
            raise ValueError
        model = result.model
        if not isinstance(model, str) or not model.strip():
            raise ValueError
        return VerifiedEmbeddingDimension(model=model, dimension=dimensions[0])
    except Exception as error:
        if isinstance(error, DimensionVerificationError):
            raise
        failure = True
    if failure:
        _fail("Cloudflare embedding dimension verification failed")
    raise AssertionError("unreachable")


def verify_live_dimension_from_environment() -> VerifiedEmbeddingDimension:
    try:
        settings = CloudflareWorkersAiEmbeddingSettings.from_environment()
    except EmbeddingConfigurationError:
        _fail("Cloudflare embedding dimension verification is unavailable")
    with CloudflareWorkersAiEmbeddingClient(settings) as client:
        return verify_embedding_dimension(client)


def _fail(message: str) -> None:
    error = DimensionVerificationError(message)
    error.__cause__ = None
    error.__context__ = None
    raise error
