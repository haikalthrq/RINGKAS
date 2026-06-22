from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol, runtime_checkable

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ringkas_worker.cleaning import CleanedDocument


ExtractionMethod = Literal["text_layer"]
_MIN_CHUNK_SIZE = 500
_MAX_CHUNK_SIZE = 800
_OVERLAP_PERCENT = 20


class ChunkingError(Exception):
    """Base class for safe, typed chunking failures."""

    code = "chunking_error"


class ChunkConfigurationError(ChunkingError):
    """Raised when chunking parameters are outside the supported range."""

    code = "invalid_chunk_configuration"


class ChunkLengthError(ChunkingError):
    """Raised when the injected length function cannot measure text safely."""

    code = "invalid_chunk_length"


class ChunkOutputError(ChunkingError):
    """Raised when a splitter result violates the configured size limit."""

    code = "invalid_chunk_output"


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A source-preserving chunk with page-local citation metadata."""

    text: str
    chunk_index: int
    page_start: int
    page_end: int
    section_heading: str | None = None
    extraction_method: ExtractionMethod = "text_layer"


@dataclass(frozen=True, slots=True)
class ChunkedDocument:
    """Immutable ordered chunks produced from a cleaned document."""

    chunks: tuple[TextChunk, ...]


@runtime_checkable
class TextChunker(Protocol):
    def chunk(self, document: CleanedDocument) -> ChunkedDocument:
        """Split a cleaned document without changing its source text."""


class RecursiveTextChunker:
    """Split each page independently using LangChain's recursive splitter.

    Chunk indexes are document-global, zero-based, and contiguous. Splitting
    per page makes page_start/page_end exact; overlap therefore never crosses a
    page boundary. The 20% overlap uses floor rounding.
    """

    def __init__(self, *, chunk_size: int, length_function: Callable[[str], int]) -> None:
        if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
            raise ChunkConfigurationError("chunk_size must be an integer")
        if not _MIN_CHUNK_SIZE <= chunk_size <= _MAX_CHUNK_SIZE:
            raise ChunkConfigurationError("chunk_size must be between 500 and 800")
        if not callable(length_function):
            raise ChunkConfigurationError("length_function must be callable")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_size * _OVERLAP_PERCENT // 100
        self.length_function = length_function

    def chunk(self, document: CleanedDocument) -> ChunkedDocument:
        chunks: list[TextChunk] = []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=self._measure,
            separators=("\n\n", "\n", " ", ""),
            strip_whitespace=False,
        )
        for page in document.pages:
            if not page.text.strip():
                continue
            split_failed = False
            try:
                page_chunks = splitter.split_text(page.text)
            except ChunkLengthError:
                raise
            except Exception:
                split_failed = True
            if split_failed:
                raise ChunkLengthError("length_function failed while splitting text")
            for text in page_chunks:
                if not text:
                    continue
                measured = self._measure(text)
                if measured > self.chunk_size:
                    raise ChunkOutputError("splitter produced an oversized chunk")
                chunks.append(
                    TextChunk(
                        text=text,
                        chunk_index=len(chunks),
                        page_start=page.page_number,
                        page_end=page.page_number,
                        section_heading=page.section_heading,
                    )
                )
        return ChunkedDocument(chunks=tuple(chunks))

    def _measure(self, text: str) -> int:
        measure_failed = False
        try:
            measured = self.length_function(text)
        except Exception:
            measure_failed = True
            measured = -1
        if measure_failed:
            raise ChunkLengthError("length_function failed to measure text")
        if isinstance(measured, bool) or not isinstance(measured, int) or measured < 0:
            raise ChunkLengthError("length_function must return a non-negative integer")
        return measured
