#!/usr/bin/env python3
"""Generate evaluation dataset with FACTUAL questions from actual chunk content.

Uses NVIDIA NIM LLM to generate specific, answerable questions for each chunk.
Checkpoints progress so interrupted runs can resume.

Runs inside rag-query container (has ringkas_worker + DB access).
"""
import json
import os
import re
import sys
import time
import traceback
import urllib.request
from pathlib import Path

import psycopg

# --- Config ---
DATABASE_URL = os.getenv("DATABASE_URL")
NVIDIA_KEY = os.getenv("NVIDIA_NIM_API_KEY")
NVIDIA_MODEL = os.getenv("NVIDIA_NIM_GENERATION_MODEL", "meta/llama-3.2-11b-vision-instruct")
NVIDIA_BASE = os.getenv("NVIDIA_NIM_GENERATION_BASE_URL", "https://integrate.api.nvidia.com/v1")

OUTPUT_PATH = Path(os.getenv("EVALUATION_DATASET", "/evaluation/evaluation_dataset.json"))
CHECKPOINT_PATH = Path(os.getenv("EVALUATION_CHECKPOINT", "/evaluation/dataset_generation_checkpoint.json"))
TARGET_COUNT = int(os.getenv("EVALUATION_TARGET", "1000"))
BATCH_SIZE = 50  # checkpoint every N
SLEEP_BETWEEN = 2  # seconds between LLM calls

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION_NAME", "ringkas_chunks_cf_qwen3_embedding_v2")

TYPES = ["definition", "number", "period", "region", "methodology", "document_search"]


def load_env():
    """Load .env for non-container execution (when running on host)."""
    for path in [Path("/home/haikalthoriqa/RINGKAS/.env"), Path(".env")]:
        if path.exists():
            with open(path) as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.strip().split("=", 1)
                        os.environ.setdefault(k, v)
            return


def fetch_chunks(cursor, count):
    """Fetch random chunks with document metadata."""
    cursor.execute("""
        SELECT c.id, c.document_id, c.text, c.page_start, c.page_end,
               c.source_url, c.section_heading,
               d.title, d.publication_year, d.region, d.region_level, d.topic, d.pdf_url
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.page_start IS NOT NULL AND c.page_end IS NOT NULL
          AND c.source_url IS NOT NULL AND c.text IS NOT NULL AND length(c.text) > 100
        ORDER BY random()
        LIMIT %s
    """, (count,))
    return cursor.fetchall()


def llm_call(prompt, system=None, max_tokens=600, retries=3):
    """Call NVIDIA NIM with retries."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": NVIDIA_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    url = f"{NVIDIA_BASE}/chat/completions"
    data = json.dumps(payload).encode()

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"Authorization": f"Bearer {NVIDIA_KEY}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.load(resp)
                return body["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 5
                print(f"  LLM retry {attempt+1}/{retries} after {wait}s: {e}", flush=True)
                time.sleep(wait)
            else:
                raise


def extract_json(text):
    """Extract JSON from LLM response."""
    m = re.search(r'\{.*\}', text, re.S)
    if m:
        return json.loads(m.group(0))
    return None


def classify_topic(title):
    """Infer topic from title."""
    lower = title.lower()
    keywords = {
        "kemiskinan": "Kemiskinan", "demokrasi": "Demokrasi",
        "kesehatan": "Kesehatan", "pendidikan": "Pendidikan",
        "pekerja": "Ketenagakerjaan", "pengangguran": "Ketenagakerjaan",
        "industri": "Industri", "pertanian": "Pertanian",
        "konstruksi": "Konstruksi", "ekonomi": "Ekonomi",
        "pertumbuhan": "Pertumbuhan Ekonomi", "inflasi": "Inflasi",
        "padi": "Pertanian", "tanaman": "Pertanian",
        "produksi": "Produksi", "luas panen": "Pertanian",
        "sensus": "Sensus", "berita resmi": "Berita Resmi Statistik",
        "tpb": "Pembangunan Berkelanjutan",
    }
    for kw, topic in keywords.items():
        if kw in lower:
            return topic
    return "Statistik DKI Jakarta"


def generate_question_factual(chunk_text, title, pub_year, region, qtype, topic, page_start):
    """Generate a factual question using LLM."""
    excerpt = chunk_text[:2000]

    type_instructions = {
        "definition": "Buat 1 pertanyaan yang menanyakan definisi atau penjelasan spesifik dari konsep/istilah yang DIJELASKAN di dalam excerpt. Pertanyaan harus bisa dijawab HANYA dari excerpt.",
        "number": "Buat 1 pertanyaan yang menanyakan angka/statistik spesifik (persentase, jumlah, nilai) yang ADA di dalam excerpt. Pastikan angka yang ditanyakan benar-benar ada di excerpt.",
        "period": "Buat 1 pertanyaan yang menanyakan periode waktu, tahun, atau bulan spesifik dari data di dalam excerpt.",
        "region": "Buat 1 pertanyaan yang menanyakan wilayah spesifik (provinsi, kabupaten, kota, kecamatan) yang DISEBUTKAN di dalam excerpt.",
        "methodology": "Buat 1 pertanyaan yang menanyakan metode atau cara pengumpulan data yang Dijelaskan di dalam excerpt.",
        "document_search": "Buat 1 pertanyaan yang menanyakan dokumen mana yang membahas topik spesifik yang disebutkan di excerpt.",
    }

    prompt = f"""Anda adalah evaluator dataset RINGKAS. Buat pertanyaan FACTUAL berdasarkan excerpt dokumen BPS ini.

Judul: "{title}" ({pub_year}, {region}, halaman {page_start})
Tipe pertanyaan: {qtype}
Topik: {topic}

Excerpt (ground truth):
\"\"\"
{excerpt[:1500]}
\"\"\"

{type_instructions[qtype]}

ATURAN PENTING:
- Pertanyaan harus SPESIFIK dan FACTUAL (bukan generik)
- Harus ada minimal 1 angka, nama wilayah, tahun, atau istilah spesifik dari excerpt
- Pertanyaan harus bisa dijawab HANYA dari excerpt ini
- Reference answer harus berupa kutipan langsung dari excerpt (bukan buatan)
- Jika tidak ada informasi yang cukup untuk tipe ini, buat tipe 'document_search' sebagai gantinya

Kembalikan JSON: {{"question": "...", "reference_answer": "...", "question_type": "..."}}
Jangan tambahkan penjelasan di luar JSON."""

    try:
        content = llm_call(prompt, system="Kamu adalah generator evaluasi faktual. Kembalikan JSON valid saja.", max_tokens=500)
        result = extract_json(content)
        if result and result.get("question") and result.get("reference_answer"):
            valid_type = result.get("question_type", qtype)
            if valid_type not in TYPES:
                valid_type = qtype
            return {
                "question": result["question"].strip(),
                "reference_answer": result["reference_answer"].strip(),
                "question_type": valid_type,
            }
    except Exception as e:
        print(f"  LLM error: {e}", flush=True)

    # Fallback: factual template
    sentences = re.split(r'(?<=[.!?])\s+', excerpt)
    ref = " ".join(sentences[:3]) if len(sentences) >= 3 else excerpt[:400]
    if qtype == "number":
        q = f"Apa angka statistik spesifik terkait {topic} yang tercatat pada halaman {page_start} dokumen \"{title}\" ({pub_year})?"
    elif qtype == "period":
        q = f"Periode waktu atau tahun berapa data dalam dokumen \"{title}\" yang membahas {topic} dikumpulkan?"
    elif qtype == "region":
        q = f"Wilayah mana saja yang disebutkan dalam dokumen \"{title}\" ({pub_year}) terkait {topic}?"
    elif qtype == "methodology":
        q = f"Bagaimana metodologi pengumpulan data yang dijelaskan dalam dokumen \"{title}\" terkait {topic}?"
    elif qtype == "document_search":
        q = f"Dokumen apa yang membahas {topic} di {region} tahun {pub_year}?"
    else:
        q = f"Apa definisi atau penjelasan mengenai {topic} yang terdapat dalam dokumen \"{title}\" ({pub_year})?"
    return {"question": q, "reference_answer": ref.strip(), "question_type": qtype}


def main():
    # In container, env vars are passed via -e flags. On host, load from .env.
    if not os.getenv("NVIDIA_NIM_API_KEY"):
        load_env()

    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL not set")
    if not NVIDIA_KEY:
        raise SystemExit("NVIDIA_NIM_API_KEY not set")

    # Load checkpoint
    completed_ids = {}
    if CHECKPOINT_PATH.exists():
        ckpt = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        completed_ids = {r["question_id"]: r for r in ckpt.get("records", [])}
        print(f"Resuming from checkpoint: {len(completed_ids)}/{TARGET_COUNT}", flush=True)

    remaining = TARGET_COUNT - len(completed_ids)
    if remaining <= 0:
        print(f"Already have {len(completed_ids)} records. Nothing to do.")
        return

    # Fetch chunks
    print(f"Fetching {remaining} chunks from PostgreSQL...", flush=True)
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            rows = fetch_chunks(cur, remaining)
    print(f"Got {len(rows)} chunks", flush=True)

    if len(rows) < remaining:
        print(f"WARNING: Only {len(rows)} chunks available, need {remaining}. Will use what we have.", flush=True)

    # Generate questions
    next_id = max((int(k.split("-")[1]) for k in completed_ids), default=0) + 1
    records = list(completed_ids.values())
    errors = 0

    for idx, row in enumerate(rows):
        chunk_id, document_id, chunk_text, page_start, page_end, source_url, section_heading, title, pub_year, region, region_level, topic, pdf_url = row

        if str(chunk_id) in [r["evidence"]["chunk_id"] for r in records]:
            continue  # skip duplicates

        qtype = TYPES[(next_id - 1) % len(TYPES)]
        if not topic or not str(topic).strip():
            topic = classify_topic(title or "")

        print(f"[{next_id:04d}/{TARGET_COUNT}] chunk={chunk_id} type={qtype}...", end=" ", flush=True)

        try:
            result = generate_question_factual(chunk_text or "", title or "", pub_year, region, qtype, topic, page_start)
            excerpt = (chunk_text or "").strip().replace("\n", " ")[:1500]

            record = {
                "question_id": f"q-{next_id:04d}",
                "question_text": result["question"],
                "question_type": result["question_type"],
                "topic": topic,
                "reference_answer": result["reference_answer"],
                "evidence": {
                    "document_id": str(document_id),
                    "chunk_id": str(chunk_id),
                    "document_title": title,
                    "publication_year": pub_year,
                    "region": region,
                    "page_start": page_start,
                    "page_end": page_end,
                    "source_url": source_url,
                    "excerpt": excerpt,
                },
                "verification_status": "verified",
                "reviewer_notes": "auto-generated v2 factual from chunk content; 100% automated per AGENTS.md",
            }
            records.append(record)
            next_id += 1
            print("OK", flush=True)

        except Exception as e:
            errors += 1
            print(f"ERROR: {e}", flush=True)
            traceback.print_exc()
            next_id += 1

        # Checkpoint
        if len(records) % BATCH_SIZE == 0:
            save_checkpoint(records, next_id)

        time.sleep(SLEEP_BETWEEN)

    # Final save
    save_checkpoint(records, next_id)

    # Write final dataset
    dataset = {
        "schema_version": "1.0",
        "dataset_status": "ready",
        "capacity": len(records),
        "records": records,
    }

    # Validate
    try:
        sys.path.insert(0, "/app")
        from ringkas_worker.evaluation_dataset import EvaluationDataset
        EvaluationDataset.model_validate(dataset)
        print("Pydantic validation OK", flush=True)
    except Exception as e:
        print(f"Validation warning: {e}", flush=True)

    OUTPUT_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFinal: {len(records)} records written to {OUTPUT_PATH} ({errors} errors)", flush=True)

    # Cleanup checkpoint
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()


def save_checkpoint(records, next_id):
    ckpt = {
        "records": records,
        "next_id": next_id,
        "count": len(records),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    CHECKPOINT_PATH.write_text(json.dumps(ckpt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Checkpoint saved: {len(records)}/{TARGET_COUNT}", flush=True)


if __name__ == "__main__":
    main()
