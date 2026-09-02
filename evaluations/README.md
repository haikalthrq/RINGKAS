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
