#!/usr/bin/env python3
"""Build the 1,000-question evaluation set from authoritative PostgreSQL chunks.

The generator is intentionally deterministic and does not call an LLM.  Questions
are made from sentence-level facts that are present in the selected chunk.  The
result is written as pending until validate_factual_dataset.py promotes it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg


EVALUATIONS_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = EVALUATIONS_DIR / "evaluation_dataset.json"
TARGET_SIZE = 1000
MAX_RECORDS_PER_CHUNK = 1
QUESTION_TYPES = ("definition", "number", "period", "region", "methodology", "document_search")
TYPE_TARGETS = {
    "definition": 167,
    "number": 167,
    "period": 167,
    "region": 167,
    "methodology": 166,
    "document_search": 166,
}

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


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: UUID
    document_id: UUID
    chunk_text: str
    page_start: int
    page_end: int
    source_url: str
    qdrant_point_id: str
    section_heading: str | None
    title: str
    publication_year: int
    region: str
    topic: str | None


@dataclass(frozen=True)
class Candidate:
    row: ChunkRow
    question_type: str
    topic: str
    anchor: str
    reference_answer: str


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_question(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def stable_key(candidate: Candidate) -> str:
    raw = f"{candidate.question_type}:{candidate.row.chunk_id}:{candidate.anchor}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def split_sentences(text: str) -> list[str]:
    normalized = normalize_text(text)
    parts = re.split(r"(?<=[.!?])\s+|(?<=;)\s+", normalized)
    return [part.strip(" -") for part in parts if len(part.strip()) >= 35]


def content_words(value: str) -> set[str]:
    return {
        word.casefold()
        for word in WORD_RE.findall(value)
        if len(word) >= 4 and word.casefold() not in STOPWORDS and not word.isdigit()
    }


def numeric_tokens(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)*", value))


def evidence_topic(row: ChunkRow, sentence: str) -> str:
    text = f"{row.section_heading or ''} {sentence}".casefold()
    topic_rules = (
        ("Produk Domestik Regional Bruto", ("produk domestik regional bruto", "pdrb", "grdp")),
        ("Kemiskinan", ("kemiskinan", "miskin", "poverty")),
        ("Pendidikan", ("pendidikan", "sekolah", "peserta didik", "education")),
        ("Ketenagakerjaan", ("ketenagakerjaan", "angkatan kerja", "pengangguran", "pekerja")),
        ("Kesehatan", ("kesehatan", "penyakit", "kesehatan", "health")),
        ("Pertanian", ("pertanian", "padi", "tanaman", "petani", "agriculture")),
        ("Inflasi dan Harga", ("inflasi", "indeks harga konsumen", "harga konsumen", "inflation")),
        ("Kependudukan", ("penduduk", "kependudukan", "population")),
        ("Pariwisata", ("pariwisata", "wisatawan", "hotel", "tourism")),
        ("Industri", ("industri", "industri mikro", "industry")),
        ("Sensus", ("sensus", "enumerasi", "pencacahan")),
        ("Survei", ("survei", "survey")),
        ("Pemerintahan", ("pemerintah", "pegawai negeri", "government")),
        ("Perumahan", ("perumahan", "rumah tangga", "housing")),
        ("Pemuda", ("pemuda", "youth")),
        ("Demokrasi", ("demokrasi", "democracy")),
    )
    for label, keywords in topic_rules:
        if any(keyword in text for keyword in keywords):
            return label
    heading = normalize_text(row.section_heading or "")
    if heading and len(heading) <= 100 and content_words(heading):
        return heading
    words = [word for word in WORD_RE.findall(sentence) if len(word) >= 5]
    return " ".join(words[:5]) or "Statistik"


def anchor_for(question_type: str, sentence: str) -> str:
    sentence = normalize_text(sentence)
    first_words = sentence.split()[:8]

    def contextual(prefix: str, limit: int = 14) -> str:
        prefix_words = prefix.split()[-10:]
        combined: list[str] = []
        for word in prefix_words + first_words:
            if word not in combined:
                combined.append(word)
        return " ".join(combined[:limit]).strip(" ,:;-")

    def semantic_context() -> str:
        without_numbers = NUMBER_RE.sub(" ", sentence)
        tokens = [
            token for token in WORD_RE.findall(without_numbers)
            if len(token) >= 4 and token.casefold() not in STOPWORDS
        ]
        if len(tokens) > 16:
            tokens = tokens[:8] + tokens[-8:]
        return " ".join(tokens).strip(" ,:;-") or " ".join(sentence.split()[:8]).strip(" ,:;-")

    if question_type == "definition":
        match = DEFINITION_RE.search(sentence)
        prefix = sentence[: match.start()] if match else sentence
        result = contextual(prefix)
        return result if len(content_words(result)) >= 2 else semantic_context()
    if question_type == "number":
        match = NUMBER_RE.search(sentence)
        prefix = sentence[: match.start()] if match else sentence
        result = contextual(prefix, 16)
        return result if len(content_words(result)) >= 2 else semantic_context()
    if question_type == "period":
        match = PERIOD_RE.search(sentence)
        prefix = sentence[: match.start()] if match else sentence
        result = contextual(prefix)
        return result if len(content_words(result)) >= 2 else semantic_context()
    if question_type == "region":
        match = REGION_RE.search(sentence)
        prefix = sentence[: match.start()] if match else sentence
        result = contextual(prefix)
        return result if len(content_words(result)) >= 2 else semantic_context()
    if question_type == "methodology":
        match = METHOD_RE.search(sentence)
        prefix = sentence[: match.start()] if match else sentence
        result = contextual(prefix)
        return result if len(content_words(result)) >= 2 else semantic_context()
    words = [word for word in sentence.split() if len(word) >= 4]
    return " ".join(words[:14]).strip(" ,:;-" ) or "topik statistik"


def best_sentence(sentences: list[str], predicate: Any) -> str | None:
    matches = [sentence for sentence in sentences if predicate(sentence)]
    if not matches:
        return None
    return min(matches, key=lambda value: (abs(len(value) - 180), -len(content_words(value)), len(value)))


def build_candidate(row: ChunkRow, question_type: str) -> Candidate | None:
    sentences = split_sentences(row.chunk_text)
    if question_type == "definition":
        sentence = best_sentence(sentences, lambda value: bool(DEFINITION_RE.search(value)))
    elif question_type == "number":
        sentence = best_sentence(
            sentences,
            lambda value: bool(NUMBER_RE.search(value)) and len(content_words(value)) >= 2,
        )
    elif question_type == "period":
        sentence = best_sentence(sentences, lambda value: bool(PERIOD_RE.search(value)))
    elif question_type == "region":
        sentence = best_sentence(sentences, lambda value: bool(REGION_RE.search(value)))
    elif question_type == "methodology":
        sentence = best_sentence(sentences, lambda value: bool(METHOD_RE.search(value)))
    else:
        sentence = best_sentence(sentences, lambda value: len(content_words(value)) >= 3)
    if not sentence:
        return None
    topic = evidence_topic(row, sentence)
    if question_type == "document_search" and not content_words(topic).intersection(content_words(row.chunk_text)):
        return None
    if question_type == "document_search" and not numeric_tokens(row.title).issubset(numeric_tokens(row.chunk_text)):
        return None
    return Candidate(
        row=row,
        question_type=question_type,
        topic=topic,
        anchor=anchor_for(question_type, sentence),
        reference_answer=sentence,
    )


def question_for(candidate: Candidate) -> str:
    row = candidate.row
    title = row.title.replace('"', "'")
    page = f"halaman {row.page_start}" if row.page_start == row.page_end else f"halaman {row.page_start}-{row.page_end}"
    anchor = candidate.anchor.replace('"', "'")
    if candidate.question_type == "definition":
        return f'Dalam dokumen "{title}" ({row.publication_year}), bagaimana penjelasan untuk "{anchor}" pada {page}?'
    if candidate.question_type == "number":
        return f'Dalam dokumen "{title}" ({row.publication_year}), berapa nilai yang dilaporkan untuk "{anchor}" pada {page}?'
    if candidate.question_type == "period":
        return f'Dalam dokumen "{title}" ({row.publication_year}), periode atau tahun apa yang disebutkan untuk "{anchor}" pada {page}?'
    if candidate.question_type == "region":
        return f'Dalam dokumen "{title}" ({row.publication_year}), wilayah mana yang disebutkan dalam keterangan "{anchor}" pada {page}?'
    if candidate.question_type == "methodology":
        return f'Dalam dokumen "{title}" ({row.publication_year}), sumber atau metode apa yang dijelaskan untuk "{anchor}" pada {page}?'
    return f'Publikasi BPS mana yang memuat topik "{candidate.topic}" dalam kutipan tentang "{anchor}" pada {page}?'


def fetch_rows(database_url: str) -> list[ChunkRow]:
    query = """
        SELECT c.id, c.document_id, c.text, c.page_start, c.page_end, c.source_url,
               c.qdrant_point_id, c.section_heading, d.title, d.publication_year,
               d.region, d.topic
        FROM chunks AS c
        JOIN documents AS d ON d.id = c.document_id
        WHERE d.ingestion_status = 'indexed'
          AND c.text IS NOT NULL AND btrim(c.text) <> ''
          AND c.page_start IS NOT NULL AND c.page_end IS NOT NULL
          AND c.source_url IS NOT NULL AND btrim(c.source_url) <> ''
          AND c.qdrant_point_id IS NOT NULL AND btrim(c.qdrant_point_id) <> ''
        ORDER BY c.document_id, c.page_start, c.page_end, c.chunk_index, c.id
    """
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return [ChunkRow(*row) for row in cursor.fetchall()]


def select_stratified(candidates: list[Candidate], count: int, used_chunks: Counter[str], used_questions: set[str]) -> list[Candidate]:
    groups: dict[tuple[int, str, int, str], deque[Candidate]] = defaultdict(deque)
    for candidate in sorted(candidates, key=stable_key):
        row = candidate.row
        groups[(row.publication_year, str(row.document_id), row.page_start // 10, candidate.topic)].append(candidate)
    group_keys = sorted(groups, key=lambda value: hashlib.sha256("|".join(map(str, value)).encode("utf-8")).hexdigest())
    selected: list[Candidate] = []
    cursor = 0
    while len(selected) < count and group_keys:
        found = False
        for offset in range(len(group_keys)):
            position = (cursor + offset) % len(group_keys)
            key = group_keys[position]
            queue = groups[key]
            while queue:
                item = queue.popleft()
                if used_chunks[str(item.row.chunk_id)] >= MAX_RECORDS_PER_CHUNK:
                    continue
                if normalize_question(question_for(item)) in used_questions:
                    continue
                selected.append(item)
                used_chunks[str(item.row.chunk_id)] += 1
                used_questions.add(normalize_question(question_for(item)))
                found = True
                cursor = position + 1
                break
            if found:
                break
        if not found:
            raise RuntimeError(f"only selected {len(selected)} of {count} candidates for {candidates[0].question_type}")
    return selected


def record_from(candidate: Candidate, index: int) -> dict[str, Any]:
    row = candidate.row
    excerpt = row.chunk_text.strip()
    if candidate.question_type == "region":
        region_match = REGION_RE.search(excerpt)
        reference_answer = region_match.group(0) if region_match else row.region
    elif candidate.question_type == "document_search":
        reference_answer = row.title
    else:
        reference_answer = normalize_text(candidate.reference_answer)
    return {
        "question_id": f"q-{index:04d}",
        "question_text": question_for(candidate),
        "question_type": candidate.question_type,
        "topic": candidate.topic,
        "reference_answer": reference_answer,
        "evidence": {
            "document_id": str(row.document_id),
            "chunk_id": str(row.chunk_id),
            "qdrant_point_id": row.qdrant_point_id,
            "document_title": row.title,
            "publication_year": row.publication_year,
            "region": row.region,
            "page_start": row.page_start,
            "page_end": row.page_end,
            "source_url": row.source_url,
            "excerpt": excerpt,
        },
        "ground_truth": {
            "expected_document_id": str(row.document_id),
            "expected_chunk_id": str(row.chunk_id),
            "expected_qdrant_point_id": row.qdrant_point_id,
            "expected_page_start": row.page_start,
            "expected_page_end": row.page_end,
        },
        "verification_status": "pending",
        "reviewer_notes": "awaiting automated validation against authoritative PostgreSQL chunk",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    rows = fetch_rows(args.database_url)
    if len(rows) < TARGET_SIZE:
        raise SystemExit(f"authoritative corpus has only {len(rows)} eligible chunks; need {TARGET_SIZE}")

    candidates_by_type: dict[str, list[Candidate]] = defaultdict(list)
    for row in rows:
        for question_type in QUESTION_TYPES:
            candidate = build_candidate(row, question_type)
            if candidate is not None:
                candidates_by_type[question_type].append(candidate)

    used_chunks: Counter[str] = Counter()
    used_questions: set[str] = set()
    selected: list[Candidate] = []
    for question_type in QUESTION_TYPES:
        selected.extend(
            select_stratified(
                candidates_by_type[question_type],
                TYPE_TARGETS[question_type],
                used_chunks,
                used_questions,
            )
        )

    # Interleave types so the file itself is not grouped by one question kind.
    by_type: dict[str, list[Candidate]] = {question_type: [] for question_type in QUESTION_TYPES}
    for candidate in selected:
        by_type[candidate.question_type].append(candidate)
    records: list[dict[str, Any]] = []
    for index in range(TARGET_SIZE):
        question_type = QUESTION_TYPES[index % len(QUESTION_TYPES)]
        if by_type[question_type]:
            records.append(record_from(by_type[question_type].pop(0), index + 1))
    # The interleave above is intentionally simple; append any residual candidates
    # only if a type's target does not divide evenly into the six positions.
    if len(records) != TARGET_SIZE:
        residual = [candidate for values in by_type.values() for candidate in values]
        records.extend(record_from(candidate, len(records) + 1) for candidate in residual)
    if len(records) != TARGET_SIZE:
        raise SystemExit(f"internal sampling error: generated {len(records)} records")

    payload = {
        "schema_version": "2.0",
        "dataset_status": "pending_automated_validation",
        "capacity": TARGET_SIZE,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "eligible_chunks": len(rows),
        "records": len(records),
        "question_types": dict(Counter(record["question_type"] for record in records)),
        "documents": len({record["evidence"]["document_id"] for record in records}),
        "years": dict(Counter(record["evidence"]["publication_year"] for record in records)),
        "status": payload["dataset_status"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
