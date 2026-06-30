from __future__ import annotations

import math
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import SecretStr
from qdrant_client import QdrantClient, models

from ringkas_worker.qdrant_setup import COLLECTION_NAME, SPARSE_VECTOR_NAME


class SparseRetrievalError(Exception):
    code = "sparse_retrieval_error"


class SparseRetrievalConfigurationError(SparseRetrievalError):
    code = "invalid_sparse_retrieval_configuration"


class SparseRetrievalQueryError(SparseRetrievalError):
    code = "invalid_sparse_retrieval_query"


class SparseRetrievalTransportError(SparseRetrievalError):
    code = "sparse_retrieval_transport_error"


class SparseRetrievalResponseError(SparseRetrievalError):
    code = "malformed_sparse_retrieval_response"


def _raise_safe(error: SparseRetrievalError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


def _uuid(value: object, name: str) -> str:
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        _raise_safe(SparseRetrievalResponseError(f"{name} must be a UUID"))
    parsed = None
    conversion_failed = False
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        conversion_failed = True
    if conversion_failed or parsed is None:
        _raise_safe(SparseRetrievalResponseError(f"{name} must be a UUID"))
    return str(parsed)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_safe(SparseRetrievalResponseError(f"{name} must be nonblank"))
    return value


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _raise_safe(SparseRetrievalResponseError(f"{name} must be finite numeric"))
    converted = None
    conversion_failed = False
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        conversion_failed = True
    if conversion_failed or converted is None:
        _raise_safe(SparseRetrievalResponseError(f"{name} must be finite numeric"))
    if not math.isfinite(converted):
        _raise_safe(SparseRetrievalResponseError(f"{name} must be finite numeric"))
    return converted


@dataclass(frozen=True, slots=True)
class SparseQuery:
    indices: tuple[int, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if isinstance(self.indices, (str, bytes, bytearray)) or not isinstance(self.indices, Sequence):
            _raise_safe(SparseRetrievalQueryError("sparse indices must be a nonempty sequence"))
        if isinstance(self.values, (str, bytes, bytearray)) or not isinstance(self.values, Sequence):
            _raise_safe(SparseRetrievalQueryError("sparse values must be a nonempty sequence"))
        if not self.indices or not self.values or len(self.indices) != len(self.values):
            _raise_safe(SparseRetrievalQueryError("sparse indices and values must be nonempty and equal length"))
        pairs: list[tuple[int, float]] = []
        seen: set[int] = set()
        for index, value in zip(self.indices, self.values, strict=True):
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                _raise_safe(SparseRetrievalQueryError("sparse indices must be nonnegative integers"))
            if index in seen:
                _raise_safe(SparseRetrievalQueryError("sparse indices must not contain duplicates"))
            seen.add(index)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                _raise_safe(SparseRetrievalQueryError("sparse values must be finite numeric"))
            converted = None
            conversion_failed = False
            try:
                converted = float(value)
            except (OverflowError, TypeError, ValueError):
                conversion_failed = True
            if conversion_failed or converted is None:
                _raise_safe(SparseRetrievalQueryError("sparse values must be finite numeric"))
            if not math.isfinite(converted):
                _raise_safe(SparseRetrievalQueryError("sparse values must be finite numeric"))
            pairs.append((index, converted))
        pairs.sort(key=lambda pair: pair[0])
        object.__setattr__(self, "indices", tuple(index for index, _ in pairs))
        object.__setattr__(self, "values", tuple(value for _, value in pairs))


@dataclass(frozen=True, slots=True)
class SparseRetrievalSettings:
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr = field(default_factory=lambda: SecretStr(""), repr=False)
    collection_name: str = COLLECTION_NAME
    sparse_top_k: int = 20
    sparse_vector_name: str = SPARSE_VECTOR_NAME

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.qdrant_url)
            valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        except (TypeError, ValueError):
            parsed, valid_port = None, False
        if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.hostname is None or not valid_port:
            _raise_safe(SparseRetrievalConfigurationError("QDRANT_URL must be a safe HTTP or HTTPS URL"))
        if not isinstance(self.qdrant_api_key, SecretStr):
            _raise_safe(SparseRetrievalConfigurationError("QDRANT_API_KEY must be secret configuration"))
        if not isinstance(self.collection_name, str) or not self.collection_name.strip():
            _raise_safe(SparseRetrievalConfigurationError("collection name must be nonblank"))
        if self.sparse_vector_name != SPARSE_VECTOR_NAME:
            _raise_safe(SparseRetrievalConfigurationError("sparse vector name must be sparse"))
        if isinstance(self.sparse_top_k, bool) or not isinstance(self.sparse_top_k, int) or self.sparse_top_k <= 0:
            _raise_safe(SparseRetrievalConfigurationError("sparse top-k must be a positive integer"))
        object.__setattr__(self, "collection_name", self.collection_name.strip())

    @classmethod
    def from_environment(cls) -> SparseRetrievalSettings:
        top_k = 20
        conversion_failed = False
        try:
            top_k = int(os.getenv("SPARSE_TOP_K", "20"))
        except (TypeError, ValueError, OverflowError):
            conversion_failed = True
        if conversion_failed:
            _raise_safe(SparseRetrievalConfigurationError("sparse retrieval integer configuration is invalid"))
        return cls(os.getenv("QDRANT_URL", "http://qdrant:6333"), SecretStr(os.getenv("QDRANT_API_KEY", "")), os.getenv("QDRANT_COLLECTION_NAME", COLLECTION_NAME), top_k)


@dataclass(frozen=True, slots=True)
class SparseRetrievalCandidate:
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
class SparseRetrievalResult:
    collection_name: str
    requested_limit: int
    candidates: tuple[SparseRetrievalCandidate, ...]


@runtime_checkable
class SparseRetriever(Protocol):
    def retrieve(self, query: SparseQuery) -> SparseRetrievalResult: ...


@runtime_checkable
class QdrantSparseQueryClient(Protocol):
    def query_points(self, **kwargs: Any) -> Any: ...


class QdrantSparseRetriever:
    def __init__(self, qdrant_client: QdrantSparseQueryClient, settings: SparseRetrievalSettings) -> None:
        if not isinstance(qdrant_client, QdrantSparseQueryClient) or not isinstance(settings, SparseRetrievalSettings):
            _raise_safe(SparseRetrievalConfigurationError("sparse retrieval clients or settings have invalid types"))
        self._qdrant_client, self._settings = qdrant_client, settings

    def retrieve(self, query: SparseQuery) -> SparseRetrievalResult:
        if not isinstance(query, SparseQuery):
            _raise_safe(SparseRetrievalQueryError("sparse query has invalid type"))
        try:
            response = self._qdrant_client.query_points(
                collection_name=self._settings.collection_name,
                query=models.SparseVector(indices=list(query.indices), values=list(query.values)),
                using=SPARSE_VECTOR_NAME,
                limit=self._settings.sparse_top_k,
                with_payload=True,
                with_vectors=False,
                score_threshold=None,
            )
        except Exception:
            error = SparseRetrievalTransportError("Qdrant sparse query failed")
        else:
            error = None
        if error is not None:
            _raise_safe(error)
        return self._parse_response(response)

    def _parse_response(self, response: object) -> SparseRetrievalResult:
        points = getattr(response, "points", None)
        if isinstance(points, (str, bytes, bytearray)) or not isinstance(points, Sequence):
            _raise_safe(SparseRetrievalResponseError("Qdrant response points are invalid"))
        if len(points) > self._settings.sparse_top_k:
            _raise_safe(SparseRetrievalResponseError("Qdrant returned more candidates than requested"))
        candidates: list[SparseRetrievalCandidate] = []
        point_ids: set[str] = set()
        chunk_ids: set[str] = set()
        for rank, point in enumerate(points, 1):
            candidate = self._candidate(point, rank)
            if candidate.qdrant_point_id in point_ids or candidate.chunk_id in chunk_ids:
                _raise_safe(SparseRetrievalResponseError("Qdrant response contains duplicate identifiers"))
            point_ids.add(candidate.qdrant_point_id)
            chunk_ids.add(candidate.chunk_id)
            candidates.append(candidate)
        return SparseRetrievalResult(self._settings.collection_name, self._settings.sparse_top_k, tuple(candidates))

    def _candidate(self, point: object, rank: int) -> SparseRetrievalCandidate:
        if point is None:
            _raise_safe(SparseRetrievalResponseError("Qdrant candidate is invalid"))
        point_id = _uuid(getattr(point, "id", None), "qdrant_point_id")
        score = _finite(getattr(point, "score", None), "score")
        payload = getattr(point, "payload", None)
        if not isinstance(payload, dict):
            _raise_safe(SparseRetrievalResponseError("Qdrant candidate payload is invalid"))
        document_id, chunk_id = _uuid(payload.get("document_id"), "document_id"), _uuid(payload.get("chunk_id"), "chunk_id")
        title, region, region_level, source_url = (_text(payload.get(name), name) for name in ("title", "region", "region_level", "source_url"))
        year, chunk_index, low_confidence = payload.get("publication_year"), payload.get("chunk_index"), payload.get("low_structure_confidence")
        if isinstance(year, bool) or not isinstance(year, int) or year <= 0 or isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0 or not isinstance(low_confidence, bool):
            _raise_safe(SparseRetrievalResponseError("Qdrant citation metadata is invalid"))
        page_start, page_end = payload.get("page_start"), payload.get("page_end")
        if (page_start is None) != (page_end is None) or (page_start is not None and (isinstance(page_start, bool) or not isinstance(page_start, int) or isinstance(page_end, bool) or not isinstance(page_end, int) or page_start <= 0 or page_end < page_start)):
            _raise_safe(SparseRetrievalResponseError("page range is invalid"))
        if payload.get("extraction_method") != "text_layer":
            _raise_safe(SparseRetrievalResponseError("extraction_method must be text_layer"))
        optional = tuple(payload.get(name) for name in ("topic", "section_heading", "pdf_url"))
        if any(value is not None and not isinstance(value, str) for value in optional):
            _raise_safe(SparseRetrievalResponseError("optional citation metadata is invalid"))
        return SparseRetrievalCandidate(rank, score, point_id, chunk_id, document_id, title, year, region, region_level, optional[0], page_start, page_end, optional[1], chunk_index, "text_layer", low_confidence, source_url, optional[2])


def qdrant_client_from_settings(settings: SparseRetrievalSettings) -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value() or None)
