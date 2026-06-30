import traceback
from dataclasses import replace
from uuid import uuid4

import pytest

from ringkas_worker.citations import (
    CitationPayload,
    CitationPersistenceError,
    CitationSourceMismatchError,
    CitationValidationError,
    GroundedCitationBuilder,
)
from ringkas_worker.db.citations import (
    CitationRepositoryError,
    CitationSourceLookupError,
    CitationSourceRepository,
    CitationSourceValidationError,
    PostgresCitationSourceRepository,
)
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult


class Cursor:
    def __init__(self, rows=(), failure=None):
        self.rows = tuple(rows)
        self.statements = []
        self.failure = failure

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.statements.append((sql, params))
        if self.failure:
            raise self.failure

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.cursor_value


def candidate(index, chunk_id, document_id, point_id, *, low=False):
    return FinalRetrievalCandidate(
        index,
        0.5,
        chunk_id,
        document_id,
        point_id,
        1,
        None,
        0.5,
        None,
        "Title",
        2025,
        "DKI Jakarta",
        "province",
        "economy",
        2,
        3,
        "Heading",
        0,
        "text_layer",
        low,
        "https://bps.test/source",
        "https://bps.test/file.pdf",
    )


def source(
    candidate_value, *, text="authoritative full text", status="indexed", **changes
):
    values = {
        "chunk_id": candidate_value.chunk_id,
        "document_id": candidate_value.document_id,
        "point_id": candidate_value.qdrant_point_id,
        "chunk_index": candidate_value.chunk_index,
        "text": text,
        "page_start": candidate_value.page_start,
        "page_end": candidate_value.page_end,
        "heading": candidate_value.section_heading,
        "extraction": candidate_value.extraction_method,
        "low": candidate_value.low_structure_confidence,
        "chunk_url": candidate_value.source_url,
        "title": candidate_value.title,
        "year": candidate_value.publication_year,
        "region": candidate_value.region,
        "level": candidate_value.region_level,
        "topic": candidate_value.topic,
        "pdf": candidate_value.pdf_url,
        "status": status,
    }
    values.update(changes)
    return (
        values["chunk_id"],
        values["document_id"],
        values["point_id"],
        values["chunk_index"],
        values["text"],
        values["page_start"],
        values["page_end"],
        values["heading"],
        values["extraction"],
        values["low"],
        values["chunk_url"],
        values["title"],
        values["year"],
        values["region"],
        values["level"],
        values["topic"],
        values["pdf"],
        values["status"],
    )


def test_repository_batches_one_parameterized_query_and_preserves_rows_for_builder():
    ids = uuid4(), uuid4(), uuid4()
    candidates = tuple(
        candidate(i + 1, str(ids[i]), str(uuid4()), str(uuid4())) for i in range(3)
    )
    cursor = Cursor(
        [source(candidates[2]), source(candidates[0]), source(candidates[1])]
    )
    repository = PostgresCitationSourceRepository(
        "postgresql://secret", lambda: Connection(cursor)
    )
    assert isinstance(repository, CitationSourceRepository)
    records = repository.get_by_chunk_ids(tuple(item.chunk_id for item in candidates))
    assert len(cursor.statements) == 1
    assert (
        "%s" in cursor.statements[0][0] and "JOIN documents" in cursor.statements[0][0]
    )
    assert cursor.statements[0][1] == ([ids[0], ids[1], ids[2]],)
    assert all(type(value) is type(ids[0]) for value in cursor.statements[0][1][0])
    assert {record.chunk_id for record in records} == {
        item.chunk_id for item in candidates
    }


def test_builder_preserves_final_order_and_authoritative_excerpt_without_scores():
    document_id, point_a, point_b = str(uuid4()), str(uuid4()), str(uuid4())
    a = candidate(1, str(uuid4()), document_id, point_a)
    b = candidate(2, str(uuid4()), document_id, point_b)
    cursor = Cursor([source(b), source(a)])
    result = GroundedCitationBuilder(
        PostgresCitationSourceRepository("unused", lambda: Connection(cursor))
    ).build(FinalRetrievalResult(10, (a, b)))
    assert [item.chunk_id for item in result.citations] == [a.chunk_id, b.chunk_id]
    assert result.citations[0].excerpt == "authoritative full text"
    assert not hasattr(result.citations[0], "rrf_score")
    assert all(isinstance(item, CitationPayload) for item in result.citations)


def test_missing_or_nonindexed_source_fails_without_silent_drop():
    item = candidate(1, str(uuid4()), str(uuid4()), str(uuid4()))
    cursor = Cursor([])
    builder = GroundedCitationBuilder(
        PostgresCitationSourceRepository("unused", lambda: Connection(cursor))
    )
    with pytest.raises(CitationSourceMismatchError):
        builder.build(FinalRetrievalResult(10, (item,)))
    cursor = Cursor([source(item, status="parsed")])
    with pytest.raises(CitationSourceMismatchError):
        GroundedCitationBuilder(
            PostgresCitationSourceRepository("unused", lambda: Connection(cursor))
        ).build(FinalRetrievalResult(10, (item,)))


def test_empty_input_does_not_query_and_database_failures_are_sanitized():
    cursor = Cursor(failure=RuntimeError("postgresql://db-secret chunk text"))
    repository = PostgresCitationSourceRepository("unused", lambda: Connection(cursor))
    assert repository.get_by_chunk_ids(()) == ()
    assert not cursor.statements
    with pytest.raises(CitationSourceLookupError) as caught:
        repository.get_by_chunk_ids((str(uuid4()),))
    assert "secret" not in str(caught.value).lower()
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_invalid_scalar_and_duplicate_ids_are_rejected():
    repository = PostgresCitationSourceRepository(
        "unused", lambda: pytest.fail("database must not be queried")
    )
    with pytest.raises(CitationSourceValidationError):
        repository.get_by_chunk_ids(str(uuid4()))
    value = str(uuid4())
    with pytest.raises(CitationSourceValidationError):
        repository.get_by_chunk_ids((value, value))


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_title", " "),
        ("publication_year", 0),
        ("region", " "),
        ("region_level", " "),
        ("chunk_source_url", " "),
        ("chunk_text", " "),
        ("chunk_index", -1),
        ("extraction_method", "ocr"),
        ("low_structure_confidence", "false"),
        ("page_start", 0),
    ],
)
def test_invalid_authoritative_metadata_is_rejected_without_exposing_excerpt(
    field, value
):
    item = candidate(1, str(uuid4()), str(uuid4()), str(uuid4()))
    row = list(source(item, text="private excerpt"))
    positions = {
        "chunk_index": 3,
        "chunk_text": 4,
        "page_start": 5,
        "extraction_method": 8,
        "low_structure_confidence": 9,
        "chunk_source_url": 10,
        "document_title": 11,
        "publication_year": 12,
        "region": 13,
        "region_level": 14,
    }
    row[positions[field]] = value
    builder = GroundedCitationBuilder(
        PostgresCitationSourceRepository(
            "unused", lambda: Connection(Cursor([tuple(row)]))
        )
    )
    with pytest.raises(CitationValidationError) as caught:
        builder.build(FinalRetrievalResult(10, (item,)))
    assert "private excerpt" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_conflicting_authoritative_metadata_fails_complete_build():
    item = candidate(1, str(uuid4()), str(uuid4()), str(uuid4()))
    cursor = Cursor([source(item, title="Different title")])
    with pytest.raises(CitationSourceMismatchError):
        GroundedCitationBuilder(
            PostgresCitationSourceRepository("unused", lambda: Connection(cursor))
        ).build(FinalRetrievalResult(10, (item,)))


def test_duplicate_and_extra_source_rows_fail_safely():
    first = candidate(1, str(uuid4()), str(uuid4()), str(uuid4()))
    second = candidate(2, str(uuid4()), first.document_id, str(uuid4()))
    with pytest.raises(CitationSourceLookupError):
        PostgresCitationSourceRepository(
            "unused", lambda: Connection(Cursor([source(first), source(first)]))
        ).get_by_chunk_ids((first.chunk_id,))
    with pytest.raises(CitationSourceMismatchError):
        GroundedCitationBuilder(
            PostgresCitationSourceRepository(
                "unused", lambda: Connection(Cursor([source(first), source(second)]))
            )
        ).build(FinalRetrievalResult(10, (first,)))


@pytest.mark.parametrize("candidates", [(object(),), ("not-candidates",)])
def test_malformed_candidate_collections_are_typed(candidates):
    with pytest.raises(CitationValidationError):
        GroundedCitationBuilder(
            PostgresCitationSourceRepository(
                "unused", lambda: pytest.fail("database must not be queried")
            )
        ).build(FinalRetrievalResult(10, candidates))


def test_invalid_candidate_rank_and_duplicate_ids_are_typed():
    first = candidate(2, str(uuid4()), str(uuid4()), str(uuid4()))
    with pytest.raises(CitationValidationError):
        GroundedCitationBuilder(
            PostgresCitationSourceRepository(
                "unused", lambda: pytest.fail("database must not be queried")
            )
        ).build(FinalRetrievalResult(10, (first,)))
    first = candidate(1, str(uuid4()), str(uuid4()), str(uuid4()))
    duplicate = replace(first, rank=2)
    with pytest.raises(CitationValidationError):
        GroundedCitationBuilder(
            PostgresCitationSourceRepository(
                "unused", lambda: pytest.fail("database must not be queried")
            )
        ).build(FinalRetrievalResult(10, (first, duplicate)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("citation_id", str(uuid4())),
        ("excerpt", " "),
        ("source_url", " "),
        ("order", 0),
    ],
)
def test_public_citation_payload_invariants_are_mandatory(field, value):
    item = CitationPayload(
        "00000000-0000-0000-0000-000000000001",
        1,
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "Title",
        2025,
        "Region",
        "province",
        None,
        None,
        None,
        None,
        "https://bps.test",
        None,
        "excerpt",
        False,
    )
    with pytest.raises(CitationValidationError):
        replace(item, **{field: value})


def test_unexpected_repository_errors_are_sanitized():
    class BrokenRepository:
        def get_by_chunk_ids(self, _ids):
            raise RuntimeError("postgresql://user:secret@db private excerpt")

    item = candidate(1, str(uuid4()), str(uuid4()), str(uuid4()))
    with pytest.raises(CitationPersistenceError) as caught:
        GroundedCitationBuilder(BrokenRepository()).build(
            FinalRetrievalResult(10, (item,))
        )
    rendered = "".join(traceback.format_exception(caught.value))
    assert "secret" not in rendered and "private excerpt" not in rendered
    assert caught.value.__cause__ is None and caught.value.__context__ is None


@pytest.mark.parametrize(
    "document_id",
    ["00000000-0000-0000-0000-00000000000A", "{00000000-0000-0000-0000-000000000001}"],
)
def test_document_id_must_be_canonical(document_id):
    with pytest.raises(CitationValidationError):
        CitationPayload(
            "00000000-0000-0000-0000-000000000001",
            1,
            "00000000-0000-0000-0000-000000000001",
            document_id,
            "Title",
            2025,
            "Region",
            "province",
            None,
            None,
            None,
            None,
            "https://bps.test",
            None,
            "excerpt",
            False,
        )


def raising_sources():
    yield object()
    raise RuntimeError("secret during materialization")


@pytest.mark.parametrize(
    "repository",
    [
        type(
            "RuntimeFailure",
            (),
            {
                "get_by_chunk_ids": lambda self, _ids: (_ for _ in ()).throw(
                    RuntimeError("secret")
                )
            },
        )(),
        type(
            "TypedFailure",
            (),
            {
                "get_by_chunk_ids": lambda self, _ids: (_ for _ in ()).throw(
                    CitationRepositoryError("secret")
                )
            },
        )(),
        type("NoneResult", (), {"get_by_chunk_ids": lambda self, _ids: None})(),
        type("BadResult", (), {"get_by_chunk_ids": lambda self, _ids: 3})(),
        type(
            "IteratorFailure",
            (),
            {"get_by_chunk_ids": lambda self, _ids: raising_sources()},
        )(),
    ],
)
def test_untrusted_repository_boundary_is_normalized(repository):
    item = candidate(1, str(uuid4()), str(uuid4()), str(uuid4()))
    with pytest.raises(CitationPersistenceError) as caught:
        GroundedCitationBuilder(repository).build(FinalRetrievalResult(10, (item,)))
    rendered = "".join(traceback.format_exception(caught.value))
    assert (
        "secret" not in rendered
        and caught.value.__cause__ is None
        and caught.value.__context__ is None
    )
