import os
from datetime import date
from uuid import UUID, uuid4

import psycopg
import pytest

from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.db.documents import DocumentRepository
from ringkas_worker.pdfs import DownloadedPdf


DATABASE_URL = os.getenv("RINGKAS_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="set RINGKAS_POSTGRES_TEST_URL for PostgreSQL integration tests")


def metadata(**overrides) -> PublicationMetadata:
    values = {
        "title": "Repository integration publication",
        "publication_year": 2025,
        "release_date": date(2025, 2, 3),
        "region": "DKI Jakarta",
        "region_level": "province",
        "topic": "Population",
        "catalog_number": "1102001.3171",
        "publication_number": "PUB-2025-01",
        "source_page_url": "https://bps.example.test/publication",
        "pdf_url": "https://files.example.test/publication.pdf",
        "language": "id",
    }
    values.update(overrides)
    return PublicationMetadata(**values)


def pdf(checksum: str) -> DownloadedPdf:
    return DownloadedPdf(checksum, f"/data/ringkas/pdfs/{checksum}.pdf", False)


def cleanup(document_ids: list[UUID], checksums: list[str]) -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("DELETE FROM documents WHERE id = ANY(%s) OR checksum = ANY(%s)", (document_ids, checksums))


def test_new_download_persists_all_metadata_and_timezone_aware_timestamps() -> None:
    checksum = "1" * 64
    repository = DocumentRepository(DATABASE_URL)
    result = repository.persist_download(metadata(), pdf(checksum))
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute(
                """SELECT title, publication_year, release_date, region, region_level, topic,
                   catalog_number, publication_number, source_page_url, pdf_url, local_pdf_path,
                   language, ingestion_status, checksum, created_at, ingested_at
                   FROM documents WHERE id = %s""",
                (result.document_id,),
            ).fetchone()
        assert row is not None
        assert row[:14] == (
            "Repository integration publication", 2025, date(2025, 2, 3), "DKI Jakarta", "province",
            "Population", "1102001.3171", "PUB-2025-01", "https://bps.example.test/publication",
            "https://files.example.test/publication.pdf", f"/data/ringkas/pdfs/{checksum}.pdf", "id",
            "downloaded", checksum,
        )
        assert row[14].tzinfo is not None
        assert row[15].tzinfo is not None
    finally:
        cleanup([result.document_id], [checksum])


def test_existing_checksum_returns_existing_document_without_modification() -> None:
    checksum = "2" * 64
    existing_id = uuid4()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """INSERT INTO documents
               (id, title, publication_year, region, region_level, source_page_url,
                local_pdf_path, ingestion_status, checksum)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (existing_id, "Existing title", 2024, "DKI Jakarta", "province", "https://example.invalid/existing",
             "/data/ringkas/pdfs/existing.pdf", "parsed", checksum),
        )
    try:
        result = DocumentRepository(DATABASE_URL).persist_download(metadata(title="New title"), pdf(checksum))
        assert result.document_id == existing_id
        assert result.is_duplicate is True
        with psycopg.connect(DATABASE_URL) as connection:
            row = connection.execute("SELECT title, ingestion_status, local_pdf_path FROM documents WHERE id = %s", (existing_id,)).fetchone()
        assert row == ("Existing title", "parsed", "/data/ringkas/pdfs/existing.pdf")
    finally:
        cleanup([existing_id], [checksum])


@pytest.mark.parametrize("invalid_metadata", [
    {"title": "x" * 501},
    {"region": "x" * 201},
])
def test_constraint_failure_rolls_back_without_partial_row(invalid_metadata: dict[str, str]) -> None:
    checksum = "3" * 64
    with pytest.raises(psycopg.errors.StringDataRightTruncation):
        DocumentRepository(DATABASE_URL).persist_download(metadata(**invalid_metadata), pdf(checksum))
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute("SELECT count(*) FROM documents WHERE checksum = %s", (checksum,)).fetchone() == (0,)


def test_insert_failure_rolls_back_without_partial_row() -> None:
    checksum = "4" * 64
    invalid = metadata()
    with pytest.raises(psycopg.errors.StringDataRightTruncation):
        DocumentRepository(DATABASE_URL).persist_download(invalid.model_copy(update={"title": "x" * 501}), pdf(checksum))
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute("SELECT count(*) FROM documents WHERE checksum = %s", (checksum,)).fetchone() == (0,)
