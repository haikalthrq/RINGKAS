import os
from uuid import uuid4

import psycopg
import pytest

from ringkas_worker.citations import GroundedCitationBuilder
from ringkas_worker.db.citations import PostgresCitationSourceRepository
from ringkas_worker.selection import FinalRetrievalCandidate, FinalRetrievalResult


DATABASE_URL = os.getenv("RINGKAS_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set RINGKAS_POSTGRES_TEST_URL for PostgreSQL integration tests",
)


def test_postgres_lookup_and_grounded_builder_preserve_authoritative_excerpt_and_order():
    document_id, first_id, second_id = uuid4(), uuid4(), uuid4()
    point_ids = str(uuid4()), str(uuid4())
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO documents (id, title, publication_year, region, region_level, source_page_url, pdf_url, ingestion_status, checksum) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    document_id,
                    "Citation integration",
                    2025,
                    "DKI Jakarta",
                    "province",
                    "https://bps.test/source",
                    "https://bps.test/file.pdf",
                    "indexed",
                    f"citation-{document_id}",
                ),
            )
            for index, chunk_id, point_id, text in (
                (0, first_id, point_ids[0], "Exact first excerpt."),
                (1, second_id, point_ids[1], "Exact second excerpt."),
            ):
                connection.execute(
                    "INSERT INTO chunks (id, document_id, chunk_index, text, page_start, page_end, section_heading, extraction_method, low_structure_confidence, source_url, qdrant_point_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        chunk_id,
                        document_id,
                        index,
                        text,
                        index + 1,
                        index + 1,
                        "Heading",
                        "text_layer",
                        False,
                        "https://bps.test/source",
                        point_id,
                    ),
                )
        candidates = tuple(
            FinalRetrievalCandidate(
                rank,
                0.5,
                str(chunk_id),
                str(document_id),
                point_id,
                1,
                None,
                0.5,
                None,
                "Citation integration",
                2025,
                "DKI Jakarta",
                "province",
                None,
                index + 1,
                index + 1,
                "Heading",
                index,
                "text_layer",
                False,
                "https://bps.test/source",
                "https://bps.test/file.pdf",
            )
            for rank, (index, chunk_id, point_id) in enumerate(
                ((1, second_id, point_ids[1]), (0, first_id, point_ids[0])), 1
            )
        )
        result = GroundedCitationBuilder(
            PostgresCitationSourceRepository(DATABASE_URL)
        ).build(FinalRetrievalResult(10, candidates))
        assert [citation.chunk_id for citation in result.citations] == [
            str(second_id),
            str(first_id),
        ]
        assert [citation.excerpt for citation in result.citations] == [
            "Exact second excerpt.",
            "Exact first excerpt.",
        ]
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("DELETE FROM documents WHERE id = %s", (document_id,))
