from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

import psycopg

from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.pdfs import DownloadedPdf


@dataclass(frozen=True, slots=True)
class PersistedDocument:
    document_id: UUID
    checksum: str
    local_pdf_path: str
    is_duplicate: bool
    status: str = "downloaded"


ConnectionFactory = Callable[[], psycopg.Connection]


class DocumentRepository:
    def __init__(self, database_url: str, connection_factory: ConnectionFactory | None = None) -> None:
        self._database_url = database_url
        self._connection_factory = connection_factory or (lambda: psycopg.connect(database_url))

    def persist_download(self, publication: PublicationMetadata, pdf: DownloadedPdf) -> PersistedDocument:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, local_pdf_path, ingestion_status FROM documents WHERE checksum = %s ORDER BY created_at ASC, id ASC LIMIT 1 FOR UPDATE",
                    (pdf.checksum,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    status = existing[2] if len(existing) > 2 else "downloaded"
                    return PersistedDocument(existing[0], pdf.checksum, existing[1] or pdf.local_pdf_path, True, status)
                document_id = uuid4()
                cursor.execute(
                    """
                    INSERT INTO documents
                    (id, title, publication_year, release_date, region, region_level, topic,
                     catalog_number, publication_number, source_page_url, pdf_url, local_pdf_path,
                     language, ingestion_status, checksum, created_at, ingested_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (document_id, publication.title, publication.publication_year, publication.release_date,
                     publication.region, publication.region_level, publication.topic, publication.catalog_number,
                     publication.publication_number, str(publication.source_page_url), str(publication.pdf_url),
                     pdf.local_pdf_path, publication.language, "downloaded", pdf.checksum,
                     datetime.now(timezone.utc), datetime.now(timezone.utc)),
                )
                return PersistedDocument(document_id, pdf.checksum, pdf.local_pdf_path, False, "downloaded")

    def mark_parsed(self, document_id: UUID, page_count: int) -> bool:
        return self._mark(document_id, "parsed", page_count=page_count, allowed=("downloaded", "parsed"))

    def mark_indexed(self, document_id: UUID) -> bool:
        return self._mark(document_id, "indexed", allowed=("parsed", "indexed"))

    def mark_failed(self, document_id: UUID, safe_error_message: str) -> bool:
        return self._mark(document_id, "failed", error_message=_safe_message(safe_error_message), allowed=("downloaded", "parsed", "failed"))

    def mark_unsupported(self, document_id: UUID, safe_failure_code: str, page_count: int | None = None) -> bool:
        return self._mark(document_id, "unsupported_or_extraction_failed", page_count=page_count,
                          error_message=_safe_message(safe_failure_code), allowed=("downloaded", "parsed", "unsupported_or_extraction_failed"))

    def get_status(self, document_id: UUID) -> str | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT ingestion_status FROM documents WHERE id = %s", (document_id,))
                row = cursor.fetchone()
                return row[0] if row else None

    def _mark(self, document_id: UUID, status: str, *, page_count: int | None = None,
              error_message: str | None = None, allowed: tuple[str, ...]) -> bool:
        completed_at = datetime.now(timezone.utc) if status in {"indexed", "failed", "unsupported_or_extraction_failed"} else None
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE documents
                       SET ingestion_status = %s, page_count = COALESCE(%s, page_count),
                           error_message = %s, ingested_at = COALESCE(%s, ingested_at)
                       WHERE id = %s AND ingestion_status = ANY(%s)""",
                    (status, page_count, error_message, completed_at, document_id, list(allowed)),
                )
                return cursor.rowcount == 1


def _safe_message(value: str) -> str:
    normalized = " ".join(value.split())[:2000]
    if not normalized:
        return "document_processing_failed"
    if re.search(r"(?i)(traceback|authorization|bearer|api[_-]?key|database[_-]?url|password|secret|postgres(?:ql)?://)", normalized):
        return "document_processing_failed"
    return normalized
