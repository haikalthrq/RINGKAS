from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ringkas_worker.embedding import (
    CloudflareWorkersAiEmbeddingClient,
    EmbeddingBatchResult,
    EmbeddingVector,
)
from ringkas_worker.embedding.config import CloudflareWorkersAiEmbeddingSettings
from ringkas_worker.embedding.errors import EmbeddingConfigurationError


class DimensionVerificationError(Exception):
    code = "embedding_dimension_verification_failed"


APPROVED_EMBEDDING_MODEL = "@cf/qwen/qwen3-embedding-0.6b"


@dataclass(frozen=True, slots=True)
class VerifiedEmbeddingDimension:
    model: str
    dimension: int


@runtime_checkable
class DimensionEmbeddingClient(Protocol):
    def embed(self, texts: tuple[str, ...]) -> EmbeddingBatchResult: ...


def verify_embedding_dimension(
    client: DimensionEmbeddingClient,
    expected_dimension: int | None = None,
) -> VerifiedEmbeddingDimension:
    """Verify the provider's live output; never derive a dimension from configuration."""
    if not isinstance(client, DimensionEmbeddingClient):
        _fail("dimension verifier client has an invalid type")
    failure = False
    try:
        if expected_dimension is not None and (
            isinstance(expected_dimension, bool)
            or not isinstance(expected_dimension, int)
            or expected_dimension <= 0
        ):
            _fail("configured embedding dimension is invalid")
        result = client.embed(("RINGKAS dimension verification sample.", "RINGKAS second sample."))
        if not isinstance(result, EmbeddingBatchResult):
            raise ValueError
        vectors = result.vectors
        if any(not isinstance(vector, EmbeddingVector) for vector in vectors):
            raise ValueError
        dimensions = tuple(len(vector.values) for vector in vectors)
        if not vectors or not dimensions or dimensions[0] <= 0 or len(set(dimensions)) != 1:
            raise ValueError
        if (
            isinstance(result.dimension, bool)
            or not isinstance(result.dimension, int)
            or result.dimension <= 0
            or result.dimension != dimensions[0]
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for vector in vectors
                for value in vector.values
            )
        ):
            raise ValueError
        model = result.model
        if model != APPROVED_EMBEDDING_MODEL:
            raise ValueError
        if expected_dimension is not None and dimensions[0] != expected_dimension:
            _fail("live embedding dimension does not match configuration")
        return VerifiedEmbeddingDimension(model=model, dimension=dimensions[0])
    except DimensionVerificationError:
        raise
    except Exception:
        failure = True
    if failure:
        _fail("Cloudflare embedding dimension verification failed")


def verify_live_dimension_from_environment() -> VerifiedEmbeddingDimension:
    expected_dimension = _expected_dimension_from_environment()
    try:
        settings = CloudflareWorkersAiEmbeddingSettings.from_environment()
    except EmbeddingConfigurationError:
        _fail("Cloudflare embedding dimension verification is unavailable")
    with CloudflareWorkersAiEmbeddingClient(settings) as client:
        return verify_embedding_dimension(client, expected_dimension)


def _expected_dimension_from_environment() -> int:
    raw_dimension = os.getenv("QDRANT_DENSE_VECTOR_SIZE")
    if raw_dimension is None or not raw_dimension.strip():
        _fail("QDRANT_DENSE_VECTOR_SIZE is required for dimension verification")
    try:
        dimension = int(raw_dimension)
    except (TypeError, ValueError):
        _fail("QDRANT_DENSE_VECTOR_SIZE must be a positive integer")
    if dimension <= 0:
        _fail("QDRANT_DENSE_VECTOR_SIZE must be a positive integer")
    return dimension


def _fail(message: str) -> None:
    error = DimensionVerificationError(message)
    error.__cause__ = None
    error.__context__ = None
    raise error
