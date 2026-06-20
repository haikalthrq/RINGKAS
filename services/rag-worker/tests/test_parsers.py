from __future__ import annotations

import traceback
from pathlib import Path

import fitz
import pytest

from ringkas_worker.parsers import (
    PdfCorruptError,
    PdfEncryptedError,
    PdfMissingError,
    PdfPage,
    PdfPageMetadata,
    PdfParser,
    PdfParserError,
    PdfUnreadableError,
    PdfExtractionError,
    PyMuPDFParser,
)


def create_pdf(path: Path, pages: list[str]) -> None:
    document = fitz.open()
    try:
        for text in pages:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        document.save(path)
    finally:
        document.close()


def assert_sanitized(error: BaseException, secret: str) -> None:
    rendered = "\n".join(
        (
            str(error),
            repr(error),
            "".join(traceback.format_exception(error)),
            repr(error.__cause__),
            repr(error.__context__),
        )
    )
    assert secret not in rendered
    assert error.__cause__ is None
    assert error.__context__ is None


def test_parser_protocol_is_implemented_by_pymupdf_parser() -> None:
    assert isinstance(PyMuPDFParser(), PdfParser)


def test_extracts_multiple_pages_with_boundaries_and_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "digital.pdf"
    create_pdf(pdf_path, ["first page", "second page"])

    result = PyMuPDFParser().parse(pdf_path)

    assert result.status == "parsed"
    assert result.extraction_method == "text_layer"
    assert [page.page_number for page in result.pages] == [1, 2]
    assert [page.text.strip() for page in result.pages] == ["first page", "second page"]
    assert result.pages[0].metadata.width > 0
    assert result.pages[0].metadata.height > 0
    assert result.pages[0].metadata.rotation == 0


def test_empty_page_does_not_make_document_unsupported(tmp_path: Path) -> None:
    pdf_path = tmp_path / "with-empty-page.pdf"
    create_pdf(pdf_path, ["text page", "", "another text page"])

    result = PyMuPDFParser().parse(pdf_path)

    assert result.status == "parsed"
    assert len(result.pages) == 3
    assert result.pages[1].text == ""


def test_document_without_usable_text_is_explicitly_unsupported(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    create_pdf(pdf_path, ["", "   "])

    result = PyMuPDFParser().parse(pdf_path)

    assert result.status == "unsupported_or_extraction_failed"
    assert result.failure_code == "no_usable_text_layer"
    assert result.extraction_method == "text_layer"
    assert len(result.pages) == 2


def test_malformed_pdf_raises_sanitized_typed_error(tmp_path: Path) -> None:
    secret_path = tmp_path / "private-malformed-document.pdf"
    secret_path.write_bytes(b"not a PDF")

    with pytest.raises(PdfCorruptError) as error:
        PyMuPDFParser().parse(secret_path)

    assert_sanitized(error.value, str(secret_path))
    assert isinstance(error.value, PdfParserError)


def test_missing_pdf_raises_sanitized_typed_error(tmp_path: Path) -> None:
    secret_path = tmp_path / "private-missing-document.pdf"

    with pytest.raises(PdfMissingError) as error:
        PyMuPDFParser().parse(secret_path)

    assert_sanitized(error.value, str(secret_path))


def test_unreadable_path_raises_sanitized_typed_error(tmp_path: Path) -> None:
    secret_path = tmp_path / "private-directory"
    secret_path.mkdir()

    with pytest.raises(PdfUnreadableError) as error:
        PyMuPDFParser().parse(secret_path)

    assert_sanitized(error.value, str(secret_path))


def test_encrypted_pdf_raises_sanitized_typed_error(tmp_path: Path) -> None:
    pdf_path = tmp_path / "encrypted.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "secret")
    document.save(pdf_path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    document.close()

    with pytest.raises(PdfEncryptedError) as error:
        PyMuPDFParser().parse(pdf_path)

    assert_sanitized(error.value, str(pdf_path))


def test_raw_extraction_failure_is_converted_without_exception_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "raw-extraction-failure.pdf"
    create_pdf(pdf_path, ["text"])
    secret = "raw pymupdf extraction detail"

    def fail_extraction(document: fitz.Document, page_index: int) -> PdfPage:
        raise RuntimeError(secret)

    monkeypatch.setattr(PyMuPDFParser, "_extract_page", staticmethod(fail_extraction))
    with pytest.raises(PdfExtractionError) as error:
        PyMuPDFParser().parse(pdf_path)

    assert_sanitized(error.value, secret)


def test_filesystem_probe_failure_is_mapped_to_unreadable_without_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "probe-failure.pdf"

    def fail_exists(self: Path) -> bool:
        raise OSError("filesystem probe secret")

    monkeypatch.setattr(Path, "exists", fail_exists)
    with pytest.raises(PdfUnreadableError) as error:
        PyMuPDFParser().parse(pdf_path)

    assert_sanitized(error.value, "filesystem probe secret")


class FailingCloseDocument:
    needs_pass = False
    page_count = 1

    def close(self) -> None:
        raise RuntimeError("close secret")


def test_document_close_failure_does_not_mask_primary_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "close-failure.pdf"
    pdf_path.write_bytes(b"placeholder")
    document = FailingCloseDocument()
    page = PdfPage(1, "usable text", PdfPageMetadata(100.0, 100.0, 0))
    monkeypatch.setattr("ringkas_worker.parsers.fitz.open", lambda **kwargs: document)
    monkeypatch.setattr(PyMuPDFParser, "_extract_page", staticmethod(lambda document, page_index: page))

    result = PyMuPDFParser().parse(pdf_path)

    assert result.status == "parsed"
    assert result.pages == (page,)


def test_cleanup_failure_does_not_mask_primary_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "cleanup-primary-error.pdf"
    pdf_path.write_bytes(b"placeholder")
    document = FailingCloseDocument()
    monkeypatch.setattr("ringkas_worker.parsers.fitz.open", lambda **kwargs: document)

    def fail_extraction(document: fitz.Document, page_index: int) -> PdfPage:
        raise PdfCorruptError()

    monkeypatch.setattr(PyMuPDFParser, "_extract_page", staticmethod(fail_extraction))
    with pytest.raises(PdfCorruptError) as error:
        PyMuPDFParser().parse(pdf_path)

    assert_sanitized(error.value, "cleanup-primary-error")
