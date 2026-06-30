from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.chunking import TextChunk
from ringkas_worker.cleaning import CleanedDocument
from ringkas_worker.db.chunks import PersistedChunk
from ringkas_worker.db.documents import PersistedDocument
from ringkas_worker.db.jobs import IngestionJob
from ringkas_worker.parsers import PdfPage, PdfPageMetadata, PdfParseResult
from ringkas_worker.pdfs import DownloadedPdf
from ringkas_worker.processor import IngestionProcessor, ProcessorSystemicError
from ringkas_worker.worker import PollingWorker


def publication(region="DKI Jakarta", year=2025, pdf=True):
    return PublicationMetadata(
        title=f"Publication {year}", publication_year=year, region=region,
        region_level="province", source_page_url="https://bps.example/source",
        pdf_url="https://files.example/document.pdf" if pdf else None,
    )


def job(max_documents=10):
    now = datetime.now(timezone.utc)
    return IngestionJob(uuid4(), "user", "running", "DKI Jakarta", 2020, 2026,
                        max_documents, now, None, now, None)


class Logs:
    def __init__(self): self.entries = []
    def append(self, *args, **kwargs): self.entries.append((args, kwargs))


class Jobs:
    def __init__(self): self.completed = 0; self.failed = 0
    def mark_completed(self, _id): self.completed += 1; return True
    def mark_failed(self, _id, _message): self.failed += 1; return True


class Documents:
    def __init__(self, status="downloaded"):
        self.status = status; self.document_id = uuid4(); self.transitions = []
    def persist_download(self, _publication, _pdf):
        return PersistedDocument(self.document_id, "a" * 64, "/tmp/a.pdf", True, self.status)
    def mark_parsed(self, _id, _pages): self.transitions.append("parsed"); return True
    def mark_indexed(self, _id): self.transitions.append("indexed"); return True
    def mark_failed(self, _id, _message): self.transitions.append("failed"); return True
    def mark_unsupported(self, _id, _code, _pages=None): self.transitions.append("unsupported"); return True


class Chunks:
    def persist_for_document(self, document_id, chunks, source_url):
        return tuple(PersistedChunk(uuid4(), document_id, c.chunk_index, c.text, c.page_start, c.page_end,
                                    c.section_heading, c.extraction_method, False, source_url, str(uuid4()),
                                    datetime.now(timezone.utc)) for c in chunks)


class Downloader:
    def download(self, _publication): return DownloadedPdf("a" * 64, "/tmp/a.pdf", False)


class Parser:
    def parse(self, _path):
        page = PdfPage(1, "A sufficiently useful source text.", PdfPageMetadata(1, 1, 0))
        return PdfParseResult("parsed", (page,))


class Cleaner:
    def clean(self, parsed): return CleanedDocument(tuple(SimpleNamespace(page_number=p.page_number, text=p.text, metadata=p.metadata, section_heading=None) for p in parsed.pages))


class Chunker:
    def chunk(self, _cleaned): return SimpleNamespace(chunks=(TextChunk("source", 0, 1, 1),))


class Indexer:
    def __init__(self): self.calls = []
    def index(self, chunks): self.calls.append(chunks)


def processor(publications, documents=None, downloader=None, parser=None, cleaner=None, chunker=None, indexer=None, logs=None, jobs=None, chunks=None):
    return IngestionProcessor(
        publications=SimpleNamespace(fetch_publications=lambda: publications),
        downloader=downloader or Downloader(), parser=parser or Parser(), cleaner=cleaner or Cleaner(), chunker=chunker or Chunker(),
        indexer=indexer or Indexer(), jobs=jobs or Jobs(), documents=documents or Documents(), chunks=chunks or Chunks(),
        logs=logs or Logs(),
    )


def test_processor_runs_complete_injected_pipeline_and_filters_scope():
    logs, jobs, indexer = Logs(), Jobs(), Indexer()
    processor([publication(), publication(" Jawa Barat "), publication(year=2019)], logs=logs, jobs=jobs, indexer=indexer).process(job(1))
    assert jobs.completed == 1 and jobs.failed == 0
    assert len(indexer.calls) == 1
    assert any(entry[0][2] == "Document indexed" for entry in logs.entries)


def test_unsupported_document_continues_and_completes():
    class UnsupportedParser:
        def parse(self, _path): return PdfParseResult("unsupported_or_extraction_failed", (), failure_code="no_text")
    documents, jobs = Documents(), Jobs()
    processor([publication()], documents=documents, parser=UnsupportedParser(), jobs=jobs).process(job())
    assert documents.transitions == ["unsupported"]
    assert jobs.completed == 1


def test_missing_pdf_url_is_logged_without_document_id():
    logs, jobs = Logs(), Jobs()
    processor([publication(pdf=False)], logs=logs, jobs=jobs).process(job())
    assert jobs.completed == 1
    assert any(item[1].get("document_id") is None for item in logs.entries)


def test_terminal_duplicate_is_skipped():
    documents, indexer = Documents("indexed"), Indexer()
    processor([publication()], documents=documents, indexer=indexer).process(job())
    assert not documents.transitions and not indexer.calls


def test_processor_is_usable_as_polling_worker_handler():
    claimed = job()
    processor_instance = processor([], jobs=Jobs())
    repository = SimpleNamespace(claim_next_job=lambda: claimed)
    polling = PollingWorker(SimpleNamespace(ingestion_poll_interval_seconds=1), repository, processor_instance)
    assert polling.run_once() is True


def test_systemic_bps_failure_terminalizes_without_raw_exception_chain():
    jobs = Jobs()
    instance = processor([], jobs=jobs)
    def fail(): raise RuntimeError("Bearer provider-secret")
    instance.publications = SimpleNamespace(fetch_publications=fail)
    with pytest.raises(ProcessorSystemicError) as raised:
        instance.process(job())
    error = raised.value
    assert str(error) == "publication enumeration failed"
    assert error.__cause__ is None and error.__context__ is None
    assert jobs.failed == 1


def test_empty_corpus_completes_with_safe_summary_before_transition():
    logs, jobs = Logs(), Jobs()
    processor([], logs=logs, jobs=jobs).process(job())
    messages = [entry[0][2] for entry in logs.entries]
    assert "No publications matched the ingestion scope" in messages
    assert jobs.completed == 1


def test_download_failure_continues_and_is_counted_in_finished_summary():
    class FailingDownloader:
        def download(self, _publication): raise RuntimeError("api_key=secret")
    logs, jobs = Logs(), Jobs()
    processor([publication()], downloader=FailingDownloader(), logs=logs, jobs=jobs).process(job())
    assert jobs.completed == 1
    assert any("failed=1" in entry[0][2] for entry in logs.entries)
    assert all("secret" not in entry[0][2] for entry in logs.entries)


def test_required_logging_failure_is_systemic_and_does_not_chain_raw_exception():
    class FailingLogs:
        def append(self, *_args, **_kwargs): raise RuntimeError("postgresql://secret")
    jobs = Jobs()
    with pytest.raises(ProcessorSystemicError) as raised:
        processor([], logs=FailingLogs(), jobs=jobs).process(job())
    assert str(raised.value) == "required ingestion logging failed"
    assert raised.value.__cause__ is None and raised.value.__context__ is None
    assert jobs.failed == 1


def test_completion_transition_failure_terminalizes_safely():
    class FailingCompleteJobs(Jobs):
        def mark_completed(self, _id): self.completed += 1; return False
    jobs = FailingCompleteJobs()
    with pytest.raises(ProcessorSystemicError, match="job completion transition failed"):
        processor([], jobs=jobs).process(job())
    assert jobs.failed == 1


def test_failure_terminalization_preserves_safe_processor_error_when_transition_fails():
    class FailingJobs(Jobs):
        def mark_failed(self, _id, _message): raise RuntimeError("password=secret")
    instance = processor([], jobs=FailingJobs())
    def fail(): raise RuntimeError("provider secret")
    instance.publications = SimpleNamespace(fetch_publications=fail)
    with pytest.raises(ProcessorSystemicError) as raised:
        instance.process(job())
    assert str(raised.value) == "publication enumeration failed"
    assert raised.value.__cause__ is None and raised.value.__context__ is None


class FailingStage:
    def __init__(self, message): self.message = message; self.calls = 0
    def clean(self, _value): self.calls += 1; raise RuntimeError(self.message)
    def chunk(self, _value): self.calls += 1; raise RuntimeError(self.message)
    def index(self, _value): self.calls += 1; raise RuntimeError(self.message)
    def parse(self, _value): self.calls += 1; raise RuntimeError(self.message)


@pytest.mark.parametrize("stage", ["parser", "cleaner", "chunker", "indexer"])
def test_each_document_stage_failure_is_recoverable_and_not_retried(stage):
    failing = FailingStage("password=provider-secret")
    kwargs = {stage: failing}
    logs, jobs = Logs(), Jobs()
    processor([publication()], logs=logs, jobs=jobs, **kwargs).process(job())
    assert failing.calls == 1
    assert jobs.completed == 1
    assert any("failed=1" in entry[0][2] for entry in logs.entries)
    assert all("provider-secret" not in entry[0][2] for entry in logs.entries)


def test_empty_chunk_output_is_recoverable_document_failure():
    class EmptyChunker:
        calls = 0
        def chunk(self, _value): self.calls += 1; return SimpleNamespace(chunks=())
    chunker = EmptyChunker()
    documents, jobs = Documents(), Jobs()
    processor([publication()], documents=documents, jobs=jobs, chunker=chunker).process(job())
    assert chunker.calls == 1 and documents.transitions[-1] == "failed" and jobs.completed == 1


@pytest.mark.parametrize("status, method, message", [
    ("unsupported", "mark_unsupported", "document unsupported transition failed"),
    ("failed", "mark_failed", "document failure transition failed"),
])
def test_unsuccessful_required_document_transition_is_systemic(status, method, message):
    class FalseTransitionDocuments(Documents):
        def mark_unsupported(self, *_args): return False
        def mark_failed(self, *_args): return False
    documents = FalseTransitionDocuments()
    parser_value = SimpleNamespace(status="unsupported_or_extraction_failed", pages=(), failure_code="no_text")
    kwargs = {"documents": documents}
    if status == "unsupported":
        kwargs["parser"] = SimpleNamespace(parse=lambda _path: parser_value)
    else:
        kwargs["cleaner"] = SimpleNamespace(clean=lambda _parsed: (_ for _ in ()).throw(RuntimeError("cleaner failure")))
    with pytest.raises(ProcessorSystemicError, match=message):
        processor([publication()], **kwargs).process(job())


def test_downloaded_and_parsed_duplicates_continue_through_indexing():
    for duplicate_status in ("downloaded", "parsed"):
        documents, indexer, jobs = Documents(duplicate_status), Indexer(), Jobs()
        processor([publication()], documents=documents, indexer=indexer, jobs=jobs).process(job())
        assert jobs.completed == 1 and documents.transitions[-1] == "indexed" and indexer.calls


def test_failed_document_followed_by_indexed_document_has_truthful_counts():
    documents, logs, jobs = Documents(), Logs(), Jobs()
    publications = [publication(), publication(year=2024)]
    class FailingFirstParser(Parser):
        calls = 0
        def parse(self, path):
            self.calls += 1
            if self.calls == 1: raise RuntimeError("provider secret")
            return super().parse(path)
    processor(publications, documents=documents, logs=logs, jobs=jobs, parser=FailingFirstParser()).process(job())
    assert jobs.completed == 1
    assert any("indexed=1" in entry[0][2] and "failed=1" in entry[0][2] for entry in logs.entries)


def test_optional_post_completion_log_failure_does_not_fail_completed_job():
    class OptionalCompletionLogFailure(Logs):
        def append(self, *args, **kwargs):
            if kwargs.get("step_name") == "job_complete": raise RuntimeError("database secret")
            super().append(*args, **kwargs)
    jobs, logs = Jobs(), OptionalCompletionLogFailure()
    processor([], jobs=jobs, logs=logs).process(job())
    assert jobs.completed == 1 and jobs.failed == 0
