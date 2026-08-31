# Scripts Evaluasi

- `generate_dataset.py` — generate 100 verified dari PostgreSQL (random chunks, 6 tipe)
- `generate_responses.py` — generate 20 respons via direct rag-query + NVIDIA NIM (bypass API rate limit, grounded prompt)
- `improve_dataset_llm.py` — perbaiki 20 Q pertama via LLM (opsional, butuh NVIDIA key)
- `run_ragas.sh` — jalankan harness live (ragas 0.4.3 + langchain-community 0.2.16)

Semua skrip diasumsikan dijalankan dari root repo.
