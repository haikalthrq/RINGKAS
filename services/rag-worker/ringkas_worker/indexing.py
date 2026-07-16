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

from ringkas_worker.embedding import (
    CloudflareWorkersAiEmbeddingClient,
    CloudflareWorkersAiEmbeddingSettings,
    EmbeddingBatchResult,
    EmbeddingClient,
)
from ringkas_worker.qdrant_setup import COLLECTION_NAME, DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME
from ringkas_worker.sparse_retrieval import FastEmbedSparseEncoder, SparseEncoder, SparseQuery


class ChunkIndexingError(Exception):
    code = "chunk_indexing_error"


class InvalidIndexableChunkError(ChunkIndexingError):
    code = "invalid_indexable_chunk"


class IndexingConfigurationError(ChunkIndexingError):
    code = "invalid_indexing_configuration"


class EmbeddingIndexingError(ChunkIndexingError):
    code = "embedding_indexing_error"


class EmbeddingValidationError(EmbeddingIndexingError):
    code = "embedding_validation_error"


class EmbeddingIndexingFailure(EmbeddingIndexingError):
    code = "embedding_failure"


class SparseIndexingFailure(ChunkIndexingError):
    code = "sparse_encoding_failure"


class QdrantIndexingTransportError(ChunkIndexingError):
    code = "qdrant_indexing_transport_error"


class QdrantUpsertIncompleteError(ChunkIndexingError):
    code = "qdrant_upsert_incomplete"


def _raise_safe(error: ChunkIndexingError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


def _uuid(value: object, field_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        _raise_safe(InvalidIndexableChunkError(f"{field_name} must be a UUID"))
    parsed: UUID | None = None
    conversion_failed = False
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        conversion_failed = True
    if conversion_failed or parsed is None:
        _raise_safe(InvalidIndexableChunkError(f"{field_name} must be a UUID"))
    return parsed


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _raise_safe(InvalidIndexableChunkError(f"{field_name} must be nonblank"))
    return value


def _convert_vector_value(value: object) -> tuple[float | None, bool]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, True
    converted: float | None = None
    conversion_failed = False
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        conversion_failed = True
    if conversion_failed or converted is None or not math.isfinite(converted):
        return None, True
    return converted, False


@dataclass(frozen=True, slots=True)
class IndexableChunk:
    qdrant_point_id: str | UUID
    chunk_id: str | UUID
    document_id: str | UUID
    text: str
    title: str
    publication_year: int
    region: str
    region_level: str
    topic: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_heading: str | None = None
    chunk_index: int = 0
    extraction_method: str = "text_layer"
    low_structure_confidence: bool = False
    source_url: str = ""
    pdf_url: str | None = None

    def __post_init__(self) -> None:
        point_id = _uuid(self.qdrant_point_id, "qdrant_point_id")
        chunk_id = _uuid(self.chunk_id, "chunk_id")
        document_id = _uuid(self.document_id, "document_id")
        _required_text(self.text, "text")
        _required_text(self.title, "title")
        _required_text(self.region, "region")
        _required_text(self.region_level, "region_level")
        _required_text(self.source_url, "source_url")
        if isinstance(self.publication_year, bool) or not isinstance(self.publication_year, int) or self.publication_year <= 0:
            _raise_safe(InvalidIndexableChunkError("publication_year must be positive"))
        if isinstance(self.chunk_index, bool) or not isinstance(self.chunk_index, int) or self.chunk_index < 0:
            _raise_safe(InvalidIndexableChunkError("chunk_index must be nonnegative"))
        if self.extraction_method != "text_layer":
            _raise_safe(InvalidIndexableChunkError("extraction_method must be text_layer"))
        if not isinstance(self.low_structure_confidence, bool):
            _raise_safe(InvalidIndexableChunkError("low_structure_confidence must be boolean"))
        if (self.page_start is None) != (self.page_end is None):
            _raise_safe(InvalidIndexableChunkError("page_start and page_end must be provided together"))
        if self.page_start is not None and (
            isinstance(self.page_start, bool) or not isinstance(self.page_start, int)
            or isinstance(self.page_end, bool) or not isinstance(self.page_end, int)
            or self.page_start <= 0 or self.page_end <= 0 or self.page_end < self.page_start
        ):
            _raise_safe(InvalidIndexableChunkError("page range is invalid"))
        for value, field_name in ((self.topic, "topic"), (self.section_heading, "section_heading"), (self.pdf_url, "pdf_url")):
            if value is not None and not isinstance(value, str):
                _raise_safe(InvalidIndexableChunkError(f"{field_name} must be text or null"))
        object.__setattr__(self, "qdrant_point_id", str(point_id))
        object.__setattr__(self, "chunk_id", chunk_id)
        object.__setattr__(self, "document_id", document_id)


@dataclass(frozen=True, slots=True)
class QdrantIndexingSettings:
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr = field(default_factory=lambda: SecretStr(""), repr=False)
    collection_name: str = COLLECTION_NAME
    expected_dense_vector_size: int = 0

    def __post_init__(self) -> None:
        parsed = urlsplit(self.qdrant_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            _raise_safe(IndexingConfigurationError("QDRANT_URL must be a safe HTTP or HTTPS URL"))
        try:
            valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        except ValueError:
            valid_port = False
        if parsed.hostname is None or not valid_port:
            _raise_safe(IndexingConfigurationError("QDRANT_URL must be a safe HTTP or HTTPS URL"))
        if not isinstance(self.qdrant_api_key, SecretStr):
            _raise_safe(IndexingConfigurationError("QDRANT_API_KEY must be secret configuration"))
        if not isinstance(self.collection_name, str) or not self.collection_name.strip():
            _raise_safe(IndexingConfigurationError("collection name must be nonblank"))
        if isinstance(self.expected_dense_vector_size, bool) or not isinstance(self.expected_dense_vector_size, int) or self.expected_dense_vector_size <= 0:
            _raise_safe(IndexingConfigurationError("expected dense vector size must be positive"))
        object.__setattr__(self, "collection_name", self.collection_name.strip())
        if self.collection_name != COLLECTION_NAME:
            _raise_safe(IndexingConfigurationError(f"collection name must be {COLLECTION_NAME}"))

    @classmethod
    def from_environment(cls) -> QdrantIndexingSettings:
        raw_size = os.getenv("QDRANT_DENSE_VECTOR_SIZE", "")
        size = 0
        conversion_failed = False
        try:
            size = int(raw_size)
        except (TypeError, ValueError):
            conversion_failed = True
        if conversion_failed:
            _raise_safe(IndexingConfigurationError("QDRANT_DENSE_VECTOR_SIZE must be a positive integer"))
        return cls(
            qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
            qdrant_api_key=SecretStr(os.getenv("QDRANT_API_KEY", "")),
            collection_name=os.getenv("QDRANT_COLLECTION_NAME", COLLECTION_NAME),
            expected_dense_vector_size=size,
        )


@dataclass(frozen=True, slots=True)
class ChunkIndexingResult:
    collection_name: str
    indexed_count: int
    point_ids: tuple[str, ...]
    chunk_ids: tuple[str, ...]


@runtime_checkable
class ChunkIndexer(Protocol):
    def index(self, chunks: Sequence[IndexableChunk], *, input_type: str | None = None, truncate: str | None = None) -> ChunkIndexingResult: ...


@runtime_checkable
class QdrantUpsertClient(Protocol):
    def upsert(self, collection_name: str, points: Sequence[models.PointStruct], wait: bool = True, **kwargs: Any) -> Any: ...


class QdrantChunkIndexer:
    def __init__(
        self,
        embedding_client: EmbeddingClient,
        qdrant_client: QdrantUpsertClient,
        settings: QdrantIndexingSettings,
        sparse_encoder: SparseEncoder,
        *,
        _owned_clients: tuple[object, ...] = (),
    ) -> None:
        if not isinstance(embedding_client, EmbeddingClient) or not isinstance(qdrant_client, QdrantUpsertClient) or not isinstance(sparse_encoder, SparseEncoder):
            _raise_safe(IndexingConfigurationError("indexing clients have invalid types"))
        if not isinstance(settings, QdrantIndexingSettings):
            _raise_safe(IndexingConfigurationError("indexing settings have invalid type"))
        self._embedding_client = embedding_client
        self._qdrant_client = qdrant_client
        self._settings = settings
        self._sparse_encoder = sparse_encoder
        self._owned_clients = _owned_clients

    @classmethod
    def from_environment(cls) -> QdrantChunkIndexer:
        settings = QdrantIndexingSettings.from_environment()
        embedding_settings = CloudflareWorkersAiEmbeddingSettings.from_environment()
        embedding_client = CloudflareWorkersAiEmbeddingClient(embedding_settings)
        try:
            sparse_encoder = FastEmbedSparseEncoder.from_environment()
            qdrant_client = qdrant_client_from_settings(settings)
        except Exception:
            embedding_client.close()
            raise
        return cls(embedding_client, qdrant_client, settings, sparse_encoder, _owned_clients=(embedding_client, qdrant_client))

    def close(self) -> None:
        owned_clients, self._owned_clients = self._owned_clients, ()
        first_error: Exception | None = None
        for client in owned_clients:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as error:
                    if first_error is None:
                        first_error = error
        if first_error is not None:
            raise first_error

    def __enter__(self) -> QdrantChunkIndexer:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def index(self, chunks: Sequence[IndexableChunk], *, input_type: str | None = None, truncate: str | None = None) -> ChunkIndexingResult:
        validated = self._validate_batch(chunks)
        texts = tuple(chunk.text for chunk in validated)
        try:
            embedded = self._embedding_client.embed(texts, input_type=input_type, truncate=truncate)
        except Exception:
            error = EmbeddingIndexingFailure("embedding provider failed")
        else:
            error = None
        if error is not None:
            _raise_safe(error)
        vectors = self._validate_embeddings(embedded, len(validated))
        try:
            sparse_vectors = self._sparse_encoder.encode_documents(texts)
        except Exception:
            _raise_safe(SparseIndexingFailure("sparse encoding failed"))
        if len(sparse_vectors) != len(validated) or any(not isinstance(vector, SparseQuery) for vector in sparse_vectors):
            _raise_safe(SparseIndexingFailure("sparse encoding count is invalid"))
        points = tuple(
            self._point(chunk, vector, sparse_vector)
            for chunk, vector, sparse_vector in zip(validated, vectors, sparse_vectors, strict=True)
        )
        try:
            response = self._qdrant_client.upsert(self._settings.collection_name, list(points), wait=True)
        except Exception:
            error = QdrantIndexingTransportError("Qdrant upsert failed")
        else:
            error = None
        if error is not None:
            _raise_safe(error)
        if not isinstance(response, models.UpdateResult) or response.status is not models.UpdateStatus.COMPLETED:
            _raise_safe(QdrantUpsertIncompleteError("Qdrant upsert did not complete"))
        return ChunkIndexingResult(self._settings.collection_name, len(points), tuple(c.qdrant_point_id for c in validated), tuple(str(c.chunk_id) for c in validated))

    def _validate_batch(self, chunks: Sequence[IndexableChunk]) -> tuple[IndexableChunk, ...]:
        if isinstance(chunks, (str, bytes, bytearray)) or not isinstance(chunks, Sequence) or not chunks:
            _raise_safe(InvalidIndexableChunkError("chunk batch must be a nonempty sequence"))
        if any(not isinstance(chunk, IndexableChunk) for chunk in chunks):
            _raise_safe(InvalidIndexableChunkError("chunk batch contains an invalid item"))
        values = tuple(chunks)
        if len({chunk.qdrant_point_id for chunk in values}) != len(values):
            _raise_safe(InvalidIndexableChunkError("duplicate qdrant point id"))
        if len({chunk.chunk_id for chunk in values}) != len(values):
            _raise_safe(InvalidIndexableChunkError("duplicate chunk id"))
        return values

    def _validate_embeddings(self, result: object, count: int) -> tuple[tuple[float, ...], ...]:
        if not isinstance(result, EmbeddingBatchResult) or len(result.vectors) != count:
            _raise_safe(EmbeddingValidationError("embedding count does not match chunk count"))
        if (
            isinstance(result.dimension, bool)
            or not isinstance(result.dimension, int)
            or result.dimension <= 0
            or result.dimension != self._settings.expected_dense_vector_size
        ):
            _raise_safe(EmbeddingValidationError("declared embedding dimension is invalid"))
        vectors = result.vectors
        if any(vector.index != index for index, vector in enumerate(vectors)):
            _raise_safe(EmbeddingValidationError("embedding indexes do not match chunk order"))
        dimensions = tuple(len(vector.values) for vector in vectors)
        if not dimensions or dimensions[0] <= 0 or len(set(dimensions)) != 1 or any(
            dimension != result.dimension or dimension != self._settings.expected_dense_vector_size for dimension in dimensions
        ):
            _raise_safe(EmbeddingValidationError("embedding dimension does not match configured dense vector size"))
        converted_vectors: list[tuple[float, ...]] = []
        value_conversion_failed = False
        for vector in vectors:
            converted: list[float] = []
            for value in vector.values:
                converted_value, conversion_failed = _convert_vector_value(value)
                if conversion_failed:
                    value_conversion_failed = True
                    continue
                assert converted_value is not None
                converted.append(converted_value)
            converted_vectors.append(tuple(converted))
        if value_conversion_failed:
            _raise_safe(EmbeddingValidationError("embedding contains an invalid vector value"))
        return tuple(converted_vectors)

    @staticmethod
    def _point(chunk: IndexableChunk, vector: tuple[float, ...], sparse_vector: SparseQuery) -> models.PointStruct:
        payload = {
            "document_id": str(chunk.document_id), "chunk_id": str(chunk.chunk_id), "title": chunk.title,
            "publication_year": chunk.publication_year, "region": chunk.region, "region_level": chunk.region_level,
            "topic": chunk.topic, "page_start": chunk.page_start, "page_end": chunk.page_end,
            "section_heading": chunk.section_heading, "chunk_index": chunk.chunk_index,
            "extraction_method": chunk.extraction_method, "low_structure_confidence": chunk.low_structure_confidence,
            "source_url": chunk.source_url, "pdf_url": chunk.pdf_url,
        }
        return models.PointStruct(
            id=chunk.qdrant_point_id,
            vector={
                DENSE_VECTOR_NAME: list(vector),
                SPARSE_VECTOR_NAME: models.SparseVector(
                    indices=list(sparse_vector.indices), values=list(sparse_vector.values)
                ),
            },
            payload=payload,
        )


def qdrant_client_from_settings(settings: QdrantIndexingSettings) -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value() or None)
