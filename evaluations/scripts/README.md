# Scripts Evaluasi

- `generate_factual_dataset.py` — bangun 1.000 record dari chunk PostgreSQL dengan sampling deterministik dan stratifikasi.
- `validate_factual_dataset.py` — validasi 100% record terhadap PostgreSQL dan mempromosikan status ke `ready` hanya saat 0 failure.
- `generate_responses.py` — jalur response generation lama, tidak dijalankan dalam rebuild dataset.
- `run_ragas.sh` — harness live lama, hanya dijalankan setelah dataset lulus validasi.

Generator tidak memanggil LLM, NVIDIA NIM, atau Cloudflare. Semua skrip diasumsikan dijalankan dari root repo dan memerlukan `DATABASE_URL` ke PostgreSQL corpus.
