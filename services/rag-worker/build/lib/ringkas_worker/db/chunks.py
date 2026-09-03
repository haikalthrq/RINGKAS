from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

import psycopg

from ringkas_worker.chunking import TextChunk


@dataclass(frozen=True, slots=True)
class PersistedChunk:
    id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_heading: str | None
    extraction_method: str
    low_structure_confidence: bool
    source_url: str
    qdrant_point_id: str
    created_at: datetime


class ChunkPersistenceError(Exception):
    """Safe validation or reprocessing conflict while persisting a chunk batch."""


ConnectionFactory = Callable[[], psycopg.Connection]


class ChunkRepository:
    def __init__(self, database_url: str, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connection_factory or (lambda: psycopg.connect(database_url))

    def persist_for_document(self, document_id: UUID, chunks: tuple[TextChunk, ...], source_url: str) -> tuple[PersistedChunk, ...]:
        if not chunks:
            raise ChunkPersistenceError("chunk batch must not be empty")
        incoming = {chunk.chunk_index: chunk for chunk in chunks}
        if len(incoming) != len(chunks):
            raise ChunkPersistenceError("chunk batch contains duplicate indexes")
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, document_id, chunk_index, text, page_start, page_end, section_heading, extraction_method, "
                    "low_structure_confidence, source_url, qdrant_point_id, created_at FROM chunks "
                    "WHERE document_id = %s ORDER BY chunk_index FOR UPDATE",
                    (document_id,),
                )
                existing_by_index = {row[2]: PersistedChunk(*row) for row in cursor.fetchall()}
                if existing_by_index and set(existing_by_index) != set(incoming):
                    raise ChunkPersistenceError("existing chunk indexes conflict with incoming batch")
                persisted: list[PersistedChunk] = []
                for chunk in chunks:
                    existing = existing_by_index.get(chunk.chunk_index)
                    if existing is not None:
                        actual = (existing.text, existing.page_start, existing.page_end, existing.section_heading,
                                  existing.extraction_method, existing.low_structure_confidence, existing.source_url)
                        expected = (chunk.text, chunk.page_start, chunk.page_end, chunk.section_heading,
                                    chunk.extraction_method, False, source_url)
                        if existing.document_id != document_id or actual != expected:
                            raise ChunkPersistenceError("existing chunk metadata conflicts")
                        persisted.append(existing)
                        continue
                    chunk_id, point_id, created_at = uuid4(), str(uuid4()), datetime.now(timezone.utc)
                    cursor.execute(
                        "INSERT INTO chunks (id, document_id, chunk_index, text, page_start, page_end, section_heading, "
                        "extraction_method, low_structure_confidence, source_url, qdrant_point_id, created_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (chunk_id, document_id, chunk.chunk_index, chunk.text, chunk.page_start, chunk.page_end,
                         chunk.section_heading, chunk.extraction_method, False, source_url, point_id, created_at),
                    )
                    persisted.append(PersistedChunk(chunk_id, document_id, chunk.chunk_index, chunk.text,
                                                    chunk.page_start, chunk.page_end, chunk.section_heading,
                                                    chunk.extraction_method, False, source_url, point_id, created_at))
                return tuple(persisted)
