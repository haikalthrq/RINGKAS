from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import psycopg
from pydantic import SecretStr
from qdrant_client import QdrantClient

from ringkas_worker.dimension import verify_live_dimension_from_environment
from ringkas_worker.embedding import CloudflareWorkersAiEmbeddingClient
from ringkas_worker.embedding.config import CloudflareWorkersAiEmbeddingSettings
from ringkas_worker.indexing import IndexableChunk, QdrantChunkIndexer
from ringkas_worker.indexing import QdrantIndexingSettings
from ringkas_worker.qdrant_setup import QdrantCollectionSetup, QdrantSetupSpec


@dataclass(frozen=True, slots=True)
class ReindexProgress:
    processed: int
    indexed: int
    skipped: int
    total: int | None


@runtime_checkable
class ReindexCheckpoint(Protocol):
    def is_complete(self, point_id: str) -> bool: ...
    def mark_complete(self, point_ids: Sequence[str]) -> None: ...


class InMemoryReindexCheckpoint:
    def __init__(self, completed: Sequence[str] = ()) -> None:
        self._completed = set(completed)

    def is_complete(self, point_id: str) -> bool:
        return point_id in self._completed

    def mark_complete(self, point_ids: Sequence[str]) -> None:
        self._completed.update(point_ids)


class FileReindexCheckpoint(InMemoryReindexCheckpoint):
    """Atomic checkpoint makes a rerun skip already completed point IDs."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        completed: list[str] = []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
                completed = payload
        except (FileNotFoundError, OSError, ValueError):
            pass
        super().__init__(completed)

    def mark_complete(self, point_ids: Sequence[str]) -> None:
        super().mark_complete(point_ids)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(sorted(self._completed)), encoding="utf-8")
        temporary.replace(self._path)


@runtime_checkable
class ReindexChunkSource(Protocol):
    def batches(self, batch_size: int) -> Iterator[tuple[IndexableChunk, ...]]: ...


class ReindexRunner:
    def __init__(
        self,
        source: ReindexChunkSource,
        indexer: QdrantChunkIndexer,
        checkpoint: ReindexCheckpoint,
        progress: Callable[[ReindexProgress], None] | None = None,
    ) -> None:
        self._source, self._indexer, self._checkpoint, self._progress = source, indexer, checkpoint, progress

    def run(self, *, batch_size: int = 64) -> ReindexProgress:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be positive")
        processed = indexed = skipped = 0
        for batch in self._source.batches(batch_size):
            pending = tuple(chunk for chunk in batch if not self._checkpoint.is_complete(chunk.qdrant_point_id))
            skipped += len(batch) - len(pending)
            if pending:
                result = self._indexer.index(pending)
                self._checkpoint.mark_complete(result.point_ids)
                indexed += result.indexed_count
            processed += len(batch)
            state = ReindexProgress(processed, indexed, skipped, None)
            if self._progress is not None:
                self._progress(state)
        return ReindexProgress(processed, indexed, skipped, None)


class PostgresChunkSource:
    """Reads authoritative text and citation metadata without touching old vectors."""

    def __init__(self, database_url: str, connection_factory: Callable[[], psycopg.Connection] | None = None) -> None:
        self._connection_factory = connection_factory or (lambda: psycopg.connect(database_url))

    def batches(self, batch_size: int) -> Iterator[tuple[IndexableChunk, ...]]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT c.qdrant_point_id, c.id, c.document_id, c.text, d.title, d.publication_year, "
                    "d.region, d.region_level, d.topic, c.page_start, c.page_end, c.section_heading, "
                    "c.chunk_index, c.extraction_method, c.low_structure_confidence, c.source_url, d.pdf_url "
                    "FROM chunks c JOIN documents d ON d.id = c.document_id ORDER BY c.document_id, c.chunk_index"
                )
                batch: list[IndexableChunk] = []
                for row in cursor:
                    batch.append(IndexableChunk(*row))
                    if len(batch) == batch_size:
                        yield tuple(batch)
                        batch.clear()
                if batch:
                    yield tuple(batch)


def main() -> int:
    logger = logging.getLogger(__name__)
    try:
        verified = verify_live_dimension_from_environment()
        embedding_settings = CloudflareWorkersAiEmbeddingSettings.from_environment()
        qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
        collection_name = "ringkas_chunks_cf_qwen3_embedding_v1"
        spec = QdrantSetupSpec(verified.dimension, os.getenv("QDRANT_DENSE_DISTANCE", "cosine"), collection_name)
        qdrant = QdrantClient(url=qdrant_url, api_key=os.getenv("QDRANT_API_KEY") or None)
        QdrantCollectionSetup(qdrant).setup(spec)
        indexer = QdrantChunkIndexer(
            CloudflareWorkersAiEmbeddingClient(embedding_settings),
            qdrant,
            QdrantIndexingSettings(
                qdrant_url=qdrant_url,
                qdrant_api_key=SecretStr(os.getenv("QDRANT_API_KEY", "")),
                collection_name=collection_name,
                expected_dense_vector_size=verified.dimension,
            ),
        )
        result = ReindexRunner(
            PostgresChunkSource(os.environ["DATABASE_URL"]),
            indexer,
            FileReindexCheckpoint(os.getenv("QDRANT_REINDEX_CHECKPOINT_PATH", "/data/ringkas/reindex.json")),
            lambda progress: logger.info("reindex progress processed=%d indexed=%d skipped=%d", progress.processed, progress.indexed, progress.skipped),
        ).run()
        logger.info("reindex completed processed=%d indexed=%d skipped=%d", result.processed, result.indexed, result.skipped)
        return 0
    except Exception:
        logger.error("Qdrant reindex failed")
        return 2
