from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import fitz


ExtractionMethod = Literal["text_layer"]
PdfParseStatus = Literal["parsed", "unsupported_or_extraction_failed"]


class PdfParserError(Exception):
    """Base class for safe, typed PDF parser failures."""

    code = "pdf_parser_error"


class PdfMissingError(PdfParserError):
    code = "missing_pdf"

    def __init__(self) -> None:
        super().__init__("PDF file is missing")


class PdfUnreadableError(PdfParserError):
    code = "unreadable_pdf"

    def __init__(self) -> None:
        super().__init__("PDF file cannot be read")


class PdfCorruptError(PdfParserError):
    code = "corrupt_pdf"

    def __init__(self) -> None:
        super().__init__("PDF file is invalid or corrupt")


class PdfEncryptedError(PdfParserError):
    code = "encrypted_pdf"

    def __init__(self) -> None:
        super().__init__("Encrypted PDFs are not supported")


class PdfExtractionError(PdfParserError):
    code = "extraction_failed"

    def __init__(self) -> None:
        super().__init__("PDF text extraction failed")


@dataclass(frozen=True, slots=True)
class PdfPageMetadata:
    width: float
    height: float
    rotation: int


@dataclass(frozen=True, slots=True)
class PdfPage:
    page_number: int
    text: str
    metadata: PdfPageMetadata


@dataclass(frozen=True, slots=True)
class PdfParseResult:
    status: PdfParseStatus
    pages: tuple[PdfPage, ...]
    extraction_method: ExtractionMethod = "text_layer"
    failure_code: str | None = None


@runtime_checkable
class PdfParser(Protocol):
    def parse(self, pdf_path: Path | str) -> PdfParseResult:
        """Parse a local PDF without downloading or applying OCR."""


class PyMuPDFParser:
    """Extract page text from local, digital PDFs using PyMuPDF."""

    def parse(self, pdf_path: Path | str) -> PdfParseResult:
        path = _coerce_path(pdf_path)
        probe_error: PdfParserError | None = None
        exists = False
        is_file = False
        try:
            exists = path.exists()
            is_file = path.is_file() if exists else False
        except Exception:
            probe_error = PdfUnreadableError()
        if probe_error is not None:
            raise probe_error
        if not exists:
            raise PdfMissingError()
        if not is_file:
            raise PdfUnreadableError()

        document: fitz.Document | None = None
        parse_error: PdfParserError | None = None
        pages: tuple[PdfPage, ...] = ()
        try:
            document = fitz.open(filename=str(path))
            if document.needs_pass:
                raise PdfEncryptedError()
            pages = tuple(self._extract_page(document, page_index) for page_index in range(document.page_count))
        except PdfParserError as error:
            parse_error = error
        except fitz.FileDataError:
            parse_error = PdfCorruptError()
        except (OSError, ValueError):
            parse_error = PdfUnreadableError()
        except Exception:
            parse_error = PdfExtractionError()
        finally:
            if document is not None:
                try:
                    document.close()
                except Exception:
                    pass

        if parse_error is not None:
            raise parse_error

        if not any(page.text.strip() for page in pages):
            return PdfParseResult(
                status="unsupported_or_extraction_failed",
                pages=pages,
                failure_code="no_usable_text_layer",
            )
        return PdfParseResult(status="parsed", pages=pages)

    @staticmethod
    def _extract_page(document: fitz.Document, page_index: int) -> PdfPage:
        page_result: PdfPage | None = None
        try:
            page = document.load_page(page_index)
            rectangle = page.rect
            page_result = PdfPage(
                page_number=page_index + 1,
                text=page.get_text("text"),
                metadata=PdfPageMetadata(
                    width=float(rectangle.width),
                    height=float(rectangle.height),
                    rotation=page.rotation,
                ),
            )
        except Exception:
            pass
        if page_result is None:
            raise PdfExtractionError()
        return page_result


def _coerce_path(pdf_path: Path | str) -> Path:
    path: Path | None = None
    try:
        path = Path(pdf_path)
    except (TypeError, ValueError):
        pass
    if path is None:
        raise PdfUnreadableError()
    return path
