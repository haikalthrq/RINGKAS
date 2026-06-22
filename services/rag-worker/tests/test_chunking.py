from __future__ import annotations

import traceback

import pytest

from ringkas_worker.chunking import (
    ChunkConfigurationError,
    ChunkLengthError,
    RecursiveTextChunker,
    TextChunker,
)
from ringkas_worker.cleaning import CleanedDocument, CleanedPage
from ringkas_worker.parsers import PdfPageMetadata


METADATA = PdfPageMetadata(612.0, 792.0, 0)


def cleaned_page(number: int, text: str, heading: str | None = None) -> CleanedPage:
    return CleanedPage(number, text, METADATA, heading)


def cleaned_document(*pages: CleanedPage) -> CleanedDocument:
    return CleanedDocument(tuple(pages))


def characters(text: str) -> int:
    return len(text)


def words(text: str) -> int:
    return len(text.split())


def test_recursive_chunker_protocol_is_implemented() -> None:
    assert isinstance(RecursiveTextChunker(chunk_size=500, length_function=words), TextChunker)


@pytest.mark.parametrize("size", [500, 800])
def test_chunk_size_boundaries_are_accepted(size: int) -> None:
    chunker = RecursiveTextChunker(chunk_size=size, length_function=words)
    assert chunker.chunk_overlap == size * 20 // 100


@pytest.mark.parametrize("size", [499, 801])
def test_chunk_size_outside_supported_range_is_rejected(size: int) -> None:
    with pytest.raises(ChunkConfigurationError):
        RecursiveTextChunker(chunk_size=size, length_function=words)


def test_overlap_is_twenty_percent_with_floor_rounding() -> None:
    assert RecursiveTextChunker(chunk_size=501, length_function=words).chunk_overlap == 100
    assert RecursiveTextChunker(chunk_size=799, length_function=words).chunk_overlap == 159


def test_short_text_remains_one_source_preserving_chunk() -> None:
    source = "Indeks harga 2024 sebesar 3,50% di DKI Jakarta."
    result = RecursiveTextChunker(chunk_size=500, length_function=characters).chunk(
        cleaned_document(cleaned_page(3, source, "INDEKS HARGA"))
    )
    assert result.chunks[0].text == source
    assert result.chunks[0].chunk_index == 0
    assert result.chunks[0].page_start == result.chunks[0].page_end == 3
    assert result.chunks[0].section_heading == "INDEKS HARGA"
    assert result.chunks[0].extraction_method == "text_layer"


def test_long_text_is_ordered_contiguous_and_overlapped() -> None:
    source = "0123456789" * 130
    result = RecursiveTextChunker(chunk_size=500, length_function=characters).chunk(
        cleaned_document(cleaned_page(1, source))
    )
    assert len(result.chunks) == 3
    assert [chunk.chunk_index for chunk in result.chunks] == [0, 1, 2]
    assert all(len(chunk.text) <= 500 for chunk in result.chunks)
    assert result.chunks[0].text[-100:] == result.chunks[1].text[:100]
    assert result.chunks[1].text[-100:] == result.chunks[2].text[:100]
    assert "".join(
        chunk.text if index == 0 else chunk.text[100:]
        for index, chunk in enumerate(result.chunks)
    ) == source


def test_empty_document_and_pages_produce_no_chunks() -> None:
    result = RecursiveTextChunker(chunk_size=500, length_function=characters).chunk(
        cleaned_document(cleaned_page(1, ""), cleaned_page(2, " \n\t"))
    )
    assert result.chunks == ()


def test_multiple_pages_preserve_exact_page_ranges_and_heading() -> None:
    result = RecursiveTextChunker(chunk_size=500, length_function=characters).chunk(
        cleaned_document(
            cleaned_page(2, "a" * 600, "BAB SATU"),
            cleaned_page(3, "b" * 20, "BAB DUA"),
        )
    )
    assert [chunk.chunk_index for chunk in result.chunks] == [0, 1, 2]
    assert [(chunk.page_start, chunk.page_end) for chunk in result.chunks] == [
        (2, 2),
        (2, 2),
        (3, 3),
    ]
    assert [chunk.section_heading for chunk in result.chunks] == ["BAB SATU", "BAB SATU", "BAB DUA"]


def test_injected_length_function_is_used_consistently() -> None:
    calls: list[str] = []

    def counting_length(text: str) -> int:
        calls.append(text)
        return len(text)

    result = RecursiveTextChunker(chunk_size=500, length_function=counting_length).chunk(
        cleaned_document(cleaned_page(1, "x" * 600))
    )
    assert calls
    assert all(len(chunk.text) <= 500 for chunk in result.chunks)


def test_long_text_does_not_exceed_injected_token_measure() -> None:
    source = " ".join(f"kata{index}" for index in range(1200))
    result = RecursiveTextChunker(chunk_size=500, length_function=words).chunk(
        cleaned_document(cleaned_page(1, source))
    )
    assert len(result.chunks) > 1
    assert all(words(chunk.text) <= 500 for chunk in result.chunks)


@pytest.mark.parametrize("invalid", [-1, 1.5, True])
def test_invalid_length_result_is_a_typed_sanitized_error(invalid: object) -> None:
    with pytest.raises(ChunkLengthError) as error:
        RecursiveTextChunker(chunk_size=500, length_function=lambda text: invalid).chunk(
            cleaned_document(cleaned_page(1, "text"))
        )
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_length_function_failure_is_sanitized_without_exception_chain() -> None:
    secret = "private tokenizer failure"

    def failing_length(text: str) -> int:
        raise RuntimeError(secret)

    with pytest.raises(ChunkLengthError) as error:
        RecursiveTextChunker(chunk_size=500, length_function=failing_length).chunk(
            cleaned_document(cleaned_page(1, "text"))
        )
    rendered = "\n".join((str(error.value), repr(error.value), "".join(traceback.format_exception(error.value))))
    assert secret not in rendered
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_statistical_text_is_not_rewritten() -> None:
    source = "Tahun 2024: 3,50 persen; 10.000 jiwa di DKI Jakarta. Definisi: penduduk tetap."
    result = RecursiveTextChunker(chunk_size=500, length_function=characters).chunk(
        cleaned_document(cleaned_page(1, source))
    )
    assert result.chunks[0].text == source
