from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable
from uuid import UUID

import psycopg


@dataclass(frozen=True, slots=True)
class CitationSourceRecord:
    chunk_id: str
    document_id: str
    qdrant_point_id: str
    chunk_index: int
    chunk_text: str
    page_start: int | None
    page_end: int | None
    section_heading: str | None
    extraction_method: str
    low_structure_confidence: bool
    chunk_source_url: str
    document_title: str
    publication_year: int
    region: str
    region_level: str
    topic: str | None
    pdf_url: str | None
    ingestion_status: str


class CitationRepositoryError(Exception):
    code = "citation_repository_error"


class CitationSourceValidationError(CitationRepositoryError):
    code = "invalid_citation_source_ids"


class CitationSourceLookupError(CitationRepositoryError):
    code = "citation_source_lookup_failed"


ConnectionFactory = Callable[[], psycopg.Connection]


def _raise_safe(error: CitationRepositoryError) -> None:
    error.__cause__ = None
    error.__context__ = None
    raise error


def _uuid(value: object, field_name: str) -> UUID:
    try:
        parsed = (
            value
            if isinstance(value, UUID)
            else UUID(value)
            if isinstance(value, str)
            else None
        )
    except (AttributeError, TypeError, ValueError):
        parsed = None
    if parsed is None:
        _raise_safe(
            CitationSourceValidationError(f"{field_name} must be a canonical UUID")
        )
    return parsed


def _canonical_uuid(value: object, field_name: str) -> str:
    return str(_uuid(value, field_name))


@runtime_checkable
class CitationSourceRepository(Protocol):
    def get_by_chunk_ids(
        self, chunk_ids: Sequence[object]
    ) -> tuple[CitationSourceRecord, ...]: ...


class PostgresCitationSourceRepository:
    def __init__(
        self, database_url: str, connection_factory: ConnectionFactory | None = None
    ) -> None:
        self._connection_factory = connection_factory or (
            lambda: psycopg.connect(database_url)
        )

    def get_by_chunk_ids(
        self, chunk_ids: Sequence[object]
    ) -> tuple[CitationSourceRecord, ...]:
        if isinstance(chunk_ids, (str, bytes, bytearray)) or not isinstance(
            chunk_ids, Sequence
        ):
            _raise_safe(CitationSourceValidationError("chunk IDs must be a sequence"))
        uuid_ids = tuple(_uuid(value, "chunk ID") for value in chunk_ids)
        if len(set(uuid_ids)) != len(uuid_ids):
            _raise_safe(CitationSourceValidationError("chunk IDs must be unique"))
        if not uuid_ids:
            return ()

        try:
            with self._connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT c.id, c.document_id, c.qdrant_point_id, c.chunk_index, c.text, "
                        "c.page_start, c.page_end, c.section_heading, c.extraction_method, "
                        "c.low_structure_confidence, c.source_url, d.title, d.publication_year, "
                        "d.region, d.region_level, d.topic, d.pdf_url, d.ingestion_status "
                        "FROM chunks AS c JOIN documents AS d ON d.id = c.document_id "
                        "WHERE c.id = ANY(%s)",
                        (list(uuid_ids),),
                    )
                    rows = tuple(cursor.fetchall())
        except Exception:
            error = CitationSourceLookupError("citation source lookup failed")
        else:
            error = None
        if error is not None:
            _raise_safe(error)

        records: list[CitationSourceRecord] = []
        seen: set[str] = set()
        try:
            for row in rows:
                record = CitationSourceRecord(
                    _canonical_uuid(row[0], "chunk ID"),
                    _canonical_uuid(row[1], "document ID"),
                    _canonical_uuid(row[2], "Qdrant point ID"),
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    row[8],
                    row[9],
                    row[10],
                    row[11],
                    row[12],
                    row[13],
                    row[14],
                    row[15],
                    row[16],
                    row[17],
                )
                if record.chunk_id in seen:
                    _raise_safe(
                        CitationSourceLookupError(
                            "citation source lookup returned duplicate rows"
                        )
                    )
                seen.add(record.chunk_id)
                records.append(record)
        except CitationRepositoryError:
            raise
        except Exception:
            _raise_safe(
                CitationSourceLookupError(
                    "citation source lookup returned malformed rows"
                )
            )
        return tuple(records)
