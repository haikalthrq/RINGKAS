# Evaluations

Folder ini berisi **semua** artefak evaluasi RINGKAS (staging) sesuai permintaan — dataset, respons, laporan, template audit, serta kode/skrip.

## Struktur
```
evaluations/
  README.md
  evaluation_dataset.json      # 100 records ready, verified, 6 tipe (definition, number, period, region, methodology, document_search)
  responses.json               # 20 respons RAG aktual (q-001..q-020) via /api/chat + rag-query
  ragas_report.json            # hasil harness live (saat ini blocked, lihat metrics_summary.md untuk baseline alternatif)
  manual_audit_template.csv    # 20 baris untuk audit manual (q-001..q-020)
  metrics_summary.md           # ringkasan baseline otomatis (retrieval + generation)
  scripts/
    generate_dataset.py        # generate 100 verified dari corpus PostgreSQL
    generate_responses.py      # generate responses via direct rag-query + NVIDIA NIM
    improve_dataset_llm.py     # perbaikan 20 Q dengan LLM (opsional)
    run_ragas.sh               # wrapper harness live
  src/
    ragas_harness.py           # copy dari services/rag-worker
    evaluation_dataset.py      # validator Pydantic
```

## Cara Jalankan (staging)
```bash
# 1. Generate dataset (jika perlu)
sudo docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.production.yml run --rm --no-deps --volume "$PWD/evaluations:/evaluation:rw" --entrypoint python rag-query /evaluations/scripts/generate_dataset.py

# 2. Generate responses (20, butuh WEB_PORT=3001 aktif)
bash evaluations/scripts/generate_responses.py  # atau via direct_eval.py

# 3. RAGAS live (butuh RAGAS_LLM_* env)
bash evaluations/scripts/run_ragas.sh
```

## Status Saat Ini
- Dataset: ready, 100 verified, semua tipe ter-cover (Counter 17/17/17/17/16/16)
- Responses: 20 (q-001..q-020) via staging RAG, avg 9 contexts, avg 1881 chars
- RAGAS: harness `sample` lulus, `live` blocked karena ragas 0.4.3 + langchain-community incompatibility (lihat ragas_report.json). Baseline alternatif di `metrics_summary.md` disediakan.
- Manual audit: template 20 baris pending, siap untuk Anda isi.

Lihat `metrics_summary.md` untuk hasil otomatis pertama.
