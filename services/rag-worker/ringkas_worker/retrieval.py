from __future__ import annotations

import math
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import SecretStr
from qdrant_client import QdrantClient

from ringkas_worker.embedding import (
    CloudflareWorkersAiEmbeddingClient,
    CloudflareWorkersAiEmbeddingSettings,
    EmbeddingBatchResult,
    EmbeddingClient,
)
from ringkas_worker.qdrant_setup import COLLECTION_NAME, DENSE_VECTOR_NAME


class DenseRetrievalError(Exception):
    code = "dense_retrieval_error"


class DenseRetrievalConfigurationError(DenseRetrievalError):
    code = "invalid_dense_retrieval_configuration"


class DenseRetrievalQueryError(DenseRetrievalError):
    code = "invalid_dense_retrieval_query"


class DenseRetrievalEmbeddingError(DenseRetrievalError):
    code = "dense_retrieval_embedding_error"


class DenseRetrievalEmbeddingValidationError(DenseRetrievalEmbeddingError):
    code = "dense_retrieval_embedding_validation_error"


class DenseRetrievalTransportError(DenseRetrievalError):
    code = "dense_retrieval_transport_error"


class DenseRetrievalResponseError(DenseRetrievalError):
    code = "malformed_dense_retrieval_response"


def _raise_safe(error: DenseRetrievalError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


def _uuid(value: object, field_name: str) -> str:
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        _raise_safe(DenseRetrievalResponseError(f"{field_name} must be a UUID"))
    parsed: UUID | None = None
    conversion_failed = False
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        conversion_failed = True
    if conversion_failed or parsed is None:
        _raise_safe(DenseRetrievalResponseError(f"{field_name} must be a UUID"))
    return str(parsed)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_safe(DenseRetrievalResponseError(f"{field_name} must be nonblank"))
    return value


def _finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise_safe(DenseRetrievalResponseError(f"{field_name} must be finite numeric"))
    converted: float | None = None
    conversion_failed = False
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        conversion_failed = True
    if conversion_failed or converted is None or not math.isfinite(converted):
        _raise_safe(DenseRetrievalResponseError(f"{field_name} must be finite numeric"))
    return converted


def _vector_value(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise_safe(DenseRetrievalEmbeddingValidationError("query embedding contains an invalid value"))
    converted: float | None = None
    conversion_failed = False
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        conversion_failed = True
    if conversion_failed or converted is None or not math.isfinite(converted):
        _raise_safe(DenseRetrievalEmbeddingValidationError("query embedding contains an invalid value"))
    return converted


@dataclass(frozen=True, slots=True)
class DenseRetrievalSettings:
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr = field(default_factory=lambda: SecretStr(""), repr=False)
    collection_name: str = COLLECTION_NAME
    expected_dense_vector_size: int = 0
    dense_top_k: int = 20

    def __post_init__(self) -> None:
        parsed = None
        url_parse_failed = False
        try:
            parsed = urlsplit(self.qdrant_url)
        except (TypeError, ValueError):
            url_parse_failed = True
        if url_parse_failed or parsed is None:
            _raise_safe(DenseRetrievalConfigurationError("QDRANT_URL must be a safe HTTP or HTTPS URL"))
        valid_port = False
        port_parse_failed = False
        try:
            valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        except ValueError:
            port_parse_failed = True
        if port_parse_failed or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.hostname is None or not valid_port:
            _raise_safe(DenseRetrievalConfigurationError("QDRANT_URL must be a safe HTTP or HTTPS URL"))
        if not isinstance(self.qdrant_api_key, SecretStr):
            _raise_safe(DenseRetrievalConfigurationError("QDRANT_API_KEY must be secret configuration"))
        if not isinstance(self.collection_name, str) or not self.collection_name.strip():
            _raise_safe(DenseRetrievalConfigurationError("collection name must be nonblank"))
        for value, name in ((self.expected_dense_vector_size, "expected dense vector size"), (self.dense_top_k, "dense top-k")):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                _raise_safe(DenseRetrievalConfigurationError(f"{name} must be a positive integer"))
        object.__setattr__(self, "collection_name", self.collection_name.strip())
        if self.collection_name != COLLECTION_NAME:
            _raise_safe(DenseRetrievalConfigurationError(f"collection name must be {COLLECTION_NAME}"))

    @classmethod
    def from_environment(cls) -> DenseRetrievalSettings:
        size = 0
        top_k = 20
        integer_parse_failed = False
        try:
            size = int(os.getenv("QDRANT_DENSE_VECTOR_SIZE", "0"))
            top_k = int(os.getenv("DENSE_TOP_K", "20"))
        except (TypeError, ValueError, OverflowError):
            integer_parse_failed = True
        if integer_parse_failed:
            _raise_safe(DenseRetrievalConfigurationError("dense retrieval integer configuration is invalid"))
        return cls(
            qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
            qdrant_api_key=SecretStr(os.getenv("QDRANT_API_KEY", "")),
            collection_name=os.getenv("QDRANT_COLLECTION_NAME", COLLECTION_NAME),
            expected_dense_vector_size=size,
            dense_top_k=top_k,
        )


@dataclass(frozen=True, slots=True)
class DenseRetrievalCandidate:
    rank: int
    score: float
    qdrant_point_id: str
    chunk_id: str
    document_id: str
    title: str
    publication_year: int
    region: str
    region_level: str
    topic: str | None
    page_start: int | None
    page_end: int | None
    section_heading: str | None
    chunk_index: int
    extraction_method: str
    low_structure_confidence: bool
    source_url: str
    pdf_url: str | None


@dataclass(frozen=True, slots=True)
class DenseRetrievalResult:
    collection_name: str
    requested_limit: int
    candidates: tuple[DenseRetrievalCandidate, ...]


@runtime_checkable
class DenseRetriever(Protocol):
    def retrieve(self, query: str, *, input_type: str | None = None, truncate: str | None = None) -> DenseRetrievalResult: ...


@runtime_checkable
class QdrantQueryClient(Protocol):
    def query_points(self, **kwargs: Any) -> Any: ...


class QdrantDenseRetriever:
    def __init__(
        self,
        embedding_client: EmbeddingClient,
        qdrant_client: QdrantQueryClient,
        settings: DenseRetrievalSettings,
        *,
        _owned_clients: tuple[object, ...] = (),
    ) -> None:
        if not isinstance(embedding_client, EmbeddingClient) or not isinstance(qdrant_client, QdrantQueryClient):
            _raise_safe(DenseRetrievalConfigurationError("retrieval clients have invalid types"))
        if not isinstance(settings, DenseRetrievalSettings):
            _raise_safe(DenseRetrievalConfigurationError("retrieval settings have invalid type"))
        self._embedding_client = embedding_client
        self._qdrant_client = qdrant_client
        self._settings = settings
        self._owned_clients = _owned_clients

    @classmethod
    def from_environment(cls) -> QdrantDenseRetriever:
        settings = DenseRetrievalSettings.from_environment()
        embedding_settings = CloudflareWorkersAiEmbeddingSettings.from_environment()
        embedding_client = CloudflareWorkersAiEmbeddingClient(embedding_settings)
        try:
            qdrant_client = qdrant_client_from_settings(settings)
        except Exception:
            embedding_client.close()
            raise
        return cls(embedding_client, qdrant_client, settings, _owned_clients=(embedding_client, qdrant_client))

    def close(self) -> None:
        owned_clients, self._owned_clients = self._owned_clients, ()
        for client in owned_clients:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def __enter__(self) -> QdrantDenseRetriever:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def retrieve(self, query: str, *, input_type: str | None = None, truncate: str | None = None) -> DenseRetrievalResult:
        if not isinstance(query, str):
            _raise_safe(DenseRetrievalQueryError("query must be a string"))
        if not query.strip():
            _raise_safe(DenseRetrievalQueryError("query must be nonblank"))
        try:
            embedded = self._embedding_client.embed((query,), input_type=input_type, truncate=truncate)
        except Exception:
            embedding_error = DenseRetrievalEmbeddingError("query embedding failed")
        else:
            embedding_error = None
        if embedding_error is not None:
            _raise_safe(embedding_error)
        vector = self._validate_embedding(embedded)
        try:
            response = self._qdrant_client.query_points(
                collection_name=self._settings.collection_name,
                query=list(vector),
                using=DENSE_VECTOR_NAME,
                limit=self._settings.dense_top_k,
                with_payload=True,
                with_vectors=False,
                score_threshold=None,
            )
        except Exception:
            transport_error = DenseRetrievalTransportError("Qdrant dense query failed")
        else:
            transport_error = None
        if transport_error is not None:
            _raise_safe(transport_error)
        return self._parse_response(response)

    def _validate_embedding(self, result: object) -> tuple[float, ...]:
        if not isinstance(result, EmbeddingBatchResult) or len(result.vectors) != 1:
            _raise_safe(DenseRetrievalEmbeddingValidationError("query embedding must contain exactly one vector"))
        if result.vectors[0].index != 0:
            _raise_safe(DenseRetrievalEmbeddingValidationError("query embedding index must be zero"))
        if isinstance(result.dimension, bool) or not isinstance(result.dimension, int) or result.dimension != self._settings.expected_dense_vector_size or result.dimension <= 0:
            _raise_safe(DenseRetrievalEmbeddingValidationError("query embedding dimension is invalid"))
        values = result.vectors[0].values
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)) or len(values) != result.dimension:
            _raise_safe(DenseRetrievalEmbeddingValidationError("query embedding dimension does not match configured size"))
        return tuple(_vector_value(value) for value in values)

    def _parse_response(self, response: object) -> DenseRetrievalResult:
        points = getattr(response, "points", None)
        if isinstance(points, (str, bytes, bytearray)) or not isinstance(points, Sequence):
            _raise_safe(DenseRetrievalResponseError("Qdrant response points are invalid"))
        if len(points) > self._settings.dense_top_k:
            _raise_safe(DenseRetrievalResponseError("Qdrant returned more candidates than requested"))
        candidates: list[DenseRetrievalCandidate] = []
        point_ids: set[str] = set()
        chunk_ids: set[str] = set()
        for rank, point in enumerate(points, 1):
            candidate = self._candidate(point, rank)
            if candidate.qdrant_point_id in point_ids or candidate.chunk_id in chunk_ids:
                _raise_safe(DenseRetrievalResponseError("Qdrant response contains duplicate identifiers"))
            point_ids.add(candidate.qdrant_point_id)
            chunk_ids.add(candidate.chunk_id)
            candidates.append(candidate)
        return DenseRetrievalResult(self._settings.collection_name, self._settings.dense_top_k, tuple(candidates))

    def _candidate(self, point: object, rank: int) -> DenseRetrievalCandidate:
        if point is None:
            _raise_safe(DenseRetrievalResponseError("Qdrant candidate is invalid"))
        point_id = _uuid(getattr(point, "id", None), "qdrant_point_id")
        score = _finite(getattr(point, "score", None), "score")
        payload = getattr(point, "payload", None)
        if not isinstance(payload, dict):
            _raise_safe(DenseRetrievalResponseError("Qdrant candidate payload is invalid"))
        document_id = _uuid(payload.get("document_id"), "document_id")
        chunk_id = _uuid(payload.get("chunk_id"), "chunk_id")
        title = _text(payload.get("title"), "title")
        region = _text(payload.get("region"), "region")
        region_level = _text(payload.get("region_level"), "region_level")
        source_url = _text(payload.get("source_url"), "source_url")
        year = payload.get("publication_year")
        chunk_index = payload.get("chunk_index")
        if isinstance(year, bool) or not isinstance(year, int) or year <= 0:
            _raise_safe(DenseRetrievalResponseError("publication_year must be positive"))
        if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
            _raise_safe(DenseRetrievalResponseError("chunk_index must be nonnegative"))
        low_confidence = payload.get("low_structure_confidence")
        if not isinstance(low_confidence, bool):
            _raise_safe(DenseRetrievalResponseError("low_structure_confidence must be boolean"))
        page_start, page_end = payload.get("page_start"), payload.get("page_end")
        if (page_start is None) != (page_end is None) or (page_start is not None and (isinstance(page_start, bool) or not isinstance(page_start, int) or isinstance(page_end, bool) or not isinstance(page_end, int) or page_start <= 0 or page_end <= 0 or page_end < page_start)):
            _raise_safe(DenseRetrievalResponseError("page range is invalid"))
        if payload.get("extraction_method") != "text_layer":
            _raise_safe(DenseRetrievalResponseError("extraction_method must be text_layer"))
        for value, name in ((payload.get("topic"), "topic"), (payload.get("section_heading"), "section_heading"), (payload.get("pdf_url"), "pdf_url")):
            if value is not None and not isinstance(value, str):
                _raise_safe(DenseRetrievalResponseError(f"{name} must be text or null"))
        return DenseRetrievalCandidate(rank, score, point_id, chunk_id, document_id, title, year, region, region_level, payload.get("topic"), page_start, page_end, payload.get("section_heading"), chunk_index, "text_layer", low_confidence, source_url, payload.get("pdf_url"))


def qdrant_client_from_settings(settings: DenseRetrievalSettings) -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value() or None)
