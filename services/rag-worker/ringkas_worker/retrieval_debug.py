from __future__ import annotations

import json
import logging
import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from ringkas_worker.fusion import FusedRetrievalCandidate, FusedRetrievalResult
from ringkas_worker.retrieval import DenseRetrievalCandidate, DenseRetrievalResult
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult
from ringkas_worker.sparse_retrieval import (
    SparseRetrievalCandidate,
    SparseRetrievalResult,
)


class RetrievalDebugConfigurationError(ValueError):
    """Safe configuration error for developer-only retrieval diagnostics."""


def _configuration_error(message: str) -> None:
    error = RetrievalDebugConfigurationError(message)
    error.__cause__ = None
    error.__context__ = None
    raise error


def _environment_boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    _configuration_error(f"{name} must be an explicit boolean")


def _environment_integer(name: str, default: int, maximum: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    parsed: int | None = None
    conversion_failed = False
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError, OverflowError):
        conversion_failed = True
    if conversion_failed or parsed is None or parsed <= 0 or parsed > maximum:
        _configuration_error(f"{name} must be a positive bounded integer")
    return parsed


@dataclass(frozen=True, slots=True)
class RetrievalDebugSettings:
    enabled: bool = False
    include_sensitive_text: bool = False
    include_scores: bool = False
    query_preview_max_chars: int = 128
    max_candidates_per_stage: int = 20

    def __post_init__(self) -> None:
        if (
            not isinstance(self.enabled, bool)
            or not isinstance(self.include_sensitive_text, bool)
            or not isinstance(self.include_scores, bool)
        ):
            _configuration_error("retrieval debug boolean settings are invalid")
        for value, name, maximum in (
            (self.query_preview_max_chars, "query preview maximum", 500),
            (self.max_candidates_per_stage, "candidate maximum", 100),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                or value > maximum
            ):
                _configuration_error(
                    f"retrieval debug {name} must be a positive bounded integer"
                )

    @classmethod
    def from_environment(cls) -> RetrievalDebugSettings:
        return cls(
            enabled=_environment_boolean("RETRIEVAL_DEBUG_LOG_ENABLED", False),
            include_sensitive_text=_environment_boolean(
                "RETRIEVAL_DEBUG_INCLUDE_SENSITIVE_TEXT", False
            ),
            include_scores=_environment_boolean(
                "RETRIEVAL_DEBUG_INCLUDE_SCORES", False
            ),
            query_preview_max_chars=_environment_integer(
                "RETRIEVAL_DEBUG_QUERY_MAX_CHARS", 128, 500
            ),
            max_candidates_per_stage=_environment_integer(
                "RETRIEVAL_DEBUG_MAX_CANDIDATES", 20, 100
            ),
        )


@dataclass(frozen=True, slots=True)
class ResolvedRetrievalFilters:
    publication_year: int | None = None
    topic: str | None = None
    document_title: str | None = None
    document_id: str | None = None


@runtime_checkable
class RetrievalDebugSink(Protocol):
    def info(self, message: str) -> None: ...


_LOGGER_NAME = "ringkas_worker.retrieval_debug"
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_FILTER_KEYS = ("publication_year", "topic", "document_title", "document_id")
_SOURCE_TEXT_HARD_MAX = 4096
_REDACTION_MARKER = "[REDACTED]"
_URL_CREDENTIALS = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^\s/@:]+(?::[^\s/@]*)?@")
_AUTH_CREDENTIALS = re.compile(
    r"(?i)(\bauthorization\s*:\s*|\b)(?:bearer|basic)\s+[^\s,;]+"
)
_NAMED_SECRETS = re.compile(
    r"(?i)(\b(?:api[_-]?key|token|access[_-]?token|refresh[_-]?token|password|passwd|secret|authorization|cookie|user[_-]?id|userid|session[_-]?id|sessionid)\b\s*[:=]\s*)(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;]+)"
)
_JWT_LIKE = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_SECRET_PREFIXED = re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{8,}\b")
_EMAIL_ADDRESS = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b"
)


def _clean_text(value: str, limit: int) -> tuple[str, bool]:
    source_limit = min(_SOURCE_TEXT_HARD_MAX, max(limit * 8, limit + 128))
    source = value[:source_limit]
    input_truncated = len(value) > source_limit
    normalized = _CONTROL_CHARACTERS.sub(" ", source)
    normalized = " ".join(normalized.split())
    normalized = _URL_CREDENTIALS.sub(rf"\1{_REDACTION_MARKER}@", normalized)
    normalized = _AUTH_CREDENTIALS.sub(_REDACTION_MARKER, normalized)
    normalized = _NAMED_SECRETS.sub(rf"\1{_REDACTION_MARKER}", normalized)
    normalized = _JWT_LIKE.sub(_REDACTION_MARKER, normalized)
    normalized = _SECRET_PREFIXED.sub(_REDACTION_MARKER, normalized)
    normalized = _EMAIL_ADDRESS.sub(_REDACTION_MARKER, normalized)
    return normalized[:limit], input_truncated or len(normalized) > limit


class _MalformedDebugInput(ValueError):
    pass


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise _MalformedDebugInput
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise _MalformedDebugInput from None
    if str(parsed) != value:
        raise _MalformedDebugInput
    return value


def _positive_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _MalformedDebugInput
    return value


def _finite_score(value: object, *, nullable: bool = False) -> float | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _MalformedDebugInput
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        raise _MalformedDebugInput from None
    if not math.isfinite(converted):
        raise _MalformedDebugInput
    return converted


class RetrievalDebugLogger:
    """Injectable, bounded retrieval diagnostics using one standard log event."""

    def __init__(
        self,
        settings: RetrievalDebugSettings | None = None,
        logger: RetrievalDebugSink | None = None,
    ) -> None:
        if settings is not None and not isinstance(settings, RetrievalDebugSettings):
            _configuration_error("retrieval debug settings have invalid type")
        self._settings = settings or RetrievalDebugSettings()
        self._logger = logger if logger is not None else logging.getLogger(_LOGGER_NAME)

    def snapshot(
        self,
        query: object,
        resolved_filters: object = None,
        *,
        dense: DenseRetrievalResult | None = None,
        sparse: SparseRetrievalResult | None = None,
        fused: FusedRetrievalResult | None = None,
        final: FinalRetrievalResult | None = None,
    ) -> bool:
        if not self._settings.enabled:
            return False
        try:
            event = {
                "event": "retrieval_debug_snapshot",
                "query": self._query_summary(query),
                "filters": self._filter_summary(resolved_filters),
                "stages": [
                    stage
                    for stage in (
                        self._stage_summary("dense", dense),
                        self._stage_summary("sparse", sparse),
                        self._stage_summary("fused", fused),
                        self._stage_summary("final", final),
                    )
                    if stage is not None
                ],
            }
            message = json.dumps(
                event,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            self._logger.info(message)
            return True
        except Exception:
            return False

    def _query_summary(self, query: object) -> dict[str, object]:
        if not isinstance(query, str):
            return {"textIncluded": False, "queryLength": None}
        summary: dict[str, object] = {
            "textIncluded": self._settings.include_sensitive_text,
            "queryLength": len(query),
        }
        if self._settings.include_sensitive_text:
            preview, truncated = _clean_text(
                query, self._settings.query_preview_max_chars
            )
            summary.update({"preview": preview, "truncated": truncated})
        return summary

    def _filter_summary(self, filters: object) -> dict[str, object]:
        if isinstance(filters, ResolvedRetrievalFilters):
            values: Mapping[str, object] = {
                key: getattr(filters, key)
                for key in (
                    "publication_year",
                    "topic",
                    "document_title",
                    "document_id",
                )
            }
        elif isinstance(filters, Mapping):
            values = filters
        else:
            values = {}
        result: dict[str, object] = {
            "textIncluded": self._settings.include_sensitive_text
        }
        for key in _FILTER_KEYS:
            value = values.get(key)
            if key == "document_title" and value is None:
                value = values.get("title")
            if key == "publication_year":
                if isinstance(value, int) and not isinstance(value, bool):
                    result[key] = value
                continue
            if value is None:
                continue
            if not isinstance(value, str):
                continue
            if self._settings.include_sensitive_text and isinstance(value, str):
                preview, truncated = _clean_text(
                    value, self._settings.query_preview_max_chars
                )
                result[key] = {
                    "present": True,
                    "preview": preview,
                    "truncated": truncated,
                }
            else:
                result[key] = {"present": True}
        return result

    def _stage_summary(self, name: str, result: object) -> dict[str, object] | None:
        if result is None:
            return None
        result_types = {
            "dense": (DenseRetrievalResult, DenseRetrievalCandidate),
            "sparse": (SparseRetrievalResult, SparseRetrievalCandidate),
            "fused": (FusedRetrievalResult, FusedRetrievalCandidate),
            "final": (FinalRetrievalResult, FinalRetrievalCandidate),
        }
        result_type, candidate_type = result_types[name]
        if not isinstance(result, result_type) or not isinstance(
            result.candidates, tuple
        ):
            raise _MalformedDebugInput
        returned_count = len(result.candidates)
        requested_limit = getattr(result, "requested_limit", None)
        if requested_limit is not None:
            requested_limit = _positive_integer(requested_limit)
            if returned_count > requested_limit:
                raise _MalformedDebugInput
        logged = result.candidates[: self._settings.max_candidates_per_stage]
        for candidate in logged:
            if not isinstance(candidate, candidate_type):
                raise _MalformedDebugInput
            self._validate_candidate(name, candidate)
        summary: dict[str, object] = {
            "stage": name,
            "requestedLimit": requested_limit,
            "returnedCandidateCount": returned_count,
            "loggedCandidateCount": len(logged),
            "capped": returned_count > len(logged),
            "candidates": [
                self._candidate_summary(name, candidate) for candidate in logged
            ],
        }
        return summary

    def _validate_candidate(self, stage: str, candidate: object) -> None:
        _positive_integer(candidate.rank)
        _canonical_uuid(candidate.chunk_id)
        _canonical_uuid(candidate.document_id)
        if stage in {"fused", "final"}:
            for rank in (candidate.dense_rank, candidate.sparse_rank):
                if rank is not None:
                    _positive_integer(rank)
        if not self._settings.include_scores:
            return
        if stage in {"dense", "sparse"}:
            _finite_score(candidate.score)
        else:
            _finite_score(candidate.rrf_score)
            _finite_score(candidate.dense_score, nullable=True)
            _finite_score(candidate.sparse_score, nullable=True)

    def _candidate_summary(self, stage: str, candidate: object) -> dict[str, object]:
        summary: dict[str, object] = {
            "rank": candidate.rank,
            "chunkId": candidate.chunk_id,
            "documentId": candidate.document_id,
        }
        if stage in {"fused", "final"}:
            summary.update(
                {"denseRank": candidate.dense_rank, "sparseRank": candidate.sparse_rank}
            )
        if self._settings.include_scores:
            if stage in {"dense", "sparse"}:
                summary["score"] = candidate.score
            else:
                summary.update(
                    {
                        "rrfScore": candidate.rrf_score,
                        "denseScore": candidate.dense_score,
                        "sparseScore": candidate.sparse_score,
                    }
                )
        return summary
