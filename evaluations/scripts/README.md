# Scripts Evaluasi

- `generate_factual_dataset.py` — bangun 1.000 record dari chunk PostgreSQL dengan sampling deterministik dan stratifikasi.
- `validate_factual_dataset.py` — validasi 100% record terhadap PostgreSQL dan mempromosikan status ke `ready` hanya saat 0 failure.
- `audit_qdrant_ground_truth.py` — audit point, chunk, document, dan page metadata pada Qdrant.
- `diagnose_retrieval_1000.py` — diagnostic dense/sparse/RRF berbasis rank ID dengan checkpoint resumable.
- `generate_factual_responses.py` — regenerate response dari private retrieval dengan canonical Cloudflare primary/secondary/tertiary account pool lalu NVIDIA fallback.
- `write_automated_audit.py` — tulis audit kontrak otomatis untuk seluruh 1.000 response.
- `run_live_ragas_1000.py` — wrapper RAGAS live dengan report blocked yang tersanitasi.
- `finalize_blocked_responses.py` — simpan response parsial nyata saat provider tidak tersedia.
- `run_t_eval_0003_background.sh` — continuation runner detached untuk response, audit, dan RAGAS.
- `generate_responses.py` — jalur response generation lama, tidak dijalankan dalam rebuild dataset.
- `run_ragas.sh` — harness live lama, hanya dijalankan setelah dataset lulus validasi.

Generator tidak memanggil LLM, NVIDIA NIM, atau Cloudflare. Semua skrip diasumsikan dijalankan dari root repo dan memerlukan `DATABASE_URL` ke PostgreSQL corpus.
