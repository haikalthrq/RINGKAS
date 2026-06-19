from datetime import date
from uuid import UUID

from ringkas_worker.bps.models import PublicationMetadata
from ringkas_worker.db.documents import DocumentRepository
from ringkas_worker.pdfs import DownloadedPdf


class Cursor:
    def __init__(self, existing=None):
        self.existing = existing
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        self.statements.append((sql, params))

    def fetchone(self):
        return self.existing


class Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_value


def metadata() -> PublicationMetadata:
    return PublicationMetadata(
        title="Title", publication_year=2025, release_date=date(2025, 1, 1),
        region="DKI Jakarta", region_level="province",
        source_page_url="https://bps.example.test/source", pdf_url="https://files.example.test/a.pdf",
    )


def test_persistence_inserts_downloaded_document_with_checksum_and_path() -> None:
    cursor = Cursor()
    result = DocumentRepository("unused", connection_factory=lambda: Connection(cursor)).persist_download(
        metadata(), DownloadedPdf("a" * 64, "/data/ringkas/pdfs/" + "a" * 64 + ".pdf", False)
    )
    assert isinstance(result.document_id, UUID)
    insert = cursor.statements[1]
    assert "downloaded" in insert[1]
    assert "a" * 64 in insert[1]
    assert any(isinstance(value, str) and "/data/ringkas/pdfs/" in value for value in insert[1])


def test_existing_checksum_is_returned_without_insert() -> None:
    existing_id = UUID("00000000-0000-0000-0000-000000000001")
    cursor = Cursor((existing_id, "/data/ringkas/pdfs/existing.pdf"))
    result = DocumentRepository("unused", connection_factory=lambda: Connection(cursor)).persist_download(
        metadata(), DownloadedPdf("b" * 64, "/data/ringkas/pdfs/b.pdf", False)
    )
    assert result.document_id == existing_id
    assert result.is_duplicate is True
    assert len(cursor.statements) == 1
