from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.chunking import TextChunker
from ringkas_worker.cleaning import TextCleaner
from ringkas_worker.db.chunks import ChunkRepository, PersistedChunk
from ringkas_worker.db.documents import DocumentRepository, PersistedDocument
from ringkas_worker.db.jobs import IngestionJob, IngestionJobRepository
from ringkas_worker.db.logs import IngestionLogRepository
from ringkas_worker.indexing import ChunkIndexer, IndexableChunk
from ringkas_worker.parsers import PdfParser

DocumentOutcome = Literal["indexed", "skipped", "unsupported", "failed"]


class ProcessorSystemicError(Exception):
    """A safe public processor failure with no retained provider/database details."""


@runtime_checkable
class PublicationSource(Protocol):
    def fetch_publications(self) -> list[PublicationMetadata]: ...


@runtime_checkable
class PdfSource(Protocol):
    def download(self, publication: PublicationMetadata): ...


class IngestionProcessor:
    """Injectable, fail-closed orchestration for one already-claimed job."""

    def __init__(self, *, publications: PublicationSource, downloader: PdfSource, parser: PdfParser,
                 cleaner: TextCleaner, chunker: TextChunker, indexer: ChunkIndexer,
                 jobs: IngestionJobRepository, documents: DocumentRepository, chunks: ChunkRepository,
                 logs: IngestionLogRepository, approved_region_level: str = "province") -> None:
        self.publications = publications
        self.downloader = downloader
        self.parser = parser
        self.cleaner = cleaner
        self.chunker = chunker
        self.indexer = indexer
        self.jobs = jobs
        self.documents = documents
        self.chunks = chunks
        self.logs = logs
        self.approved_region_level = approved_region_level.strip().casefold()

    def __call__(self, job: IngestionJob) -> None:
        self.process(job)

    def process(self, job: IngestionJob) -> None:
        failure: ProcessorSystemicError | None = None
        if not self._log(job, "info", "Ingestion job started", "job_start"):
            failure = ProcessorSystemicError("required ingestion logging failed")
        publications: list[PublicationMetadata] = []
        if failure is None:
            try:
                publications = self.publications.fetch_publications()
            except Exception:
                failure = ProcessorSystemicError("publication enumeration failed")
        selected: list[PublicationMetadata] = []
        if failure is None:
            try:
                selected = self._select(publications, job)
            except Exception:
                failure = ProcessorSystemicError("invalid ingestion scope")
        counts = {"indexed": 0, "skipped": 0, "unsupported": 0, "failed": 0}
        if failure is None:
            for publication in selected:
                try:
                    outcome = self._process_document(job, publication)
                except ProcessorSystemicError as error:
                    failure = error
                    break
                counts[outcome] += 1
        if failure is None:
            summary = self._summary(counts, empty=not selected)
            if not self._log(job, "info", summary, "batch_finished"):
                failure = ProcessorSystemicError("required ingestion logging failed")
        if failure is None:
            completed = False
            try:
                completed = self.jobs.mark_completed(job.id)
            except Exception:
                failure = ProcessorSystemicError("job completion transition failed")
            if not completed and failure is None:
                failure = ProcessorSystemicError("job completion transition failed")
            # This post-terminal log is optional and must not reverse completion.
            if failure is None:
                self._log(job, "info", "Ingestion job completed", "job_complete")
        if failure is not None:
            self._terminalize_failure(job, logging_already_failed=failure.args[0] == "required ingestion logging failed")
            raise failure

    def _select(self, publications: Sequence[PublicationMetadata], job: IngestionJob) -> list[PublicationMetadata]:
        if job.scope_year_start > job.scope_year_end or job.max_documents < 0:
            raise ValueError("invalid scope")
        return [publication for publication in publications
                if job.scope_year_start <= publication.publication_year <= job.scope_year_end
                and publication.region.strip().casefold() == job.scope_region.strip().casefold()
                and publication.region_level.strip().casefold() == self.approved_region_level][:job.max_documents]

    def _process_document(self, job: IngestionJob, publication: PublicationMetadata) -> DocumentOutcome:
        if publication.pdf_url is None:
            return self._document_log_outcome(job, "Document skipped: missing PDF URL", "document_download", None, "failed")
        downloaded = None
        try:
            downloaded = self.downloader.download(publication)
        except Exception:
            pass
        if downloaded is None:
            return self._document_log_outcome(job, "Document download failed", "document_download", None, "failed")
        document = None
        persistence_failed = False
        try:
            document = self.documents.persist_download(publication, downloaded)
        except Exception:
            persistence_failed = True
        if persistence_failed or document is None:
            raise ProcessorSystemicError("document persistence failed")
        if document.status in {"indexed", "failed", "unsupported_or_extraction_failed"}:
            return self._document_log_outcome(job, f"Duplicate document skipped: status={document.status}",
                                              "duplicate_skip", document.document_id, "skipped")
        if not self._log(job, "info", "Document downloaded", "document_download", document.document_id):
            return self._failed_document(job, document.document_id, "required ingestion logging failed")
        parsed = None
        try:
            parsed = self.parser.parse(Path(document.local_pdf_path))
        except Exception:
            pass
        if parsed is None:
            return self._failed_document(job, document.document_id, "document_processing_failed")
        if parsed.status == "unsupported_or_extraction_failed":
            marked = False
            status_failed = False
            try:
                marked = self.documents.mark_unsupported(document.document_id, parsed.failure_code or "unsupported_pdf", len(parsed.pages))
            except Exception:
                status_failed = True
            if status_failed:
                raise ProcessorSystemicError("document status update failed")
            if not marked:
                raise ProcessorSystemicError("document unsupported transition failed")
            return self._document_log_outcome(job, "Document unsupported or extraction failed", "document_unsupported", document.document_id, "unsupported")
        marked_parsed = False
        status_failed = False
        try:
            marked_parsed = self.documents.mark_parsed(document.document_id, len(parsed.pages))
        except Exception:
            status_failed = True
        if status_failed:
            raise ProcessorSystemicError("document status update failed")
        if not marked_parsed:
            return self._failed_document(job, document.document_id, "document_status_update_failed")
        stage_failed = False
        try:
            cleaned = self.cleaner.clean(parsed)
            chunked = self.chunker.chunk(cleaned)
            if not chunked.chunks:
                stage_failed = True
            else:
                persisted = self.chunks.persist_for_document(document.document_id, chunked.chunks, str(publication.source_page_url))
                self.indexer.index(tuple(self._to_indexable(publication, document, chunk) for chunk in persisted))
        except Exception:
            stage_failed = True
        if stage_failed:
            return self._failed_document(job, document.document_id, "document_processing_failed")
        marked_indexed = False
        status_failed = False
        try:
            marked_indexed = self.documents.mark_indexed(document.document_id)
        except Exception:
            status_failed = True
        if status_failed:
            raise ProcessorSystemicError("document status update failed")
        if not marked_indexed:
            return self._failed_document(job, document.document_id, "document_status_update_failed")
        return self._document_log_outcome(job, "Document indexed", "document_index", document.document_id, "indexed")

    def _failed_document(self, job: IngestionJob, document_id: UUID, message: str) -> DocumentOutcome:
        marked = False
        status_failed = False
        try:
            marked = self.documents.mark_failed(document_id, message)
        except Exception:
            status_failed = True
        if status_failed:
            raise ProcessorSystemicError("document status update failed")
        if not marked:
            raise ProcessorSystemicError("document failure transition failed")
        return self._document_log_outcome(job, "Document processing failed", "document_failure", document_id, "failed")

    def _document_log_outcome(self, job: IngestionJob, message: str, step: str, document_id: UUID | None,
                              outcome: DocumentOutcome) -> DocumentOutcome:
        if not self._log(job, "warn" if outcome in {"failed", "unsupported"} else "info", message, step, document_id):
            raise ProcessorSystemicError("required ingestion logging failed")
        return outcome

    @staticmethod
    def _summary(counts: dict[str, int], *, empty: bool) -> str:
        if empty:
            return "No publications matched the ingestion scope"
        return ("Batch finished: indexed={indexed}; skipped={skipped}; unsupported={unsupported}; "
                "failed={failed}").format(**counts)

    @staticmethod
    def _to_indexable(publication: PublicationMetadata, document: PersistedDocument, chunk: PersistedChunk) -> IndexableChunk:
        return IndexableChunk(qdrant_point_id=chunk.qdrant_point_id, chunk_id=chunk.id, document_id=document.document_id,
                              text=chunk.text, title=publication.title, publication_year=publication.publication_year,
                              region=publication.region, region_level=publication.region_level, topic=publication.topic,
                              page_start=chunk.page_start, page_end=chunk.page_end, section_heading=chunk.section_heading,
                              chunk_index=chunk.chunk_index, extraction_method=chunk.extraction_method,
                              low_structure_confidence=False, source_url=chunk.source_url,
                              pdf_url=str(publication.pdf_url) if publication.pdf_url else None)

    def _log(self, job: IngestionJob, level: str, message: str, step: str, document_id: UUID | None = None) -> bool:
        try:
            self.logs.append(job.id, level, message, document_id=document_id, step_name=step)
        except Exception:
            return False
        return True

    def _terminalize_failure(self, job: IngestionJob, *, logging_already_failed: bool) -> None:
        if not logging_already_failed:
            self._log(job, "error", "Ingestion job failed", "job_failed")
        try:
            self.jobs.mark_failed(job.id, "systemic ingestion failure")
        except Exception:
            pass
