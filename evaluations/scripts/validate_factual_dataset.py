#!/usr/bin/env python3
"""Validate every evaluation record against the live authoritative PostgreSQL corpus."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg


EVALUATIONS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = EVALUATIONS_DIR / "evaluation_dataset.json"
DEFAULT_REPORT = EVALUATIONS_DIR / "dataset_validation_report.json"
EXPECTED_TYPES = {"definition", "number", "period", "region", "methodology", "document_search"}
MAX_RECORDS_PER_CHUNK = 1

DEFINITION_RE = re.compile(
    r"\b(?:adalah|merupakan|yaitu|dimaksud dengan|didefinisikan sebagai|diartikan sebagai|merujuk pada)\b",
    re.IGNORECASE,
)
METHOD_RE = re.compile(
    r"\b(?:survei|survey|sensus|enumerasi|pencacahan|metodologi|metode pengumpulan|sumber data|data diperoleh|responden|pendataan|sampling)\b",
    re.IGNORECASE,
)
PERIOD_RE = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\b",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*(?:\s*%|\s*(?:juta|ribu|orang|unit|persen|ton|hektar|km2|km²))?", re.IGNORECASE)
REGION_RE = re.compile(
    r"\b(?:DKI Jakarta|Jakarta (?:Utara|Selatan|Timur|Barat|Pusat)|Kepulauan Seribu|"
    r"Kota Jakarta(?: Utara| Selatan| Timur| Barat| Pusat)?|Indonesia|Banten|Jawa Barat|Jawa Tengah|Jawa Timur)\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
STOPWORDS = {
    "adalah", "akan", "atau", "bahwa", "dan", "dalam", "dari", "data", "dengan", "di", "ini", "itu",
    "jumlah", "ke", "lebih", "menurut", "pada", "sebagai", "sebesar", "secara", "serta", "tahun", "tentang",
    "tercatat", "terdapat", "untuk", "yang", "provinsi", "dokumen", "tabel", "gambar", "the", "of", "and",
    "by", "for", "in", "on", "number", "percentage", "province", "total", "table", "figure",
    "januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus", "september", "oktober", "november", "desember",
}
GENERIC_FRAGMENTS = (
    "apa definisi atau penjelasan mengenai",
    "berapa angka atau statistik terkait",
    "wilayah mana yang menjadi fokus utama",
    "bagaimana metodologi pengumpulan data yang dijelaskan",
    "dokumen apa yang membahas topik",
)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_question(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def words(value: str) -> set[str]:
    return {
        token.casefold()
        for token in WORD_RE.findall(value)
        if len(token) >= 4 and token.casefold() not in STOPWORDS and not token.isdigit()
    }


def numeric_tokens(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)*", value))


def load_model(payload: dict[str, Any]) -> None:
    src = EVALUATIONS_DIR / "src"
    sys.path.insert(0, str(src))
    from evaluation_dataset import EvaluationDataset

    EvaluationDataset.model_validate(payload)


def fetch_authoritative(database_url: str, chunk_ids: list[UUID]) -> dict[str, tuple[Any, ...]]:
    query = """
        SELECT c.id, c.document_id, c.text, c.page_start, c.page_end, c.source_url,
               c.qdrant_point_id, d.title, d.publication_year, d.region
        FROM chunks AS c
        JOIN documents AS d ON d.id = c.document_id
        WHERE c.id = ANY(%s) AND d.ingestion_status = 'indexed'
    """
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (chunk_ids,))
            return {str(row[0]): row for row in cursor.fetchall()}


def validate_record(record: dict[str, Any], authoritative: tuple[Any, ...] | None) -> list[str]:
    errors: list[str] = []
    evidence = record.get("evidence") or {}
    ground_truth = record.get("ground_truth") or {}
    question_type = record.get("question_type")
    question = str(record.get("question_text") or "")
    reference = str(record.get("reference_answer") or "")
    excerpt = str(evidence.get("excerpt") or "")
    normalized_excerpt = normalize(excerpt)
    normalized_reference = normalize(reference)

    if question_type not in EXPECTED_TYPES:
        errors.append("question_type is not approved")
    if not question.strip():
        errors.append("question is empty")
    if not str(record.get("topic") or "").strip():
        errors.append("topic is empty")
    if not normalized_reference:
        errors.append("reference_answer is empty")
    if any(fragment in question.casefold() for fragment in GENERIC_FRAGMENTS):
        errors.append("generic question template")
    for field in ("document_id", "chunk_id", "qdrant_point_id", "document_title", "publication_year", "region", "page_start", "page_end", "source_url", "excerpt"):
        if evidence.get(field) in (None, ""):
            errors.append(f"evidence {field} is missing")
    for field in ("expected_document_id", "expected_chunk_id", "expected_qdrant_point_id", "expected_page_start", "expected_page_end"):
        if ground_truth.get(field) in (None, ""):
            errors.append(f"ground_truth {field} is missing")
    question_words = words(question)
    evidence_word_overlap = question_words.intersection(words(excerpt))
    period_overlap = numeric_tokens(question).intersection(numeric_tokens(excerpt))
    has_specific_period = question_type == "period" and bool(period_overlap)
    has_specific_method = question_type == "methodology" and bool(evidence_word_overlap)
    if len(evidence_word_overlap) < 2 and not has_specific_period and not has_specific_method:
        errors.append("question lacks at least two evidence-specific terms")
    if authoritative is None:
        errors.append("authoritative chunk/document does not exist or is not indexed")
        return errors

    chunk_id, document_id, text, page_start, page_end, source_url, qdrant_point_id, title, year, region = authoritative
    authoritative_excerpt = normalize(str(text or ""))
    if str(evidence.get("chunk_id")) != str(chunk_id):
        errors.append("evidence chunk_id differs from PostgreSQL")
    if str(evidence.get("document_id")) != str(document_id):
        errors.append("evidence document_id differs from PostgreSQL")
    expected_metadata = {
        "document_title": title,
        "publication_year": year,
        "region": region,
        "page_start": page_start,
        "page_end": page_end,
        "source_url": source_url,
        "qdrant_point_id": qdrant_point_id,
    }
    for field, expected in expected_metadata.items():
        if str(evidence.get(field)) != str(expected):
            errors.append(f"evidence {field} differs from PostgreSQL")
    if normalized_excerpt != authoritative_excerpt:
        errors.append("evidence excerpt is not the authoritative chunk text")
    if not source_url or not str(source_url).startswith(("http://", "https://")):
        errors.append("source URL is not an HTTP URL")

    expected_ground_truth = {
        "expected_document_id": document_id,
        "expected_chunk_id": chunk_id,
        "expected_qdrant_point_id": qdrant_point_id,
        "expected_page_start": page_start,
        "expected_page_end": page_end,
    }
    for field, expected in expected_ground_truth.items():
        if str(ground_truth.get(field)) != str(expected):
            errors.append(f"ground_truth {field} differs from PostgreSQL")

    if question_type == "document_search":
        if str(record.get("reference_answer")) != str(title):
            errors.append("document_search reference answer is not the authoritative title")
        topic_words = words(str(record.get("topic") or ""))
        if not topic_words.intersection(words(authoritative_excerpt)):
            errors.append("document_search topic is not evidenced by the chunk")
    elif normalized_reference not in authoritative_excerpt:
        errors.append("reference_answer is not supported by the excerpt")

    if not numeric_tokens(reference).issubset(numeric_tokens(excerpt)):
        errors.append("reference_answer contains a numeric token absent from the excerpt")
    if question_type == "definition" and not DEFINITION_RE.search(authoritative_excerpt):
        errors.append("definition question lacks a definition/explanatory statement")
    if question_type == "number" and (not NUMBER_RE.search(authoritative_excerpt) or not numeric_tokens(reference)):
        errors.append("number question lacks an exact numeric fact")
    if question_type == "period" and not PERIOD_RE.search(normalized_reference):
        errors.append("period question lacks an explicit period/year in the answer")
    if question_type == "region" and not (REGION_RE.search(authoritative_excerpt) or str(region).strip()):
        errors.append("region question lacks a named region")
    if question_type == "methodology" and not METHOD_RE.search(authoritative_excerpt):
        errors.append("methodology question lacks explicit methodology/source evidence")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-promote", action="store_true", help="validate without changing pending status to ready")
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    failures: list[dict[str, Any]] = []
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or len(records) != 1000:
        failures.append({"question_id": None, "errors": ["dataset must contain exactly 1000 records"]})
        records = records if isinstance(records, list) else []
    ids = [record.get("question_id") for record in records if isinstance(record, dict)]
    expected_ids = [f"q-{index:04d}" for index in range(1, 1001)]
    if ids != expected_ids:
        failures.append({"question_id": None, "errors": ["question IDs are not contiguous q-0001 through q-1000"]})
    if payload.get("capacity") != 1000:
        failures.append({"question_id": None, "errors": ["capacity must be 1000"]})
    if payload.get("dataset_status") not in {"pending_automated_validation", "ready"}:
        failures.append({"question_id": None, "errors": ["dataset_status is invalid"]})

    chunk_ids: list[UUID] = []
    invalid_uuid_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        value = str((record.get("evidence") or {}).get("chunk_id") or "")
        try:
            chunk_ids.append(UUID(value))
        except ValueError:
            invalid_uuid_ids.add(value)
    authoritative = fetch_authoritative(args.database_url, chunk_ids) if chunk_ids else {}
    seen_questions: Counter[str] = Counter()
    seen_chunks: Counter[str] = Counter()
    for record in records:
        if not isinstance(record, dict):
            failures.append({"question_id": None, "errors": ["record is not an object"]})
            continue
        question_id = record.get("question_id")
        errors = validate_record(record, None if str((record.get("evidence") or {}).get("chunk_id") or "") in invalid_uuid_ids else authoritative.get(str((record.get("evidence") or {}).get("chunk_id"))))
        normalized_question = normalize_question(str(record.get("question_text") or ""))
        seen_questions[normalized_question] += 1
        chunk_key = str((record.get("evidence") or {}).get("chunk_id") or "")
        seen_chunks[chunk_key] += 1
        if seen_questions[normalized_question] > 1:
            errors.append("duplicate normalized question")
        if seen_chunks[chunk_key] > MAX_RECORDS_PER_CHUNK:
            errors.append(f"chunk exceeds repetition limit {MAX_RECORDS_PER_CHUNK}")
        if errors:
            failures.append({"question_id": question_id, "errors": sorted(set(errors))})

    counts = {
        "question_type": dict(sorted(Counter(record.get("question_type") for record in records if isinstance(record, dict)).items())),
        "document": dict(sorted(Counter(str((record.get("evidence") or {}).get("document_id")) for record in records if isinstance(record, dict)).items())),
        "publication_year": dict(sorted(Counter(str((record.get("evidence") or {}).get("publication_year")) for record in records if isinstance(record, dict)).items())),
        "topic": dict(sorted(Counter(str(record.get("topic")) for record in records if isinstance(record, dict)).items())),
        "page": dict(sorted(Counter(str((record.get("evidence") or {}).get("page_start")) for record in records if isinstance(record, dict)).items())),
    }
    report: dict[str, Any] = {
        "status": "failed" if failures else "passed",
        "dataset_path": str(args.dataset),
        "dataset_status_before": payload.get("dataset_status"),
        "dataset_status_after": payload.get("dataset_status"),
        "records": len(records),
        "failures": len(failures),
        "rejected_records": failures,
        "counts": counts,
        "authoritative_chunks_loaded": len(authoritative),
        "max_records_per_chunk": MAX_RECORDS_PER_CHUNK,
    }
    if not failures and not args.no_promote:
        for record in payload["records"]:
            record["verification_status"] = "verified"
            record["reviewer_notes"] = "automatically validated against authoritative PostgreSQL chunk"
        payload["dataset_status"] = "ready"
        load_model(payload)
        args.dataset.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["dataset_status_after"] = "ready"
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "records": len(records),
        "failures": len(failures),
        "dataset_status": report["dataset_status_after"],
        "report": str(args.report),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
