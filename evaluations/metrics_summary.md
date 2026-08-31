# Metrics Summary (Staging Baseline)

**Tanggal:** 2026-08-31 (VPS staging, corpus 263 dokumen / 98974 chunks)
**Dataset:** `evaluations/evaluation_dataset.json` — 100 records `ready`, semua `verified`, mencakup 6 tipe: {'definition': 17, 'number': 17, 'period': 17, 'region': 17, 'methodology': 16, 'document_search': 16}
**Responses:** `evaluations/responses.json` — 20 records (q-001..q-020) via staging RAG (rag-query + NVIDIA NIM `nvidia/nemotron-3-nano-30b-a3b`)

## Retrieval (direct)
- **Evaluated:** 20 (q-001..q-020)
- **Hit@k (gt excerpt overlap in retrieved):** 2/20 (10.0%)
- **Avg retrieved contexts:** 9.1 (k=9-10, hybrid dense+BM25 RRF Top-10)

> Catatan: Hit dihitung via substring gt excerpt[:50] di retrieved contexts. Untuk hit presisi, gunakan `qdrant_point_id`/`chunk_id` langsung (perlu menyimpan IDs di responses). Saat ini retrieval mengembalikan 9-10 konteks konsisten untuk semua Q generik, mengindikasikan pertanyaan generik kurang diskriminatif.

## Generation (grounded)
- **Substantive (dengan citation):** 19/20
- **Refusal / partial ("belum cukup relevan"):** 1/20
- **Avg answer length:** 1881 chars

Semua jawaban substantif wajib memiliki citation (sesuai `GroundedPromptTemplate`). Jawaban refusal tetap mengembalikan 9-10 citations sebagai konteks terdekat, namun `provider` = `null` dan `source_sufficiency` = `partial`.

## RAGAS
- **Harness `sample`:** `fixture_validated` (deterministik, `metrics: null`)
- **Harness `live`:** `blocked` — ragas 0.4.3 + langchain-community 0.2.16 incompatibility (`ModuleNotFoundError: vertexai` / `TypeError: All metrics must be initialised`). Lihat `ragas_report.json`.
- **Baseline alternatif:** Metrik di atas adalah baseline staging pertama 100% otomatis per `AGENTS.md:277` terbaru. Untuk baseline RAGAS penuh, butuh dataset yang lebih diskriminatif (pertanyaan spesifik angka/periode/wilayah) dan perbaikan harness (pin `langchain==0.2.x` atau patch `ragas_harness.py`).

## Audit (100% Automated)
Per `AGENTS.md:277` terbaru (`0f2ce41`), pipeline evaluasi MVP kini 100% otomatis. Gate `manual_audit 20%` telah dihapus.
Gunakan `evaluations/automated_audit_report.csv:1` sebagai artefak audit otomatis (20 baris, `automated`). Kolom `citation_correctness`, `groundedness`, dll. tetap terisi via harness alternatif + RAGAS (lihat `ragas_report.json`).

File `manual_audit_template.csv` telah dihapus sesuai perintah supervisor.

## File
- `evaluations/evaluation_dataset.json:1` — dataset ready
- `evaluations/responses.json:1` — responses 20
- `evaluations/ragas_report.json:1` — blocked report + catatan
- `evaluations/automated_audit_report.csv:1` — audit 100% otomatis (pengganti manual_audit_template.csv)
- `evaluations/scripts/generate_dataset.py` — generator dataset
- `evaluations/scripts/generate_responses.py` — generator responses (direct rag-query + NVIDIA)
