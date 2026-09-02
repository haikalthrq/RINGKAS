# Metrics Summary (Staging Baseline)

**Tanggal:** 2026-08-31 (VPS staging, corpus 263 dokumen / 98974 chunks)
**Dataset:** `evaluations/evaluation_dataset.json` — 1000 records `ready`, semua `verified`, 6 tipe {'definition': 167, 'number': 167, 'period': 167, 'region': 167, 'methodology': 166, 'document_search': 166}, IDs `q-0001..q-1000`, **tanpa fiktif** (fictitious 0/1000)
**Responses:** `evaluations/responses.json` — 1000 records via staging RAG (rag-query + NVIDIA NIM `nvidia/nemotron-3-nano-30b-a3b`)

## Retrieval (direct)
- **Evaluated:** 1000
- **Hit@k (gt excerpt overlap):** 98/1000 (9.8%)
- **Avg retrieved contexts:** 9.1 (Top-10 hybrid)

## Generation (grounded)
- **Substantive:** 961/1000
- **Refusal/partial:** 39/1000
- **Avg answer length:** 2273 chars

## RAGAS
- **Harness `sample`:** `fixture_validated`
- **Harness `live`:** dependency RAGAS sudah kompatibel (`ragas==0.4.3`, `langchain-community==0.3.31`, `langchain-openai==1.3.5`, `openai==2.46.0`); live baseline belum dijalankan ulang setelah dataset retrieval diperbaiki. Baseline di atas adalah 100% otomatis per `AGENTS.md:277`.

## Audit (100% Automated)
Per `AGENTS.md:277` terbaru, pipeline 100% otomatis. `automated_audit_report.csv` berisi 1000 baris `automated`.

## File
- `evaluations/evaluation_dataset.json:1` — dataset 1000 ready
- `evaluations/responses.json:1` — responses 1000
- `evaluations/src/evaluation_dataset.py:1` — validator support 100 & 1000
