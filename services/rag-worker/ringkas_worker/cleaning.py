from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ringkas_worker.parsers import PdfPage, PdfPageMetadata, PdfParseResult


# These are deliberately conservative implementation limits, not product claims.
_EDGE_LINE_LIMIT = 2
_MIN_REPEATED_PAGES = 2
_MAX_BOILERPLATE_DIGITS = 0
_HEADING_MAX_WORDS = 12
_HEADING_MAX_LENGTH = 100

_PAGE_NUMBER_RE = re.compile(
    r"^(?:(?:page|halaman)\s*)?[-\u2013\u2014]?\s*(\d+)\s*[-\u2013\u2014]?$",
    re.IGNORECASE,
)
_HORIZONTAL_SPACE_RE = re.compile(r"[ \t\f\v]+")
_MULTISPACE_RE = re.compile(r"\s+")
_REDUPLICATION_RE = re.compile(r"^([\w\u00c0-\u024f]+)-$", re.UNICODE)
_KNOWN_WRAPPED_REPETITIONS = frozenset({("sehari", "hari")})


@dataclass(frozen=True, slots=True)
class CleanedPage:
    """Cleaned text while retaining the parser's page identity and metadata."""

    page_number: int
    text: str
    metadata: PdfPageMetadata
    section_heading: str | None = None


@dataclass(frozen=True, slots=True)
class CleanedDocument:
    """Immutable page-preserving output for the future chunking stage."""

    pages: tuple[CleanedPage, ...]
    repeated_headers: tuple[str, ...] = ()
    repeated_footers: tuple[str, ...] = ()


@runtime_checkable
class TextCleaner(Protocol):
    def clean(self, parsed: PdfParseResult) -> CleanedDocument:
        """Clean parsed text without changing document semantics."""


class ConservativeTextCleaner:
    """Apply only deterministic, text-preserving cleanup to parsed PDF pages."""

    def clean(self, parsed: PdfParseResult) -> CleanedDocument:
        header_keys, footer_keys = _find_repeated_edge_lines(parsed.pages)
        cleaned_pages = tuple(
            self._clean_page(page, header_keys, footer_keys) for page in parsed.pages
        )
        return CleanedDocument(
            pages=cleaned_pages,
            repeated_headers=tuple(sorted(header_keys)),
            repeated_footers=tuple(sorted(footer_keys)),
        )

    @staticmethod
    def _clean_page(
        page: PdfPage,
        header_keys: frozenset[str],
        footer_keys: frozenset[str],
    ) -> CleanedPage:
        lines = _prepare_lines(page.text)
        kept: list[str] = []
        line_count = len(lines)
        for index, line in enumerate(lines):
            key = _line_key(line)
            header_position, footer_position = _edge_position(index, line_count)
            if key in header_keys and header_position:
                continue
            if key in footer_keys and footer_position:
                continue
            if _is_standalone_page_number(line, page.page_number):
                continue
            kept.append(line)

        heading = _detect_heading(kept)
        text = _join_lines(kept)
        return CleanedPage(page.page_number, text, page.metadata, heading)


def _prepare_lines(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    raw_lines = [_normalize_line(line) for line in normalized.split("\n")]
    lines: list[str] = []
    index = 0
    while index < len(raw_lines):
        line = raw_lines[index]
        if not line:
            index += 1
            continue
        if line.endswith("-") and index + 1 < len(raw_lines):
            next_line = raw_lines[index + 1]
            joined = _join_hyphenated_lines(line, next_line)
            if joined is not None:
                lines.append(joined)
                index += 2
                continue
        lines.append(line)
        index += 1
    return lines


def _normalize_line(line: str) -> str:
    return _HORIZONTAL_SPACE_RE.sub(" ", line).strip()


def _join_lines(lines: list[str]) -> str:
    # Page boundaries remain explicit in CleanedDocument.pages; text line wraps do not.
    return _MULTISPACE_RE.sub(" ", " ".join(lines)).strip()


def _join_hyphenated_lines(line: str, next_line: str) -> str | None:
    if not next_line or not line or line[-1] != "-":
        return None
    prefix = line[:-1].rstrip()
    if not prefix or not prefix[-1].isalpha() or not next_line[0].islower():
        return None
    reduplication = _REDUPLICATION_RE.fullmatch(line)
    if reduplication is None:
        return prefix + next_line
    pair = (reduplication.group(1).casefold(), next_line.casefold())
    if pair in _KNOWN_WRAPPED_REPETITIONS or pair[0] == pair[1]:
        return line + next_line
    return prefix + next_line


def _find_repeated_edge_lines(pages: tuple[PdfPage, ...]) -> tuple[frozenset[str], frozenset[str]]:
    if len(pages) < _MIN_REPEATED_PAGES:
        return frozenset(), frozenset()
    header_pages: defaultdict[str, set[int]] = defaultdict(set)
    footer_pages: defaultdict[str, set[int]] = defaultdict(set)
    for page in pages:
        lines = _prepare_lines(page.text)
        if not lines:
            continue
        for index, line in enumerate(lines):
            header_position, footer_position = _edge_position(index, len(lines))
            if _is_boilerplate_candidate(line):
                key = _line_key(line)
                if header_position:
                    header_pages[key].add(page.page_number)
                if footer_position:
                    footer_pages[key].add(page.page_number)

    page_count = len(pages)
    minimum_count = max(_MIN_REPEATED_PAGES, (page_count + 1) // 2)
    headers = {key for key, page_numbers in header_pages.items() if len(page_numbers) >= minimum_count}
    footers = {key for key, page_numbers in footer_pages.items() if len(page_numbers) >= minimum_count}
    ambiguous = headers & footers
    headers.difference_update(ambiguous)
    footers.difference_update(ambiguous)
    return frozenset(headers), frozenset(footers)


def _edge_position(index: int, line_count: int) -> tuple[bool, bool]:
    header_position = index < _EDGE_LINE_LIMIT
    footer_position = index >= max(0, line_count - _EDGE_LINE_LIMIT)
    if header_position and footer_position:
        return False, False
    return header_position, footer_position


def _is_boilerplate_candidate(line: str) -> bool:
    # Numeric-bearing edge lines are retained because they may be statistical content.
    return bool(line) and sum(character.isdigit() for character in line) <= _MAX_BOILERPLATE_DIGITS


def _line_key(line: str) -> str:
    return " ".join(line.casefold().split())


def _is_standalone_page_number(line: str, page_number: int) -> bool:
    match = _PAGE_NUMBER_RE.fullmatch(line)
    return match is not None and int(match.group(1)) == page_number


def _detect_heading(lines: list[str]) -> str | None:
    for line in lines:
        if _looks_like_heading(line):
            return line
    return None


def _looks_like_heading(line: str) -> bool:
    if not line or len(line) > _HEADING_MAX_LENGTH or line[-1] in ".,;:!?%":
        return False
    words = line.split()
    if not 1 <= len(words) <= _HEADING_MAX_WORDS or any(character.isdigit() for character in line):
        return False
    alphabetic = [character for character in line if character.isalpha()]
    if not alphabetic or not any(character.isupper() for character in alphabetic):
        return False
    return line.isupper() or sum(word[:1].isupper() for word in words) >= max(1, len(words) - 1)
