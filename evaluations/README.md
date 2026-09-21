# Evaluations

Folder ini berisi artefak evaluasi RINGKAS (staging): dataset, respons, laporan, dan skrip.

## Struktur
```
evaluations/
  README.md
  evaluation_dataset.json      # 1000 records ready, verified, 6 tipe (167/167/167/167/166/166) — 100% grounded dari dokumen asli
  responses.json               # 1000 respons RAG yang linked ke dataset terverifikasi
  ragas_report.json            # laporan baseline RAGAS pinned-provider, atau blocked report tersanitasi
  automated_audit_report.csv   # audit otomatis atas 1000 respons
  metrics_summary.md           # ringkasan baseline otomatis
  scripts/
    generate_dataset.py        # generate 1000 verified dari corpus PostgreSQL (tanpa fiktif)
    generate_responses.py      # generate responses via direct rag-query + NVIDIA NIM
    improve_dataset_llm.py     # perbaikan Q dengan LLM (opsional)
    run_ragas.sh               # wrapper harness live
  src/
    ragas_harness.py           # compatibility entry point ke harness services/rag-worker
    evaluation_dataset.py      # validator Pydantic (support 100 & 1000, IDs q-0001..q-1000)
```

## Cara Jalankan (staging)
```bash
# 1. Generate dataset 1000 (jika perlu)
sudo docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.production.yml run --rm --no-deps --volume "$PWD/evaluations:/evaluation:rw" --entrypoint python rag-query /evaluation/scripts/generate_dataset.py

# 2. Generate seluruh 1000 responses (membutuhkan staging RAG aktif)
bash evaluations/scripts/generate_responses.py

# 3. RAGAS live: memilih 100 response verified secara stratified dan deterministik
bash evaluations/scripts/run_ragas.sh
```

## RAGAS Live Baseline

Live RAGAS requires a ready 1000-record dataset and 1000 linked verified responses. It evaluates exactly 100 samples, balanced across question types as far as their available counts allow. The selection uses stable question-ID hashes and the report includes the selected IDs and their hash.

The evaluator is one model and one provider for the entire baseline. The default Cloudflare contract uses `RAGAS_LLM_MODEL=@cf/openai/gpt-oss-120b` and may fail over only across primary, secondary, and tertiary Cloudflare accounts with the same model. The approved alternative is the official DeepSeek API contract: `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE_URL=https://api.deepseek.com`, and `DEEPSEEK_RAGAS_MODEL=deepseek-flash`. DeepSeek is only an LLM judge for a separately started baseline; it must not replace embedding or product-generation providers and cannot be mixed into a Cloudflare baseline.

All `RAGAS_LLM_*` numeric values must be positive. Defaults in the environment examples are: timeout 120 seconds, retries 2, one worker, preflight 20, output cap 32,000, and temperature 0.1. Preflight scores its configured samples progressively and stops the baseline if any required metric is missing or non-finite.

The harness atomically checkpoints every finite metric beside `responses.json`. A resume is allowed only when the model, provider, output cap, timeout, retry count, worker count, RAGAS version, temperature, and selected sample IDs exactly match. `completed` is emitted only when all 100 samples have finite `faithfulness`, `context_precision`, and `context_recall` values. The 1000-response automated audit remains separate from this 100-sample RAGAS baseline.

Lihat `metrics_summary.md` untuk hasil otomatis pertama.
