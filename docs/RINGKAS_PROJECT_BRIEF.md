# Project Brief — RINGKAS RAG BPS

**Project Name:** RINGKAS  
**Full Name:** Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik  
**Document Type:** Project Brief  
**Status:** Final Initial Brief / Baseline Requirement  
**Version:** 1.0  
**Date:** 2026-07-08  
**Language:** Bahasa Indonesia  

---

## 1. Project Name

**RINGKAS** adalah singkatan dari:

> **Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik**

RINGKAS adalah web Retrieval-Augmented Generation (RAG) untuk pencarian, tanya jawab, dan ringkasan berbasis dokumen publikasi Badan Pusat Statistik (BPS), dengan jawaban yang wajib menyertakan sumber/citation.

---

## 2. Background

Publikasi BPS berisi informasi statistik yang penting untuk kajian sosial-ekonomi, penelitian, kebijakan, dan analisis berbasis data resmi. Namun, informasi tersebut umumnya tersebar di banyak dokumen PDF, berbeda periode, wilayah, topik, dan struktur penyajian.

Pengguna sering harus membaca publikasi panjang secara manual untuk menemukan definisi indikator, angka statistik, metodologi, atau konteks tertentu. Di sisi lain, penggunaan LLM umum tanpa grounding ke dokumen BPS memiliki risiko menghasilkan jawaban yang tidak sesuai sumber, salah periode, salah wilayah, salah satuan, atau salah definisi.

RINGKAS dibangun untuk membantu pengguna mencari dan memahami isi publikasi BPS secara lebih cepat, tetapi tetap menjaga prinsip evidence-based melalui citation dan pembatasan jawaban hanya berdasarkan sumber yang tersedia di corpus.

---

## 3. Problem Statement

Masalah utama yang ingin diselesaikan:

1. Pengguna harus membaca PDF publikasi BPS yang panjang secara manual.
2. Informasi statistik tersebar di banyak dokumen, periode, wilayah, dan topik.
3. Pengguna membutuhkan jawaban cepat dengan sumber yang jelas.
4. Pengguna dapat kesulitan memahami istilah, indikator, definisi, atau metodologi BPS.
5. Jawaban dari LLM umum berisiko tidak grounded ke sumber BPS.

Dampak dari masalah tersebut:

1. Waktu pencarian informasi menjadi lama.
2. Kajian cepat berbasis publikasi BPS menjadi sulit.
3. Pengguna tidak selalu tahu dokumen mana yang perlu dibaca.
4. Ada risiko salah mengambil angka, periode, wilayah, satuan, atau definisi indikator.
5. Ada risiko jawaban AI tampak meyakinkan, tetapi tidak sesuai dokumen resmi.

---

## 4. Project Objectives

Tujuan utama RINGKAS:

1. Menyediakan sistem tanya jawab berbasis dokumen publikasi BPS.
2. Menyediakan jawaban yang menyertakan citation ke dokumen sumber.
3. Memudahkan pencarian dokumen berdasarkan metadata dan kata kunci.
4. Memungkinkan pengguna memperoleh ringkasan berbasis pertanyaan tertentu.
5. Mengurangi risiko hallucination dengan grounding ke chunk dokumen yang terindeks.
6. Menjadi baseline sistem RAG yang dapat dievaluasi secara retrieval dan generation.

---

## 5. Target Users

### 5.1 Primary Evaluation Users

Target evaluasi awal:

- Tim internal kecil, sekitar **10–30 user**.

Target ini digunakan untuk validasi awal kualitas sistem, performa, usability, dan evaluasi RAG.

### 5.2 Secondary Users

Target pengguna sekunder:

- Mahasiswa.
- Peneliti.
- Pengguna publikasi BPS.
- Pengguna yang membutuhkan pencarian cepat terhadap dokumen statistik.

### 5.3 Access Scope

RINGKAS MVP mengizinkan **public self-registration**, sehingga sistem tidak disebut internal-only secara akses.

Namun, evaluasi awal tetap difokuskan pada 10–30 user internal.

Implikasi akses publik:

- Perlu email verification.
- Perlu quota prompt.
- Perlu rate limit per user.
- Perlu rate limit per IP untuk guest.
- Perlu logging penggunaan dasar.
- Perlu pembatasan token/response.
- Perlu kontrol abuse/spam dasar.

---

## 6. Core Use Cases

Core use cases MVP:

1. User bertanya tentang isi publikasi BPS dan mendapat jawaban berbasis dokumen.
2. User melihat citation ke dokumen sumber.
3. User mencari dokumen berdasarkan metadata atau kata kunci.
4. User login dan melihat riwayat chat.
5. Guest/public user mencoba satu prompt dengan citation minimal.
6. Admin/System Maintainer menjalankan ingestion corpus dari API BPS melalui UI sederhana.
7. User meminta ringkasan berdasarkan pertanyaan tertentu.

---

## 7. MVP Scope

### 7.1 Product Scope

Fitur utama MVP:

1. Public self-registration.
2. Login email-password.
3. Google OAuth.
4. Guest trial mode terbatas.
5. Chat/Q&A berbasis dokumen publikasi BPS.
6. Citation ke dokumen sumber.
7. Search dokumen berdasarkan metadata/kata kunci.
8. Riwayat chat untuk user login.
9. Admin UI sederhana untuk ingestion.
10. Ingestion corpus dari API BPS oleh Admin/System Maintainer.
11. Ringkasan berdasarkan pertanyaan user sebagai MVP Plus.

### 7.2 Guest/Public User Scope

Guest/Public User dapat:

- mencoba maksimal 1 prompt;
- tetap melihat citation minimal;
- tidak memiliki riwayat chat;
- tidak dapat search dokumen penuh;
- tidak dapat upload dokumen;
- tidak dapat mengakses fitur lanjutan.

Guest tidak boleh menerima jawaban substantif tanpa citation karena citation adalah prinsip inti RINGKAS.

### 7.3 Admin/System Maintainer Scope

Admin/System Maintainer dapat:

- menjalankan ingestion melalui endpoint internal;
- menggunakan admin UI sederhana untuk trigger ingestion;
- melihat status job ingestion;
- melihat log ringkas ingestion.

Admin UI MVP tidak mencakup:

- upload dokumen oleh user;
- dashboard analytics kompleks;
- manajemen dokumen lengkap;
- edit/delete massal;
- reprocess detail;
- role-based access control kompleks.

---

## 8. Corpus Scope

### 8.1 Wilayah

Corpus MVP:

- Wilayah: **DKI Jakarta**
- Level wilayah: **Provinsi**

### 8.2 Rentang Tahun

Corpus MVP menggunakan:

- publikasi BPS DKI Jakarta **5 tahun terakhir**.

Pipeline dirancang agar Developer/System Maintainer dapat memperluas rentang tahun melalui konfigurasi ingestion di masa depan.

### 8.3 Jumlah Publikasi

Jumlah publikasi awal:

- semua publikasi DKI Jakarta dalam 5 tahun terakhir jika jumlahnya **<= 300 dokumen**;
- jika jumlahnya lebih dari 300 dokumen, publikasi diprioritaskan berdasarkan relevansi dan kebutuhan MVP.

### 8.4 Topik

MVP mencakup:

- semua topik dalam corpus DKI Jakarta yang berhasil di-ingest.

Konsekuensi:

- evaluasi harus mencakup topik utama yang muncul dalam corpus.

### 8.5 Jenis Dokumen

Dokumen yang diprioritaskan:

- publikasi PDF digital BPS;
- dokumen dengan text layer;
- dokumen yang dapat diproses dengan PyMuPDF.

Dokumen yang tidak didukung pada MVP:

- PDF scan tanpa text layer;
- dokumen yang membutuhkan OCR;
- dokumen rusak/encrypted/tidak dapat diparsing.

---

## 9. Out of Scope

Tidak masuk MVP:

1. Upload dokumen oleh user.
2. OCR dokumen scan.
3. Pipeline OCR.
4. Pemahaman visual penuh atas grafik/gambar.
5. Ekstraksi tabel kompleks yang dijamin akurat.
6. Integrasi data tabel BPS secara real-time.
7. Query langsung ke database statistik BPS secara real-time.
8. Validasi angka terhadap sumber eksternal di luar dokumen yang dipakai.
9. Pemrosesan semua publikasi BPS nasional sejak awal.
10. Analisis statistik otomatis.
11. Visualisasi grafik otomatis dari isi dokumen.
12. Perbandingan lintas dokumen secara kompleks.
13. Forecasting/prediksi indikator.
14. Rekomendasi kebijakan otomatis.
15. Fine-tuning LLM.
16. Training embedding model sendiri.
17. Multi-agent workflow di aplikasi end-user.
18. Mobile app native.
19. Payment/subscription.
20. Public API pihak ketiga.
21. Manajemen organisasi/tim kompleks.
22. Role-based access control kompleks.
23. Multi-user collaboration.
24. Dashboard analytics penggunaan kompleks.
25. Audit log kompleks.
26. Voice input/output.
27. Integrasi WhatsApp/Telegram.
28. Multi-language support termasuk bahasa daerah.
29. GitHub OAuth.
30. Telegram OAuth.
31. Hugging Face OAuth.

Future plan:

- OCR fallback setelah pipeline text-first stabil.
- Docling sebagai kandidat parser eksperimen.
- Object storage jika scale meningkat.
- OAuth provider tambahan.
- Export PDF/Word, jika diputuskan nanti.
- Reranking jika provider/model gratis atau hemat tersedia.

---

## 10. Key Features

### 10.1 Authentication

MVP authentication:

- email-password login;
- public self-registration;
- Google OAuth.

Future authentication:

- GitHub OAuth;
- Telegram OAuth;
- Hugging Face OAuth.

### 10.2 Chat/Q&A

User dapat bertanya tentang corpus publikasi BPS. Sistem mengambil chunk relevan dan menghasilkan jawaban berbasis sumber.

### 10.3 Citation

Citation minimal untuk user umum:

- judul dokumen;
- tahun publikasi;
- wilayah;
- halaman jika berhasil diekstrak;
- URL dokumen atau halaman BPS;
- potongan teks sumber melalui hover/click citation.

Skor relevansi tidak ditampilkan ke user umum. Skor retrieval/generation hanya untuk developer/evaluasi internal.

### 10.4 Search Dokumen

User dapat mencari dokumen berdasarkan:

- judul;
- tahun;
- wilayah;
- topik/subjek jika tersedia;
- kata kunci.

### 10.5 Riwayat Chat

User login dapat melihat riwayat chat.

Guest tidak memiliki riwayat chat.

### 10.6 Admin UI Sederhana

Admin UI MVP hanya mencakup:

- trigger ingestion;
- status job;
- log ringkas.

---

## 11. High-Level System Flow

### 11.1 Ingestion Flow

Alur ingestion MVP:

1. Admin/System Maintainer menjalankan ingestion melalui admin UI sederhana atau endpoint internal.
2. Backend mengambil metadata dari API BPS.
3. Backend memfilter dokumen DKI Jakarta dalam 5 tahun terakhir.
4. Backend mengunduh PDF.
5. PDF disimpan di local storage VPS.
6. Backend melakukan parsing PDF menggunakan PyMuPDF.
7. Teks dibersihkan secara hati-hati.
8. Dokumen dipecah menjadi chunk.
9. Chunk diberi metadata.
10. Embedding dibuat menggunakan provider embedding.
11. Chunk dan embedding disimpan di Qdrant.
12. Metadata dokumen, status ingestion, dan log disimpan di PostgreSQL.
13. Jika dokumen gagal diproses, sistem retry beberapa kali.
14. Jika tetap gagal, dokumen diberi status `failed`, error dicatat, dan ingestion dokumen lain dilanjutkan.

### 11.2 Query Flow

Alur query MVP:

1. User mengirim pertanyaan.
2. Sistem melakukan retrieval hybrid menggunakan Qdrant dense + sparse vector.
3. Hasil dense dan sparse digabung menggunakan Reciprocal Rank Fusion (RRF).
4. Sistem mengambil top chunk final.
5. Sistem memeriksa retrieval sufficiency rule.
6. Jika sumber cukup, sistem membuat jawaban berbasis chunk.
7. Jika sumber kurang, sistem memberi jawaban parsial dengan keterbatasan atau menolak menjawab substantif.
8. Jawaban dikembalikan dengan citation.
9. Riwayat chat disimpan untuk user login.

---

## 12. Technical Architecture

### 12.1 Runtime dan Deployment

MVP menggunakan:

- Next.js + TypeScript dengan App Router sebagai frontend/web presentation layer dan API consumer terhadap ASP.NET Core;
- ASP.NET Core Web API sebagai main backend/API dan source of truth untuk domain logic dan authorization;
- Python RAG Worker sebagai internal processing service yang tidak public-facing;
- local persistent storage untuk PDF;
- PostgreSQL untuk metadata, auth, job, dan log;
- Qdrant untuk vector database.

Next.js tidak menggantikan ASP.NET Core sebagai backend utama dan tidak mengakses PostgreSQL atau Qdrant secara langsung. Authentication, authorization, Chat/Q&A API, document search API, admin ingestion API, rate limiting, application logging, dan core business logic tetap berada di ASP.NET Core.

MVP dapat menjalankan container Next.js frontend, ASP.NET Core API, Python RAG Worker, PostgreSQL, dan Qdrant melalui Docker Compose pada satu VPS.

PDF disimpan lokal pada MVP dan dapat dimigrasikan ke object storage jika skala meningkat.

### 12.2 Database

PostgreSQL digunakan untuk:

- metadata dokumen;
- status ingestion;
- auth/user;
- role;
- chat history;
- document search/filter;
- log ringkas ingestion.

### 12.3 Vector Database

Qdrant digunakan untuk:

- dense vector retrieval;
- sparse vector retrieval;
- hybrid retrieval dalam satu collection;
- metadata filtering jika dibutuhkan.

Fusion menggunakan Reciprocal Rank Fusion/RRF.

Catatan:

- Istilah BM25 tidak dipakai sebagai klaim implementasi kecuali sistem benar-benar memakai BM25 engine.

### 12.4 Parser

Parser utama MVP:

- PyMuPDF.

Parser future/experimental:

- Docling.

MVP tidak menggunakan OCR.

PDF scan tanpa text layer diberi status:

- `unsupported_or_extraction_failed`.

### 12.5 Cleaning

Cleaning MVP:

- hapus header/footer berulang;
- normalisasi spasi dan newline;
- gabungkan hyphenated words;
- hapus nomor halaman yang mengganggu;
- pertahankan struktur heading jika terdeteksi;
- pertahankan informasi halaman;
- hindari cleaning agresif agar tidak mengubah makna.

### 12.6 Table Handling

Tabel sederhana:

- diekstrak sebagai teks;
- diekstrak sebagai markdown table jika memungkinkan.

Tabel kompleks:

- diproses best-effort;
- tidak menjadi prioritas retrieval;
- jika struktur rusak, teks mentah disimpan dengan metadata `low_structure_confidence`.

### 12.7 Chunking

Strategi chunking awal:

- recursive character/text splitter.

Parameter awal:

- chunk size: 500–800 tokens;
- overlap: 20%.

Metadata per chunk:

- `document_id`;
- `chunk_id`;
- `judul_dokumen`;
- `tahun_publikasi`;
- `wilayah`;
- `level_wilayah`;
- `halaman_awal`;
- `halaman_akhir`;
- `section_heading` jika tersedia;
- `chunk_index`;
- `extraction_method = text_layer`;
- `low_structure_confidence` jika struktur tidak jelas;
- `url_sumber`.

### 12.8 Retrieval

Retrieval MVP:

- Qdrant dense vector + sparse vector retrieval;
- dense candidate: top-20;
- sparse candidate: top-20;
- fusion: RRF;
- top-k final sebelum generation: top-10.

Catatan:

- Top-10 valid sebagai baseline, tetapi perlu dievaluasi karena dapat meningkatkan token cost dan noise.
- Threshold numerik tetap belum digunakan pada MVP awal.
- Sistem tetap menggunakan retrieval sufficiency rule.

### 12.9 Metadata Filtering

Default:

- retrieval tidak memakai filter eksplisit.

Conditional filtering:

- jika user menyebut tahun, sistem boleh memakai filter tahun;
- jika user menyebut topik/subjek, sistem boleh memakai filter topik jika metadata tersedia;
- jika user menyebut judul dokumen, sistem boleh memprioritaskan dokumen tersebut;
- wilayah default selalu DKI Jakarta untuk MVP;
- filter tidak boleh terlalu ketat sampai membuang sumber relevan;
- filter behavior dievaluasi setelah baseline retrieval.

### 12.10 Reranking

Reranking:

- optional feature flag;
- hanya diaktifkan jika provider/model gratis atau hemat tersedia;
- MVP tetap harus berjalan tanpa reranker.

### 12.11 Model Provider

Generation:

- primary: NVIDIA NIM;
- fallback: Cloudflare Workers AI;
- OpenCode Zen / DeepSeek V4 Flash Free: experimental only.

Embedding target yang disetujui:

- Cloudflare Workers AI saja;
- model: `@cf/qwen/qwen3-embedding-0.6b`;
- tidak ada fallback embedding otomatis.

Task T-0415 sampai T-0417 telah mengimplementasikan dan memverifikasi client
Cloudflare, verifikasi dimensi, collection berversi, serta jalur hybrid
dense+sparse indexing/query yang diwajibkan.
Provider/model embedding yang berbeda tidak boleh dicampur dengan vector lama.
Perubahan provider/model wajib menggunakan collection Qdrant berversi baru dan
full corpus reindex.

Jika embedding provider gagal:

- sistem menampilkan error;
- sistem tidak otomatis memakai embedding model berbeda.

Catatan:

- Model generation MVP dikunci berurutan: NVIDIA `nvidia/nemotron-3-nano-30b-a3b` primary, Cloudflare `@cf/meta/llama-3.3-70b-instruct-fp8-fast` cross-provider fallback, NVIDIA `mistralai/mistral-small-4-119b-2603` dan `nvidia/nemotron-mini-4b-instruct` sebagai reserve fallback, serta Cloudflare `@cf/meta/llama-4-scout-17b-16e-instruct` sebagai eksperimental.
- Dimensi output `1024` untuk model embedding Cloudflare yang disetujui telah diverifikasi live.
- Rate limit, terms, dan availability provider tetap harus diverifikasi untuk deployment.

---

## 13. Generation and Answer Policy

### 13.1 Bahasa Jawaban

Sistem mengikuti bahasa pertanyaan user.

### 13.2 Format Jawaban

Format jawaban bersifat adaptif.

Default:

- jawaban langsung singkat dengan citation.

Format tambahan:

- bullet points jika jawaban berisi beberapa poin;
- tabel jika struktur informasi cocok dan sumber mendukung;
- ringkasan + detail jika user meminta penjelasan lebih panjang.

Sistem tidak memaksa semua format muncul dalam setiap jawaban.

### 13.3 Citation Placement

Citation ditampilkan:

- di akhir setiap paragraf/klaim;
- inline;
- juga dapat ditampilkan dalam panel sumber.

### 13.4 Hallucination Control

Instruksi generasi wajib:

1. Jawaban hanya berdasarkan chunk yang diberikan.
2. Tidak boleh membuat angka, periode, wilayah, satuan, atau definisi di luar sumber.
3. Jika sumber kurang, nyatakan keterbatasan.
4. Jika tidak ada sumber cukup, tolak menjawab substantif.
5. Selalu sertakan citation untuk klaim substantif.
6. Jangan menyimpulkan tren atau kausalitas tanpa sumber eksplisit.
7. Jika citation tidak tersedia, jawaban dianggap tidak memenuhi standar RINGKAS.

### 13.5 Retrieval Sufficiency Rule

MVP tidak menggunakan threshold skor numerik tetap.

Namun, sistem tetap memiliki rule kecukupan sumber:

- minimal ada chunk relevan yang dapat dijadikan citation;
- jika chunk tidak cukup relevan, sistem memberi jawaban parsial dengan keterbatasan atau menolak menjawab substantif;
- threshold numerik ditentukan setelah baseline evaluasi retrieval;
- sistem tidak boleh mengklaim jawaban benar hanya berdasarkan skor retrieval.

---

## 14. Evaluation Plan

### 14.1 Evaluation Principle

RINGKAS menggunakan pendekatan **automated-first evaluation**.

Artinya:

- RAGAS digunakan sebagai evaluasi otomatis utama;
- LLM-as-judge boleh digunakan sebagai bantuan;
- evaluasi manual dibuat seminimal mungkin;
- evaluasi manual tidak dihapus sepenuhnya;
- hasil RAGAS tidak dianggap sebagai satu-satunya bukti kualitas sistem.

### 14.2 Evaluation Dataset

Dataset evaluasi awal:

- 100 pertanyaan;
- pertanyaan dibuat dengan bantuan LLM;
- semua pertanyaan diverifikasi manual sebelum dipakai;
- jawaban referensi atau evidence chunk ditandai dari dokumen BPS;
- pertanyaan mencakup topik utama corpus DKI Jakarta;
- pertanyaan mencakup variasi:
  - definisi;
  - angka;
  - periode;
  - wilayah;
  - metodologi;
  - pencarian dokumen.

### 14.3 Retrieval Evaluation

Retrieval evaluation:

- RAGAS digunakan sebagai evaluasi otomatis awal untuk retrieval/context quality;
- retrieval tetap memakai dataset 100 pertanyaan yang sudah diverifikasi;
- evidence chunk atau ground truth source ditandai dari dokumen BPS;
- manual relevance judgment dilakukan pada subset kecil;
- Recall@K, MRR, nDCG, dan Hit Rate boleh dihitung jika ground truth tersedia;
- jika metrik klasik belum siap, MVP minimal memakai RAGAS + manual audit subset.

### 14.4 Generation Evaluation

Generation evaluation:

- RAGAS digunakan untuk membantu evaluasi faithfulness dan answer relevance;
- LLM-as-judge boleh digunakan sebagai bantuan evaluasi;
- citation accuracy dicek manual pada subset kecil;
- correctness angka, periode, wilayah, satuan, dan definisi dicek manual pada subset kecil;
- human evaluation tidak dilakukan penuh untuk semua jawaban kecuali diperlukan;
- hasil automated evaluation wajib diberi catatan keterbatasan.

### 14.5 Manual Audit

Manual audit:

- 20% dari dataset evaluasi awal.

Karena dataset awal berisi 100 pertanyaan, manual audit minimal mencakup:

- 20 pertanyaan.

Rekomendasi operasional:

- kasus gagal/meragukan menurut automated evaluation tetap diprioritaskan untuk dicek jika memungkinkan.

### 14.6 Evaluation Claim Boundary

Batas klaim evaluasi:

- jika evaluasi manual hanya subset kecil, laporan tidak boleh mengklaim sistem sudah akurat secara menyeluruh;
- hasil evaluasi disebut sebagai baseline awal MVP;
- metrik minimum final ditentukan setelah baseline eksperimen;
- jika ditemukan banyak error angka/citation pada audit manual, pipeline wajib diperbaiki sebelum dianggap layak;
- evaluasi otomatis dipakai untuk iterasi cepat, bukan sebagai satu-satunya validasi akhir.

---

## 15. Success Criteria

### 15.1 Product Success Criteria

MVP dianggap berhasil secara produk jika:

1. User bisa register/login.
2. Guest bisa mencoba 1 prompt dengan citation.
3. User bisa mencari dokumen berdasarkan metadata/kata kunci.
4. User bisa bertanya dan menerima jawaban dengan citation.
5. User bisa melihat riwayat chat.
6. Admin/System Maintainer bisa menjalankan ingestion dari UI sederhana.
7. Sistem bisa memproses corpus DKI Jakarta 5 tahun terakhir.
8. Sistem memberi batasan jika sumber tidak cukup.

### 15.2 Technical Success Criteria

MVP dianggap berhasil secara teknis jika:

1. Ingestion API BPS berjalan.
2. PDF digital berhasil diparsing.
3. Chunk tersimpan dengan metadata citation.
4. Embedding tersimpan di Qdrant.
5. Hybrid retrieval menghasilkan chunk relevan.
6. Jawaban memiliki citation valid.
7. Dokumen gagal diproses diberi status `failed`.
8. Sistem tidak menjawab substantif jika sumber tidak cukup.

### 15.3 RAG Evaluation Success Criteria

MVP dianggap cukup secara evaluasi jika:

1. Retrieval mencapai nilai minimal pada metrik yang ditentukan setelah baseline.
2. Jawaban dinilai grounded terhadap sumber.
3. Citation mengarah ke dokumen/halaman yang benar.
4. Tidak ada angka, periode, wilayah, satuan penting yang dikarang.
5. Metrik minimum final ditentukan setelah baseline eksperimen.

---

## 16. Risks and Mitigations

| Risk ID | Risiko | Dampak | Mitigasi Awal |
|---|---|---|---|
| R-01 | API BPS tidak menyediakan metadata/PDF secara lengkap | Corpus tidak lengkap | Verifikasi API BPS, simpan status missing metadata |
| R-02 | PDF parsing gagal atau noisy | Retrieval buruk | Logging, status failed, parser modular |
| R-03 | Tabel kompleks tidak terbaca akurat | Jawaban berbasis tabel bisa salah | Best-effort, low_structure_confidence, tidak klaim akurat |
| R-04 | Retrieval salah dokumen/periode/wilayah | Jawaban misleading | Metadata chunk, citation, audit retrieval |
| R-05 | LLM membuat jawaban tidak grounded | Hallucination | Prompt policy, citation requirement, refusal policy |
| R-06 | Citation salah halaman/sumber | Verifikasi sumber gagal | Simpan halaman awal/akhir, manual audit subset |
| R-07 | Biaya/limit provider model tidak cukup karena public registration | Layanan gagal/mahal | Quota, rate limit, token cap, fallback generation |
| R-08 | Local storage VPS penuh | Ingestion gagal | Cap dokumen, monitoring storage, migrasi object storage |
| R-09 | Admin UI melebar jadi dashboard kompleks | Scope creep | Batasi admin UI ke trigger ingestion/status/log ringkas |
| R-10 | Evaluasi terlalu luas karena semua topik DKI Jakarta masuk | Evaluasi lama/noisy | Dataset 100 pertanyaan mencakup topik utama |
| R-11 | RAGAS memberi skor baik tapi gagal menangkap kesalahan angka/satuan/konteks | Evaluasi misleading | Manual audit 20%, evidence chunk, batas klaim |
| R-12 | Human verification terlalu sedikit | Error citation/angka tidak terdeteksi | Manual audit minimal 20% |
| R-13 | Ground truth evaluasi kurang kuat | Metrik tidak reliable | Evidence chunk/reference answer ditandai dari dokumen BPS |

---

## 17. Assumptions

Asumsi awal:

1. API BPS dapat menyediakan metadata dan/atau link PDF publikasi yang dibutuhkan.
2. Publikasi BPS DKI Jakarta 5 tahun terakhir tersedia dalam format PDF digital yang dapat diproses tanpa OCR.
3. Jumlah publikasi dalam scope MVP tidak melebihi 300 dokumen, atau dapat diprioritaskan jika lebih.
4. VPS memiliki storage cukup untuk menyimpan PDF, metadata, dan service backend.
5. NVIDIA NIM digunakan sebagai provider generation utama dengan model `nvidia/nemotron-3-nano-30b-a3b`; secondary reserve models are `mistralai/mistral-small-4-119b-2603` and `nvidia/nemotron-mini-4b-instruct`.
6. Cloudflare Workers AI digunakan sebagai fallback generation dengan model `@cf/meta/llama-3.3-70b-instruct-fp8-fast`; `@cf/meta/llama-4-scout-17b-16e-instruct` is the experimental last-resort model, and Cloudflare remains the sole embedding provider with `@cf/qwen/qwen3-embedding-0.6b`.
7. RAGAS dan LLM-as-judge dapat membantu evaluasi otomatis, tetapi tetap memiliki keterbatasan.
8. Manual audit 20% cukup untuk baseline awal MVP, bukan untuk klaim akurasi menyeluruh.

---

## 18. Open Questions / TBD

TBD yang masih perlu diputuskan:

1. Detail terms dan limit API BPS yang berlaku untuk deployment.
2. Model generation NVIDIA NIM lain untuk eksperimen lanjutan.
3. Model fallback Cloudflare Workers AI lain untuk eksperimen lanjutan.
6. Sparse retrieval method di Qdrant.
7. Reranker provider/model jika feature flag diaktifkan.
8. Threshold numerik minimum relevansi setelah baseline eksperimen.
9. Prompt template final.
10. Schema database final.
11. Schema Qdrant collection final.
12. Detail UI/UX chat dan citation panel.
13. Detail UI/UX admin ingestion.
14. Export jawaban ke PDF/Word: out-of-scope atau MVP Plus.
15. Deployment detail VPS.
16. Backup strategy untuk PDF dan database.
17. Rate limit dan quota final untuk guest dan registered user.
18. Evaluasi final setelah baseline eksperimen.

---

## 19. Development Priority

Urutan implementasi awal:

1. Setup PostgreSQL dan Qdrant.
2. API BPS ingestion.
3. Download dan parsing PDF.
4. Cleaning dan chunking.
5. Embedding, vector indexing, dan wiring processor ingestion end-to-end.
6. Retrieval hybrid.
7. Citation mechanism.
8. Generation pipeline.
9. Evaluation harness awal.
10. Auth dan user role.
11. Chat UI.
12. Search dokumen.
13. Admin UI sederhana.

Catatan:

- Evaluation harness sebaiknya dibuat sebelum UI selesai agar kualitas RAG diuji sejak awal.
- Jangan mulai dari frontend penuh sebelum ingestion, parsing, retrieval, dan citation terbukti berjalan.
- Admin UI harus tetap sempit agar tidak melebar menjadi dashboard kompleks.

---

## 20. Next Recommended Documents

Dokumen lanjutan yang disarankan:

1. `TECHNICAL_ARCHITECTURE.md`
2. `DATA_INGESTION_SPEC.md`
3. `RAG_PIPELINE_SPEC.md`
4. `DATABASE_SCHEMA.md`
5. `QDRANT_COLLECTION_SCHEMA.md`
6. `CITATION_POLICY.md`
7. `PROMPTING_SPEC.md`
8. `EVALUATION_PLAN.md`
9. `API_SPEC.md`
10. `MVP_BACKLOG.md`
11. `RISK_REGISTER.md`
12. `DEPLOYMENT_PLAN.md`

---

## 21. Final Notes

Project Brief ini adalah baseline awal yang disusun dari requirement gathering. Dokumen ini belum menggantikan hasil eksperimen, benchmark, atau validasi API/provider.

Setiap keputusan teknis yang masih TBD harus diverifikasi sebelum implementasi penuh, terutama:

- terms, limits, dan availability API/provider;
- vector schema dan sparse retrieval method;
- retrieval quality dan citation accuracy;
- reranker jika diaktifkan;
- rate limit, quota, dan biaya;
- domain/HTTPS, session strategy, dan storage capacity;
- evaluasi baseline.
