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
- **Harness `live` (preflight):** `preflight_validated` — 20 sampel (60 metrik) via Cloudflare Workers AI (`@cf/openai/gpt-oss-120b`).
  - Faithfulness: `0.4083`
  - Context Precision: `0.0375`
  - Context Recall: `0.1250`
  - Blocker inkompatibilitas ragas 0.4.3 / event loop asyncio terselesaikan via arsitektur subprocess worker terisolasi (`ragas_metric_worker.py`), pin `langchain==0.3.20` & `langchain-openai==0.3.35`, timeout 300 detik untuk model reasoning 120B, serta failover multi-akun Cloudflare.
- **Harness `live` (full baseline):** Siap dijalankan / resumable untuk 100 sampel (300 metrik). Baseline di atas adalah 100% otomatis per `AGENTS.md:277`.

## Audit (100% Automated)
Per `AGENTS.md:277` terbaru, pipeline 100% otomatis. `automated_audit_report.csv` berisi 1000 baris `automated`.

## File
- `evaluations/evaluation_dataset.json:1` — dataset 1000 ready
- `evaluations/responses.json:1` — responses 1000
- `evaluations/src/evaluation_dataset.py:1` — validator support 100 & 1000
