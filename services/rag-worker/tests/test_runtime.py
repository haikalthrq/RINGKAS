from contextlib import ExitStack
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

import ringkas_worker.__main__ as runtime
from ringkas_worker.chunking import RecursiveTextChunker
from ringkas_worker.cleaning import ConservativeTextCleaner
from ringkas_worker.parsers import PyMuPDFParser


def settings():
    return SimpleNamespace(
        database_url=SecretStr("postgresql://worker:secret@localhost/ringkas"),
        database_connect_timeout_seconds=10,
        database_statement_timeout_ms=30_000,
        bps_base_url="https://bps.example",
        bps_publications_path="publications",
        pdf_storage_path="/data/ringkas/pdfs",
        pdf_allowed_hosts="files.example",
        pdf_max_size_bytes=50 * 1024 * 1024,
        pdf_connect_timeout_seconds=10.0,
        pdf_read_timeout_seconds=60.0,
        pdf_total_timeout_seconds=300.0,
        pdf_max_redirects=5,
        chunk_size_max=800,
    )


class Resource:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def close(self):
        self.events.append(self.name)


def test_build_processor_wires_all_components_and_closes_owned_resources(monkeypatch):
    events = []
    bps = Resource("bps", events)
    downloader = Resource("pdf", events)
    indexer = Resource("qdrant-cloudflare", events)
    monkeypatch.setattr(runtime.BpsClient, "from_settings", lambda _settings: bps)
    monkeypatch.setattr(runtime.PdfDownloader, "from_settings", lambda _settings: downloader)
    monkeypatch.setattr(runtime.QdrantChunkIndexer, "from_environment", lambda: indexer)

    with ExitStack() as resources:
        processor = runtime.build_processor(settings(), resources)
        assert processor.publications is bps
        assert processor.downloader is downloader
        assert processor.indexer is indexer
        assert isinstance(processor.parser, PyMuPDFParser)
        assert isinstance(processor.cleaner, ConservativeTextCleaner)
        assert isinstance(processor.chunker, RecursiveTextChunker)
        assert processor.jobs is not None
        assert processor.documents is not None
        assert processor.chunks is not None
        assert processor.logs is not None
    assert events == ["qdrant-cloudflare", "pdf", "bps"]


def test_build_processor_failure_closes_resources_without_claiming(monkeypatch):
    events = []
    monkeypatch.setattr(runtime.BpsClient, "from_settings", lambda _settings: Resource("bps", events))
    monkeypatch.setattr(runtime.PdfDownloader, "from_settings", lambda _settings: Resource("pdf", events))

    def fail_indexer():
        raise ValueError("provider secret")

    monkeypatch.setattr(runtime.QdrantChunkIndexer, "from_environment", fail_indexer)
    resources = ExitStack()
    with pytest.raises(ValueError):
        runtime.build_processor(settings(), resources)
    resources.close()
    assert events == ["pdf", "bps"]
