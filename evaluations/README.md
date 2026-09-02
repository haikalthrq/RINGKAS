# Evaluations

Folder ini berisi **semua** artefak evaluasi RINGKAS (staging) — dataset, respons, laporan, serta kode/skrip. **100% otomatis** per `AGENTS.md:277` terbaru (`0f2ce41`, expandable).

## Struktur
```
evaluations/
  README.md
  evaluation_dataset.json      # 1000 records ready, verified, 6 tipe (167/167/167/167/166/166) — 100% grounded dari dokumen asli
  responses.json               # 20 respons RAG aktual (q-0001..q-0020) via direct rag-query + NVIDIA NIM (contoh untuk 1000)
  ragas_report.json            # hasil harness live saat dijalankan + baseline alternatif
  automated_audit_report.csv   # 20 baris audit otomatis (pengganti manual_audit_template.csv)
  metrics_summary.md           # ringkasan baseline otomatis
  scripts/
    generate_dataset.py        # generate 1000 verified dari corpus PostgreSQL (tanpa fiktif)
    generate_responses.py      # generate responses via direct rag-query + NVIDIA NIM
    improve_dataset_llm.py     # perbaikan Q dengan LLM (opsional)
    run_ragas.sh               # wrapper harness live
  src/
    ragas_harness.py           # copy dari services/rag-worker
    evaluation_dataset.py      # validator Pydantic (support 100 & 1000, IDs q-0001..q-1000)
```

## Cara Jalankan (staging)
```bash
# 1. Generate dataset 1000 (jika perlu)
sudo docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.production.yml run --rm --no-deps --volume "$PWD/evaluations:/evaluation:rw" --entrypoint python rag-query /evaluation/scripts/generate_dataset.py

# 2. Generate responses (contoh 20, butuh WEB_PORT=3001 aktif; untuk 1000 ubah slice)
bash evaluations/scripts/generate_responses.py

# 3. RAGAS live (butuh RAGAS_LLM_* env)
bash evaluations/scripts/run_ragas.sh
```

## Status Saat Ini
- Dataset: **1000** ready, semua `verified`, semua tipe ter-cover (167/167/167/167/166/166), IDs `q-0001..q-1000`, **tanpa pertanyaan fiktif** (setiap `reference_answer` adalah substring `excerpt` asli atau `title`, `evidence` lengkap dari chunk asli)
- Responses: 20 contoh (q-0001..q-0020) via staging RAG, avg 9 konteks, avg 1881 chars — untuk 1000, jalankan skrip dengan slice 1000
- RAGAS: harness `sample` lulus; dependency live sudah dipin dan tervalidasi. Live baseline menunggu dataset retrieval yang diperbaiki dan evaluator provider yang tersedia.
- Audit: 100% otomatis via `automated_audit_report.csv` (20 baris); `manual_audit_template.csv` telah dihapus per `AGENTS.md:277`.

Lihat `metrics_summary.md` untuk hasil otomatis pertama.
