# RINGKAS Evaluation Dataset

Artefak di folder ini membangun dan mengaudit dataset evaluasi RINGKAS dari
chunk PostgreSQL otoritatif. Dataset tidak memakai LLM, tidak mengubah corpus
atau Qdrant, dan tidak boleh diberi status `ready` sebelum validator lulus.

## Artefak Utama

```text
evaluations/
  evaluation_dataset.json
  dataset_validation_report.json
  scripts/
    generate_factual_dataset.py
    validate_factual_dataset.py
    audit_qdrant_ground_truth.py
    diagnose_retrieval_1000.py
    generate_factual_responses.py
    write_automated_audit.py
    run_live_ragas_1000.py
    run_t_eval_0003_background.sh
  src/evaluation_dataset.py
```

Setiap dari 1.000 record memiliki pertanyaan spesifik, tipe pertanyaan, topik,
jawaban referensi, excerpt chunk asli, metadata dokumen, `qdrant_point_id`, dan
ground truth document/chunk/page. Enam tipe pertanyaan diseimbangkan sebagai
167/167/167/167/166/166. Sampling dilakukan deterministik dan distratifikasi
melalui dokumen, tahun, halaman, serta topik; satu chunk hanya boleh dipakai
satu kali.

## Generate Dan Validate

Jalankan dari root repo dengan `DATABASE_URL` menuju PostgreSQL pada private
Compose network. Contoh menggunakan service `rag-query`:

```bash
docker compose --env-file .env -f infra/docker-compose.yml run --rm --no-deps \
  --volume "$PWD/evaluations:/evaluation:rw" \
  --entrypoint python rag-query /evaluation/scripts/generate_factual_dataset.py \
  --output /evaluation/evaluation_dataset.json

docker compose --env-file .env -f infra/docker-compose.yml run --rm --no-deps \
  --volume "$PWD/evaluations:/evaluation:rw" \
  --entrypoint python rag-query /evaluation/scripts/validate_factual_dataset.py \
  --dataset /evaluation/evaluation_dataset.json \
  --report /evaluation/dataset_validation_report.json
```

Generator menulis `pending_automated_validation`. Validator memuat kembali
setiap chunk dan dokumen dari PostgreSQL, memeriksa grounding, metadata,
numeric token, kompatibilitas tipe, generic/duplicate question, serta batas
pengulangan chunk. Hanya validator yang mengubah status menjadi `ready` setelah
semua pemeriksaan lulus. `dataset_validation_report.json` memuat status,
jumlah penolakan, dan hitungan per tipe, dokumen, tahun, halaman, dan topik.

## Pemeriksaan Tambahan

```bash
uv run --project services/rag-worker --extra test --frozen pytest \
  services/rag-worker/tests/test_evaluation_dataset.py \
  services/rag-worker/tests/test_ragas_harness.py \
  services/rag-worker/tests/test_manual_audit.py
git diff --check
```

RAGAS dan response generation tidak dijalankan sebagai bagian dari rebuild ini;
keduanya hanya boleh dijalankan setelah report validasi menunjukkan `passed`
dan `failures: 0`.

## T-EVAL-0003 Background Pipeline

Diagnostic retrieval menyimpan rank ID-based dan metrik dense, sparse, serta RRF
di `retrieval_diagnostic_1000.json`; checkpoint dan log juga berada di folder
ini. Response regeneration tidak memakai `responses.json` lama dan hanya
menyimpan konteks dari private `rag-query`. Generation memakai kontrak
Cloudflare Workers AI yang sama dengan production: akun primary, secondary,
lalu tertiary dengan model/endpoint yang sama. Akun yang gagal dilewati untuk
request berikutnya; jika seluruh akun Cloudflare gagal, evaluator mencoba model
NVIDIA yang aktif dan secondary-nya bila tersedia.

Pool memakai `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_SECONDARY_ACCOUNT_ID`/`CLOUDFLARE_SECONDARY_API_TOKEN`, dan
`CLOUDFLARE_TERTIARY_ACCOUNT_ID`/`CLOUDFLARE_TERTIARY_API_TOKEN`. Nama ini
berlaku sama untuk embedding dan generation; model tetap dipilih oleh
`CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL` atau
`CLOUDFLARE_WORKERS_AI_GENERATION_MODEL`.

Untuk menjalankan kelanjutan secara detached setelah response generation:

```bash
nohup evaluations/scripts/run_t_eval_0003_background.sh \
  > evaluations/t_eval_0003_background.log 2>&1 &
```

Runner menunggu `response_generation_report.json`, lalu menjalankan audit CSV
dan live RAGAS. RAGAS hanya berstatus `completed` jika seluruh 1.000 response
valid; error provider atau dependency ditulis sebagai `blocked` tanpa metrik
fiktif.

Status T-EVAL-0003 terakhir: retrieval diagnostic selesai untuk 1.000 record
dengan 0 transport/provider failure. Response report sebelumnya terhenti pada
135 response nyata karena quota Cloudflare primary habis. Pipeline sekarang
mendukung account failover production-compatible dan resume; response lama
tidak dijadikan fallback. Jalankan ulang generator setelah konfigurasi akun
secondary/tertiary dan/atau quota provider tersedia.
