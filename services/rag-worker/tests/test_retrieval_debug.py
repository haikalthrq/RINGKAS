import json
import math
import traceback
from dataclasses import replace

import pytest

from ringkas_worker.fusion import FusedRetrievalCandidate, FusedRetrievalResult
from ringkas_worker.retrieval import DenseRetrievalCandidate, DenseRetrievalResult
from ringkas_worker.retrieval_debug import (
    ResolvedRetrievalFilters,
    RetrievalDebugConfigurationError,
    RetrievalDebugLogger,
    RetrievalDebugSettings,
)
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult
from ringkas_worker.sparse_retrieval import (
    SparseRetrievalCandidate,
    SparseRetrievalResult,
)


class Sink:
    def __init__(self, error: Exception | None = None) -> None:
        self.messages: list[str] = []
        self.error = error

    def info(self, message: str) -> None:
        if self.error:
            raise self.error
        self.messages.append(message)


def _dense_candidate(rank: int = 1) -> DenseRetrievalCandidate:
    return DenseRetrievalCandidate(
        rank,
        0.9,
        f"point-{rank}",
        f"00000000-0000-0000-0000-{rank:012d}",
        "00000000-0000-0000-0000-000000000001",
        "secret title",
        2024,
        "DKI Jakarta",
        "province",
        "secret topic",
        1,
        2,
        "secret heading",
        rank,
        "text_layer",
        False,
        "https://secret.example",
        "https://secret.example/file.pdf",
    )


def _sparse_candidate(rank: int = 1) -> SparseRetrievalCandidate:
    return SparseRetrievalCandidate(
        rank,
        0.8,
        f"point-{rank}",
        f"00000000-0000-0000-0000-{rank:012d}",
        "00000000-0000-0000-0000-000000000001",
        "secret title",
        2024,
        "DKI Jakarta",
        "province",
        "secret topic",
        1,
        2,
        "secret heading",
        rank,
        "text_layer",
        False,
        "https://secret.example",
        "https://secret.example/file.pdf",
    )


def _fused_candidate(rank: int = 1) -> FusedRetrievalCandidate:
    return FusedRetrievalCandidate(
        rank,
        0.5,
        f"00000000-0000-0000-0000-{rank:012d}",
        "00000000-0000-0000-0000-000000000001",
        f"point-{rank}",
        rank,
        rank,
        0.9,
        0.8,
        "secret title",
        2024,
        "DKI Jakarta",
        "province",
        "secret topic",
        1,
        2,
        "secret heading",
        rank,
        "text_layer",
        False,
        "https://secret.example",
        "https://secret.example/file.pdf",
    )


def _results(count: int = 2):
    dense = DenseRetrievalResult(
        "collection",
        20,
        tuple(_dense_candidate(index) for index in range(1, count + 1)),
    )
    sparse = SparseRetrievalResult(
        "collection",
        20,
        tuple(_sparse_candidate(index) for index in range(1, count + 1)),
    )
    fused = FusedRetrievalResult(
        "collection",
        60,
        tuple(_fused_candidate(index) for index in range(1, count + 1)),
    )
    final = FinalRetrievalResult(
        10,
        tuple(
            FinalRetrievalCandidate(
                candidate.rank,
                candidate.rrf_score,
                candidate.chunk_id,
                candidate.document_id,
                candidate.qdrant_point_id,
                candidate.dense_rank,
                candidate.sparse_rank,
                candidate.dense_score,
                candidate.sparse_score,
                candidate.title,
                candidate.publication_year,
                candidate.region,
                candidate.region_level,
                candidate.topic,
                candidate.page_start,
                candidate.page_end,
                candidate.section_heading,
                candidate.chunk_index,
                candidate.extraction_method,
                candidate.low_structure_confidence,
                candidate.source_url,
                candidate.pdf_url,
            )
            for candidate in fused.candidates
        ),
    )
    return dense, sparse, fused, final


def _event(sink: Sink) -> dict:
    return json.loads(sink.messages[0])


def test_settings_defaults_and_environment(monkeypatch):
    assert RetrievalDebugSettings() == RetrievalDebugSettings()
    monkeypatch.setenv("RETRIEVAL_DEBUG_LOG_ENABLED", "yes")
    monkeypatch.setenv("RETRIEVAL_DEBUG_INCLUDE_SENSITIVE_TEXT", "on")
    monkeypatch.setenv("RETRIEVAL_DEBUG_INCLUDE_SCORES", "1")
    monkeypatch.setenv("RETRIEVAL_DEBUG_QUERY_MAX_CHARS", "50")
    monkeypatch.setenv("RETRIEVAL_DEBUG_MAX_CANDIDATES", "7")
    assert RetrievalDebugSettings.from_environment() == RetrievalDebugSettings(
        True, True, True, 50, 7
    )


@pytest.mark.parametrize(
    "name,value",
    [
        ("RETRIEVAL_DEBUG_LOG_ENABLED", "maybe"),
        ("RETRIEVAL_DEBUG_INCLUDE_SCORES", ""),
        ("RETRIEVAL_DEBUG_INCLUDE_SENSITIVE_TEXT", "2"),
    ],
)
def test_invalid_boolean_configuration_is_safe(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RetrievalDebugConfigurationError) as error:
        RetrievalDebugSettings.from_environment()
    assert not value or value not in str(error.value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("RETRIEVAL_DEBUG_QUERY_MAX_CHARS", "0"),
        ("RETRIEVAL_DEBUG_QUERY_MAX_CHARS", "501"),
        ("RETRIEVAL_DEBUG_MAX_CANDIDATES", "-1"),
        ("RETRIEVAL_DEBUG_MAX_CANDIDATES", "101"),
        ("RETRIEVAL_DEBUG_MAX_CANDIDATES", "true"),
        ("RETRIEVAL_DEBUG_QUERY_MAX_CHARS", "bad"),
    ],
)
def test_invalid_numeric_configuration_is_safe(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RetrievalDebugConfigurationError) as error:
        RetrievalDebugSettings.from_environment()
    assert value not in str(error.value)


def test_disabled_logger_does_not_inspect_inputs():
    sink = Sink()
    logger = RetrievalDebugLogger(logger=sink)
    assert logger.snapshot(object(), object(), dense=object()) is False
    assert sink.messages == []


def test_query_and_filters_are_bounded_and_private_by_default():
    sink = Sink()
    RetrievalDebugLogger(RetrievalDebugSettings(enabled=True), sink).snapshot(
        "line\n\twith\x00 secret",
        {"publication_year": 2024, "topic": "secret topic", "unknown": "credential"},
    )
    event = _event(sink)
    assert event["query"] == {"queryLength": 18, "textIncluded": False}
    assert event["filters"] == {
        "publication_year": 2024,
        "textIncluded": False,
        "topic": {"present": True},
    }
    assert "hash" not in sink.messages[0].lower()


def test_sensitive_query_filter_text_is_normalized_and_truncated():
    sink = Sink()
    settings = RetrievalDebugSettings(
        enabled=True, include_sensitive_text=True, query_preview_max_chars=5
    )
    RetrievalDebugLogger(settings, sink).snapshot(
        " a\n\tb  c ",
        ResolvedRetrievalFilters(topic=" x\nyyy ", document_title="title"),
    )
    event = _event(sink)
    assert event["query"]["preview"] == "a b c"
    assert event["query"]["truncated"] is False
    assert event["filters"]["topic"] == {
        "preview": "x yyy",
        "present": True,
        "truncated": False,
    }
    assert event["filters"]["document_title"]["preview"] == "title"


def test_all_stages_are_summarized_without_sensitive_fields_or_scores():
    sink = Sink()
    dense, sparse, fused, final = _results(3)
    RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, max_candidates_per_stage=2), sink
    ).snapshot("q", {}, dense=dense, sparse=sparse, fused=fused, final=final)
    event = _event(sink)
    assert [stage["stage"] for stage in event["stages"]] == [
        "dense",
        "sparse",
        "fused",
        "final",
    ]
    assert all(
        stage["returnedCandidateCount"] == 3
        and stage["loggedCandidateCount"] == 2
        and stage["capped"]
        for stage in event["stages"]
    )
    assert event["stages"][0]["candidates"][0] == {
        "chunkId": "00000000-0000-0000-0000-000000000001",
        "documentId": "00000000-0000-0000-0000-000000000001",
        "rank": 1,
    }
    assert "secret" not in sink.messages[0]
    assert "score" not in sink.messages[0].lower()
    assert "vector" not in sink.messages[0].lower()


def test_scores_and_source_ranks_are_opt_in():
    sink = Sink()
    dense, sparse, fused, final = _results(1)
    RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, include_scores=True), sink
    ).snapshot("q", {}, dense=dense, sparse=sparse, fused=fused, final=final)
    event = _event(sink)
    assert event["stages"][0]["candidates"][0]["score"] == 0.9
    assert event["stages"][2]["candidates"][0]["rrfScore"] == 0.5
    assert event["stages"][3]["candidates"][0]["denseRank"] == 1


def test_logging_failure_is_swallowed_and_source_results_are_unchanged():
    sink = Sink(error=RuntimeError("secret logger failure"))
    dense, _, _, _ = _results(1)
    assert (
        RetrievalDebugLogger(RetrievalDebugSettings(enabled=True), sink).snapshot(
            "q", {}, dense=dense
        )
        is False
    )
    assert dense.candidates[0].chunk_id == "00000000-0000-0000-0000-000000000001"
    assert sink.messages == []


def test_opted_in_previews_redact_credentials_tokens_urls_and_email():
    sink = Sink()
    raw = (
        "Authorization: Bearer bearer-secret Basic basic-secret "
        "api_key=api-secret password:pw-secret cookie=cookie-secret "
        "https://user:url-secret@example.test "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature-secret "
        "sk-123456789 email@example.test"
    )
    RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, include_sensitive_text=True), sink
    ).snapshot(raw, {"topic": raw})
    message = sink.messages[0]
    assert message.count("[REDACTED]") >= 10
    for secret in (
        "bearer-secret",
        "basic-secret",
        "api-secret",
        "pw-secret",
        "cookie-secret",
        "url-secret",
        "signature-secret",
        "sk-123456789",
        "email@example.test",
    ):
        assert secret not in message


class _TrackingString(str):
    requested_stop: int | None = None

    def __getitem__(self, key):
        if isinstance(key, slice):
            self.requested_stop = key.stop
        return super().__getitem__(key)


def test_preview_processing_uses_bounded_source_prefix():
    query = _TrackingString("x" * 10_000)
    sink = Sink()
    RetrievalDebugLogger(
        RetrievalDebugSettings(
            enabled=True, include_sensitive_text=True, query_preview_max_chars=10
        ),
        sink,
    ).snapshot(query)
    event = _event(sink)
    assert query.requested_stop is not None and query.requested_stop < len(query)
    assert len(event["query"]["preview"]) == 10
    assert event["query"]["truncated"] is True


def test_title_alias_is_emitted_as_document_title_only():
    sink = Sink()
    RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, include_sensitive_text=True), sink
    ).snapshot("q", {"title": "resolved title", "nested": {"secret": "value"}})
    filters = _event(sink)["filters"]
    assert filters["document_title"]["preview"] == "resolved title"
    assert "title" not in filters
    assert "nested" not in filters


@pytest.mark.parametrize(
    "candidate_update",
    [
        {"chunk_id": "not-a-uuid"},
        {"chunk_id": "00000000-0000-0000-0000-000000000000secret"},
        {"rank": True},
    ],
)
def test_malformed_candidate_fails_closed(candidate_update):
    candidate = replace(_dense_candidate(), **candidate_update)
    result = DenseRetrievalResult("collection", 20, (candidate,))
    sink = Sink()
    assert (
        RetrievalDebugLogger(RetrievalDebugSettings(enabled=True), sink).snapshot(
            "q", {}, dense=result
        )
        is False
    )
    assert sink.messages == []


def test_invalid_requested_limit_fails_closed():
    result = DenseRetrievalResult("collection", True, (_dense_candidate(),))
    sink = Sink()
    assert (
        RetrievalDebugLogger(RetrievalDebugSettings(enabled=True), sink).snapshot(
            "q", {}, dense=result
        )
        is False
    )
    assert sink.messages == []


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_non_finite_score_fails_closed(score):
    candidate = replace(_dense_candidate(), score=score)
    result = DenseRetrievalResult("collection", 20, (candidate,))
    sink = Sink()
    assert (
        RetrievalDebugLogger(
            RetrievalDebugSettings(enabled=True, include_scores=True), sink
        ).snapshot("q", {}, dense=result)
        is False
    )
    assert sink.messages == []


def test_candidate_cap_preserves_order_and_source_result():
    dense, _, _, _ = _results(3)
    original = dense.candidates
    sink = Sink()
    assert RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, max_candidates_per_stage=2), sink
    ).snapshot("q", {}, dense=dense)
    candidates = _event(sink)["stages"][0]["candidates"]
    assert [candidate["rank"] for candidate in candidates] == [1, 2]
    assert dense.candidates is original


def test_integer_configuration_has_no_context_or_traceback_value(monkeypatch):
    invalid = "invalid-secret-value"
    monkeypatch.setenv("RETRIEVAL_DEBUG_MAX_CANDIDATES", invalid)
    try:
        RetrievalDebugSettings.from_environment()
    except RetrievalDebugConfigurationError as error:
        assert error.__cause__ is None
        assert error.__context__ is None
        assert invalid not in traceback.format_exc()
    else:
        pytest.fail("invalid integer configuration was accepted")


def test_json_serialization_failure_is_isolated(monkeypatch):
    sink = Sink()

    def fail_json(*args, **kwargs):
        raise RuntimeError("serialization secret")

    monkeypatch.setattr("ringkas_worker.retrieval_debug.json.dumps", fail_json)
    assert (
        RetrievalDebugLogger(RetrievalDebugSettings(enabled=True), sink).snapshot("q")
        is False
    )
    assert sink.messages == []


@pytest.mark.parametrize(
    "raw,secret",
    [
        ('token="alpha beta"', "alpha beta"),
        ("password='gamma delta'", "gamma delta"),
        ("api_key=epsilon-secret", "epsilon-secret"),
    ],
)
def test_named_secret_values_are_fully_redacted(raw, secret):
    sink = Sink()
    assert RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, include_sensitive_text=True), sink
    ).snapshot(raw)
    message = sink.messages[0]
    assert secret not in message
    assert "[REDACTED]" in message


@pytest.mark.parametrize(
    "raw,fragments",
    [
        ('token="alpha \\"beta secret\\" gamma"', ("alpha", "beta secret", "gamma")),
        ("token='alpha \\'beta secret\\' gamma'", ("alpha", "beta secret", "gamma")),
        ('token="alpha \\\\ beta"', ("alpha", "beta")),
        ("token='alpha \\\\ beta'", ("alpha", "beta")),
        (
            'token="alpha \\"beta\\" \\"gamma\\" delta"',
            ("alpha", "beta", "gamma", "delta"),
        ),
    ],
)
def test_escaped_delimiters_in_quoted_secrets_are_fully_redacted(raw, fragments):
    sink = Sink()
    assert RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, include_sensitive_text=True), sink
    ).snapshot(raw)
    message = sink.messages[0]
    for fragment in fragments:
        assert fragment not in message
    assert "[REDACTED]" in message


@pytest.mark.parametrize(
    "raw,identifier",
    [
        ('user_id="user alpha"', "user alpha"),
        ("user-id='user beta'", "user beta"),
        ("userId=user-gamma", "user-gamma"),
        ('session_id="session alpha"', "session alpha"),
        ("session-id='session beta'", "session beta"),
        ("sessionId=session-gamma", "session-gamma"),
    ],
)
def test_user_and_session_identifiers_are_redacted(raw, identifier):
    sink = Sink()
    assert RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, include_sensitive_text=True), sink
    ).snapshot(raw)
    message = sink.messages[0]
    assert identifier not in message
    assert "[REDACTED]" in message


@pytest.mark.parametrize("token", ["sk-123456789", "SK-123456789", "sK-123456789"])
def test_secret_prefixed_tokens_are_case_insensitively_redacted(token):
    sink = Sink()
    assert RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, include_sensitive_text=True), sink
    ).snapshot(token)
    assert token not in sink.messages[0]
    assert "[REDACTED]" in sink.messages[0]


def test_malformed_candidate_beyond_cap_is_not_inspected():
    valid = (_dense_candidate(1), _dense_candidate(2))
    result = DenseRetrievalResult("collection", 20, (*valid, object()))
    sink = Sink()
    assert RetrievalDebugLogger(
        RetrievalDebugSettings(enabled=True, max_candidates_per_stage=2), sink
    ).snapshot("q", {}, dense=result)
    stage = _event(sink)["stages"][0]
    assert stage["returnedCandidateCount"] == 3
    assert stage["loggedCandidateCount"] == 2
    assert stage["capped"] is True
    assert [candidate["rank"] for candidate in stage["candidates"]] == [1, 2]


def test_malformed_candidate_inside_cap_fails_closed():
    result = DenseRetrievalResult("collection", 20, (_dense_candidate(), object()))
    sink = Sink()
    assert (
        RetrievalDebugLogger(
            RetrievalDebugSettings(enabled=True, max_candidates_per_stage=2), sink
        ).snapshot("q", {}, dense=result)
        is False
    )
    assert sink.messages == []
