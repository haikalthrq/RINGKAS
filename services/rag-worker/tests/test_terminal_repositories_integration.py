import os
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
import pytest

from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.chunking import ChunkedDocument, TextChunk
from ringkas_worker.cleaning import CleanedDocument, CleanedPage
from ringkas_worker.db.documents import DocumentRepository
from ringkas_worker.db.chunks import ChunkRepository
from ringkas_worker.db.jobs import IngestionJobRepository
from ringkas_worker.db.jobs import IngestionJob
from ringkas_worker.db.logs import IngestionLogRepository
from ringkas_worker.parsers import PdfPage, PdfPageMetadata, PdfParseResult
from ringkas_worker.pdfs import DownloadedPdf
from ringkas_worker.processor import IngestionProcessor


DATABASE_URL = os.getenv("RINGKAS_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="set RINGKAS_POSTGRES_TEST_URL for PostgreSQL integration tests")


def test_job_terminal_transitions_commit_and_do_not_overwrite_terminal_state() -> None:
    job_id, user_id = uuid4(), f"terminal-test-{uuid4()}"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute('INSERT INTO "AspNetUsers" ("Id", "EmailConfirmed", "PhoneNumberConfirmed", "TwoFactorEnabled", "LockoutEnabled", "AccessFailedCount") VALUES (%s, false, false, false, false, 0)', (user_id,))
        connection.execute("INSERT INTO ingestion_jobs (id, requested_by_user_id, status, scope_region, scope_year_start, scope_year_end, max_documents, created_at) VALUES (%s, %s, 'running', 'DKI Jakarta', 2020, 2026, 1, %s)", (job_id, user_id, datetime.now(timezone.utc)))
    try:
        repository = IngestionJobRepository(DATABASE_URL)
        assert repository.mark_completed(job_id) is True
        assert repository.mark_failed(job_id, "safe failure") is False
        with psycopg.connect(DATABASE_URL) as connection:
            status, completed_at, summary = connection.execute("SELECT status, completed_at, error_summary FROM ingestion_jobs WHERE id = %s", (job_id,)).fetchone()
        assert (status, summary) == ("completed", None)
        assert completed_at.tzinfo is not None
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("DELETE FROM ingestion_jobs WHERE id = %s", (job_id,))
            connection.execute('DELETE FROM "AspNetUsers" WHERE "Id" = %s', (user_id,))


def test_document_terminal_transition_does_not_regress_indexed_record() -> None:
    document_id, checksum = uuid4(), f"terminal-{uuid4()}"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO documents (id, title, publication_year, region, region_level, source_page_url, ingestion_status, checksum) VALUES (%s, 'Terminal fixture', 2025, 'DKI Jakarta', 'province', 'https://example.invalid/source', 'downloaded', %s)", (document_id, checksum))
    try:
        repository = DocumentRepository(DATABASE_URL)
        assert repository.mark_parsed(document_id, 1) is True
        assert repository.mark_indexed(document_id) is True
        assert repository.mark_failed(document_id, "safe failure") is False
        with psycopg.connect(DATABASE_URL) as connection:
            assert connection.execute("SELECT ingestion_status FROM documents WHERE id = %s", (document_id,)).fetchone() == ("indexed",)
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))


def test_chunk_repository_commits_and_reuses_exact_batch_ids() -> None:
    document_id, checksum = uuid4(), f"chunk-terminal-{uuid4()}"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO documents (id, title, publication_year, region, region_level, source_page_url, ingestion_status, checksum) VALUES (%s, 'Chunk fixture', 2025, 'DKI Jakarta', 'province', 'https://example.invalid/source', 'parsed', %s)", (document_id, checksum))
    try:
        repository = ChunkRepository(DATABASE_URL)
        chunks = (TextChunk("source text", 0, 1, 1, "Heading"),)
        first = repository.persist_for_document(document_id, chunks, "https://example.invalid/source")
        second = repository.persist_for_document(document_id, chunks, "https://example.invalid/source")
        assert (first[0].id, first[0].qdrant_point_id) == (second[0].id, second[0].qdrant_point_id)
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))


def test_chunk_repository_rolls_back_all_rows_when_later_insert_fails() -> None:
    document_id, checksum = uuid4(), f"chunk-rollback-{uuid4()}"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("INSERT INTO documents (id, title, publication_year, region, region_level, source_page_url, ingestion_status, checksum) VALUES (%s, 'Chunk rollback fixture', 2025, 'DKI Jakarta', 'province', 'https://example.invalid/source', 'parsed', %s)", (document_id, checksum))
    try:
        repository = ChunkRepository(DATABASE_URL)
        valid = TextChunk("first", 0, 1, 1)
        invalid = TextChunk("second", 1, 1, 1, extraction_method="ocr")
        with pytest.raises(psycopg.errors.CheckViolation):
            repository.persist_for_document(document_id, (valid, invalid), "https://example.invalid/source")
        with psycopg.connect(DATABASE_URL) as connection:
            assert connection.execute("SELECT count(*) FROM chunks WHERE document_id = %s", (document_id,)).fetchone() == (0,)
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))


def test_processor_postgresql_pipeline_persists_job_document_chunks_and_logs() -> None:
    job_id, user_id = uuid4(), f"processor-test-{uuid4()}"
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute('INSERT INTO "AspNetUsers" ("Id", "EmailConfirmed", "PhoneNumberConfirmed", "TwoFactorEnabled", "LockoutEnabled", "AccessFailedCount") VALUES (%s, false, false, false, false, 0)', (user_id,))
        connection.execute("INSERT INTO ingestion_jobs (id, requested_by_user_id, status, scope_region, scope_year_start, scope_year_end, max_documents, created_at) VALUES (%s, %s, 'running', 'DKI Jakarta', 2020, 2026, 1, %s)", (job_id, user_id, datetime.now(timezone.utc)))
    publication = PublicationMetadata(title="Processor integration", publication_year=2025, region="DKI Jakarta", region_level="province", source_page_url="https://bps.example/source", pdf_url="https://files.example/document.pdf")
    job = IngestionJob(job_id, user_id, "running", "DKI Jakarta", 2020, 2026, 1, datetime.now(timezone.utc), None, datetime.now(timezone.utc), None)
    page = PdfPage(1, "Integration source text", PdfPageMetadata(100, 100, 0))

    class Source:
        def fetch_publications(self): return [publication]
    class Downloader:
        def download(self, _publication): return DownloadedPdf("integration-" + str(job_id), "/tmp/integration.pdf", False)
    class Parser:
        def parse(self, _path): return PdfParseResult("parsed", (page,))
    class Cleaner:
        def clean(self, parsed): return CleanedDocument((CleanedPage(1, parsed.pages[0].text, parsed.pages[0].metadata),))
    class Chunker:
        def chunk(self, _cleaned): return ChunkedDocument((TextChunk("Integration source text", 0, 1, 1),))
    class Indexer:
        def index(self, _chunks): return None

    jobs = IngestionJobRepository(DATABASE_URL)
    documents = DocumentRepository(DATABASE_URL)
    chunks = ChunkRepository(DATABASE_URL)
    logs = IngestionLogRepository(DATABASE_URL)
    processor = IngestionProcessor(publications=Source(), downloader=Downloader(), parser=Parser(), cleaner=Cleaner(), chunker=Chunker(), indexer=Indexer(), jobs=jobs, documents=documents, chunks=chunks, logs=logs)
    try:
        processor.process(job)
        with psycopg.connect(DATABASE_URL) as connection:
            status = connection.execute("SELECT status FROM ingestion_jobs WHERE id = %s", (job_id,)).fetchone()[0]
            document_id, document_status = connection.execute("SELECT id, ingestion_status FROM documents WHERE checksum = %s", ("integration-" + str(job_id),)).fetchone()
            chunk_count = connection.execute("SELECT count(*) FROM chunks WHERE document_id = %s", (document_id,)).fetchone()[0]
            log_count = connection.execute("SELECT count(*) FROM ingestion_logs WHERE job_id = %s", (job_id,)).fetchone()[0]
        assert status == "completed"
        assert document_status == "indexed"
        assert chunk_count == 1
        assert log_count >= 3
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("DELETE FROM ingestion_logs WHERE job_id = %s", (job_id,))
            connection.execute("DELETE FROM ingestion_jobs WHERE id = %s", (job_id,))
            connection.execute("DELETE FROM documents WHERE checksum = %s", ("integration-" + str(job_id),))
            connection.execute('DELETE FROM "AspNetUsers" WHERE "Id" = %s', (user_id,))
