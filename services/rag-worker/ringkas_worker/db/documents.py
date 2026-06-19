from __future__ import annotations

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


ConnectionFactory = Callable[[], psycopg.Connection]


class DocumentRepository:
    def __init__(self, database_url: str, connection_factory: ConnectionFactory | None = None) -> None:
        self._database_url = database_url
        self._connection_factory = connection_factory or (lambda: psycopg.connect(database_url))

    def persist_download(self, publication: PublicationMetadata, pdf: DownloadedPdf) -> PersistedDocument:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, local_pdf_path FROM documents WHERE checksum = %s ORDER BY created_at ASC, id ASC LIMIT 1 FOR UPDATE",
                    (pdf.checksum,),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    return PersistedDocument(existing[0], pdf.checksum, existing[1] or pdf.local_pdf_path, True)
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
                return PersistedDocument(document_id, pdf.checksum, pdf.local_pdf_path, False)
