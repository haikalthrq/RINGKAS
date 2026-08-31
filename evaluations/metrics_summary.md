# Metrics Summary (Staging Baseline)

**Tanggal:** 2026-08-31 (VPS staging, corpus 263 dokumen / 98974 chunks)
**Dataset:** `evaluations/evaluation_dataset.json` — 1000 records `ready`, semua `verified`, mencakup 6 tipe: {'definition': 167, 'number': 167, 'period': 167, 'region': 167, 'methodology': 166, 'document_search': 166}, IDs `q-0001..q-1000`, **tanpa pertanyaan fiktif** (fictitious check 0/1000)
**Responses:** `evaluations/responses.json` — 20 contoh (q-0001..q-0020) via staging RAG (rag-query + NVIDIA NIM `nvidia/nemotron-3-nano-30b-a3b`) — untuk 1000, jalankan `scripts/generate_responses.py` dengan slice 1000

## Retrieval (direct)
- **Evaluated:** 20 (contoh untuk 1000) — untuk evaluasi penuh 1000, hitung ulang
- **Hit@k (gt excerpt overlap):** 2/20 (10.0%) pada sample generik sebelumnya; dengan dataset 1000 yang lebih grounded, hit diharapkan meningkat
- **Avg retrieved contexts:** 9.1 (k=9-10, hybrid dense+BM25 RRF Top-10)

> Dataset 1000 telah divalidasi Pydantic (support 100 & 1000, pattern `q-[0-9]{3,4}`, `fictitious=0`). Setiap `reference_answer` adalah substring `excerpt` asli atau `title`, `evidence` lengkap dari chunk asli.

## Generation (grounded)
- **Substantive (dengan citation):** 19/20 (pada sample 20)
- **Refusal / partial:** 1/20
- **Avg answer length:** 1881 chars

## RAGAS
- **Harness `sample`:** `fixture_validated`
- **Harness `live`:** `blocked` — ragas 0.4.3 incompat (lihat `ragas_report.json`). Baseline alternatif di atas adalah baseline 100% otomatis per `AGENTS.md:277`.

## Audit (100% Automated)
Per `AGENTS.md:277` terbaru (`0f2ce41`), pipeline evaluasi MVP kini 100% otomatis. `automated_audit_report.csv` berisi 20 baris `automated`. `manual_audit_template.csv` telah dihapus.

## File
- `evaluations/evaluation_dataset.json:1` — dataset 1000 ready (expandable)
- `evaluations/responses.json:1` — responses 20 contoh
- `evaluations/ragas_report.json:1` — blocked + alternatif
- `evaluations/automated_audit_report.csv:1` — audit 100% otomatis
- `evaluations/src/evaluation_dataset.py:1` — validator support 100 & 1000
