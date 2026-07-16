from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import psycopg
from qdrant_client import QdrantClient

from ringkas_worker.dimension import verify_live_dimension_from_environment
from ringkas_worker.embedding import CloudflareWorkersAiEmbeddingClient
from ringkas_worker.embedding.config import CloudflareWorkersAiEmbeddingSettings
from ringkas_worker.indexing import (
    ChunkIndexingResult,
    IndexableChunk,
    QdrantChunkIndexer,
    QdrantIndexingSettings,
)
from ringkas_worker.sparse_retrieval import FastEmbedSparseEncoder
from ringkas_worker.logging_config import configure_logging
from ringkas_worker.qdrant_setup import (
    COLLECTION_NAME,
    SCHEMA_VERSION,
    SUPPORTED_DISTANCES,
    QdrantCollectionSetup,
    QdrantSetupSettings,
)


PROVIDER = "cloudflare_workers_ai"
MODEL = "@cf/qwen/qwen3-embedding-0.6b"
CHECKPOINT_VERSION = 1


class ReindexError(Exception):
    code = "reindex_error"


class ReindexCheckpointError(ReindexError):
    code = "reindex_checkpoint_invalid"


class ReindexBatchError(ReindexError):
    code = "reindex_batch_failed"

    def __init__(self, progress: ReindexProgress) -> None:
        super().__init__("reindex batch failed")
        self.progress = progress


@dataclass(frozen=True, slots=True)
class MigrationIdentity:
    provider: str
    model: str
    collection: str
    dimension: int
    distance: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.provider != PROVIDER or self.model != MODEL:
            _raise_checkpoint(ReindexCheckpointError("migration provider or model is not approved"))
        if self.collection != COLLECTION_NAME:
            _raise_checkpoint(ReindexCheckpointError("migration collection is not the versioned target"))
        if isinstance(self.dimension, bool) or not isinstance(self.dimension, int) or self.dimension <= 0:
            _raise_checkpoint(ReindexCheckpointError("migration dimension must be positive"))
        if self.distance not in SUPPORTED_DISTANCES:
            _raise_checkpoint(ReindexCheckpointError("migration distance is unsupported"))
        if self.schema_version != SCHEMA_VERSION:
            _raise_checkpoint(ReindexCheckpointError("migration schema version is unsupported"))

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "collection": self.collection,
            "dimension": self.dimension,
            "distance": self.distance,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ReindexProgress:
    processed: int
    indexed: int
    skipped: int
    total: int | None
    failed: int = 0


@runtime_checkable
class ReindexCheckpoint(Protocol):
    identity: MigrationIdentity

    def is_complete(self, point_id: str) -> bool: ...

    def mark_complete(self, point_ids: Sequence[str]) -> None: ...


class InMemoryReindexCheckpoint:
    def __init__(self, identity: MigrationIdentity, completed: Sequence[str] = ()) -> None:
        self.identity = identity
        self._completed = set(completed)

    def is_complete(self, point_id: str) -> bool:
        return point_id in self._completed

    def mark_complete(self, point_ids: Sequence[str]) -> None:
        self._completed.update(point_ids)


class FileReindexCheckpoint(InMemoryReindexCheckpoint):
    """Atomic checkpoint bound to one embedding migration identity."""

    def __init__(self, path: str, identity: MigrationIdentity) -> None:
        self._path = Path(path)
        completed = self._load(identity)
        super().__init__(identity, completed)

    def _load(self, identity: MigrationIdentity) -> list[str]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError, ValueError):
            _raise_checkpoint(ReindexCheckpointError("reindex checkpoint is corrupt"))
        if (
            not isinstance(payload, dict)
            or set(payload) != {"checkpoint_version", "migration", "completed_ids"}
            or payload["checkpoint_version"] != CHECKPOINT_VERSION
            or payload["migration"] != identity.as_dict()
            or not isinstance(payload["completed_ids"], list)
            or any(not isinstance(item, str) or not item for item in payload["completed_ids"])
            or len(set(payload["completed_ids"])) != len(payload["completed_ids"])
        ):
            _raise_checkpoint(ReindexCheckpointError("reindex checkpoint identity or data is invalid"))
        return payload["completed_ids"]

    def mark_complete(self, point_ids: Sequence[str]) -> None:
        if any(not isinstance(point_id, str) or not point_id for point_id in point_ids):
            _raise_checkpoint(ReindexCheckpointError("reindex checkpoint point ID is invalid"))
        super().mark_complete(point_ids)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "checkpoint_version": CHECKPOINT_VERSION,
                    "migration": self.identity.as_dict(),
                    "completed_ids": sorted(self._completed),
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
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
        processed = indexed = skipped = failed = 0
        for batch in self._source.batches(batch_size):
            pending = tuple(chunk for chunk in batch if not self._checkpoint.is_complete(chunk.qdrant_point_id))
            skipped += len(batch) - len(pending)
            if pending:
                try:
                    result = self._indexer.index(pending)
                    if not isinstance(result, ChunkIndexingResult) or (
                        result.collection_name != self._checkpoint.identity.collection
                        or result.indexed_count != len(pending)
                        or set(result.point_ids) != {chunk.qdrant_point_id for chunk in pending}
                    ):
                        raise ReindexError("reindex upsert result was incomplete")
                    self._checkpoint.mark_complete(result.point_ids)
                except Exception:
                    failed += len(pending)
                    processed += len(batch)
                    state = ReindexProgress(processed, indexed, skipped, None, failed)
                    self._emit(state)
                    _raise_reindex_batch(state)
                indexed += len(pending)
            processed += len(batch)
            self._emit(ReindexProgress(processed, indexed, skipped, None, failed))
        return ReindexProgress(processed, indexed, skipped, None, failed)

    def _emit(self, progress: ReindexProgress) -> None:
        if self._progress is not None:
            self._progress(progress)


class PostgresChunkSource:
    """Reads authoritative text and citation metadata without touching old vectors."""

    def __init__(self, database_url: str, connection_factory: Callable[[], psycopg.Connection] | None = None) -> None:
        self._connection_factory = connection_factory or (lambda: psycopg.connect(database_url))

    def batches(self, batch_size: int) -> Iterator[tuple[IndexableChunk, ...]]:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be positive")
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
    configure_logging()
    logger = logging.getLogger(__name__)
    identity: MigrationIdentity | None = None
    try:
        verified = verify_live_dimension_from_environment()
        embedding_settings = CloudflareWorkersAiEmbeddingSettings.from_environment()
        qdrant_settings = QdrantSetupSettings.from_environment()
        assert qdrant_settings.spec is not None
        if qdrant_settings.spec.dense_size != verified.dimension:
            raise ReindexError("configured and verified dimensions differ")
        identity = MigrationIdentity(
            PROVIDER,
            embedding_settings.model,
            qdrant_settings.spec.collection_name,
            verified.dimension,
            qdrant_settings.spec.dense_distance,
        )
        qdrant = QdrantClient(
            url=qdrant_settings.qdrant_url,
            api_key=qdrant_settings.qdrant_api_key.get_secret_value() or None,
        )
        QdrantCollectionSetup(qdrant).setup(qdrant_settings.spec)
        with CloudflareWorkersAiEmbeddingClient(embedding_settings) as embedding_client:
            sparse_encoder = FastEmbedSparseEncoder.from_environment()
            indexer = QdrantChunkIndexer(
                embedding_client,
                qdrant,
                QdrantIndexingSettings(
                    qdrant_url=qdrant_settings.qdrant_url,
                    qdrant_api_key=qdrant_settings.qdrant_api_key,
                    expected_dense_vector_size=verified.dimension,
                ),
                sparse_encoder,
            )
            result = ReindexRunner(
                PostgresChunkSource(os.environ["DATABASE_URL"]),
                indexer,
                FileReindexCheckpoint(
                    os.getenv("QDRANT_REINDEX_CHECKPOINT_PATH", "/data/ringkas/reindex.json"),
                    identity,
                ),
                lambda progress: logger.info(
                    "reindex progress provider=%s model=%s collection=%s processed=%d indexed=%d skipped=%d failed=%d",
                    identity.provider,
                    identity.model,
                    identity.collection,
                    progress.processed,
                    progress.indexed,
                    progress.skipped,
                    progress.failed,
                ),
            ).run()
        logger.info(
            "reindex state=completed provider=%s model=%s collection=%s processed=%d indexed=%d skipped=%d failed=%d",
            identity.provider,
            identity.model,
            identity.collection,
            result.processed,
            result.indexed,
            result.skipped,
            result.failed,
        )
        return 0
    except ReindexBatchError as error:
        if identity is not None:
            logger.error(
                "reindex state=failed provider=%s model=%s collection=%s processed=%d indexed=%d skipped=%d failed=%d",
                identity.provider,
                identity.model,
                identity.collection,
                error.progress.processed,
                error.progress.indexed,
                error.progress.skipped,
                error.progress.failed,
            )
        else:
            logger.error("reindex state=failed")
        return 2
    except Exception:
        logger.error("reindex state=failed")
        return 2


def _raise_checkpoint(error: ReindexCheckpointError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


def _raise_reindex_batch(progress: ReindexProgress) -> None:
    error = ReindexBatchError(progress)
    error.__cause__ = None
    error.__context__ = None
    raise error


if __name__ == "__main__":
    raise SystemExit(main())
