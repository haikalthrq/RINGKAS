# Scripts Evaluasi

- `generate_dataset.py` — generate 1000 verified dari PostgreSQL (random chunks, 6 tipe, tanpa fiktif)
- `generate_responses.py` — generate respons via direct rag-query + NVIDIA NIM (run for all 1000 before a live baseline)
- `improve_dataset_llm.py` — perbaiki 20 Q pertama via LLM (opsional, butuh NVIDIA key)
- `run_ragas.sh` — jalankan baseline RAGAS pinned-provider yang resumable, 100 sampel stratified dari 1000 respons verified; kontrak Cloudflare atau DeepSeek resmi dipilih sebelum baseline dimulai

Semua skrip diasumsikan dijalankan dari root repo.
