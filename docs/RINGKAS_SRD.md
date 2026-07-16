# Software Requirements Document (SRD/SRS) — RINGKAS RAG BPS

**Project Name:** RINGKAS  
**Full Name:** Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik  
**Document Type:** Software Requirements Document / Software Requirements Specification  
**Status:** Initial System Requirement Baseline  
**Version:** 1.0  
**Date:** 2026-07-08  
**Language:** Bahasa Indonesia  
**Source Documents:** `RINGKAS_PROJECT_BRIEF.md`, `RINGKAS_PRD.md`

---

## 1. Purpose

Dokumen ini mendefinisikan requirement sistem/software RINGKAS. Fokus SRD adalah perilaku sistem, fungsi backend/frontend, data, integrasi, penyimpanan, retrieval, generation, citation, evaluasi, error handling, keamanan dasar, dan constraint teknis.

SRD ini belum menggantikan Technical Specification, API Specification, Database Schema, Qdrant Collection Schema, atau Implementation Backlog.

---

## 2. System Overview

RINGKAS adalah aplikasi web RAG berbasis publikasi BPS. Sistem mengambil metadata dan PDF publikasi BPS dari API BPS, memproses PDF digital menggunakan pipeline text-first, menyimpan metadata di PostgreSQL, menyimpan embedding/chunk di Qdrant, lalu menjawab pertanyaan user menggunakan retrieval hybrid dan LLM generation dengan citation.

Next.js + TypeScript dengan App Router berfungsi sebagai frontend/web presentation layer dan API consumer terhadap ASP.NET Core Web API. ASP.NET Core adalah main backend/API dan source of truth untuk domain logic dan authorization. Python RAG Worker adalah internal processing service dan tidak public-facing.

---

## 3. System Scope

### 3.1 In Scope MVP

1. Public self-registration.
2. Email-password login.
3. Google OAuth.
4. Guest trial mode 1 prompt.
5. Chat/Q&A berbasis corpus BPS.
6. Citation untuk semua jawaban substantif.
7. Search dokumen berdasarkan metadata/kata kunci.
8. Riwayat chat user login.
9. Admin UI sederhana untuk ingestion.
10. Ingestion dari API BPS.
11. PDF parsing text-first menggunakan PyMuPDF.
12. Hybrid retrieval menggunakan Qdrant dense + sparse vector.
13. RRF fusion.
14. Generation dengan NVIDIA NIM primary dan Cloudflare Workers AI fallback.
15. Embedding dengan Cloudflare Workers AI model `@cf/qwen/qwen3-embedding-0.6b` saja.
16. Evaluasi automated-first menggunakan RAGAS/LLM-as-judge dan manual audit 20%.

### 3.2 Out of Scope MVP

1. OCR.
2. PDF scan processing.
3. Full visual understanding.
4. Guaranteed complex table extraction.
5. Real-time BPS database query.
6. User document upload.
7. Fine-tuning LLM.
8. Training embedding model.
9. Complex admin dashboard.
10. Complex RBAC.
11. Native mobile app.
12. Payment/subscription.
13. Third-party public API.

---

## 4. Actors and Roles

### 4.1 Guest

- Dapat mengirim 1 prompt.
- Dapat melihat citation minimal.
- Tidak punya riwayat chat.
- Tidak bisa search dokumen penuh.

### 4.2 Registered User

- Dapat login.
- Dapat chat/Q&A.
- Dapat melihat citation.
- Dapat search dokumen.
- Dapat melihat riwayat chat.

### 4.3 Admin/System Maintainer

- Dapat trigger ingestion melalui admin UI sederhana.
- Dapat melihat status job ingestion.
- Dapat melihat log ringkas.
- Tidak melakukan upload dokumen user.
- Tidak memiliki dashboard analytics kompleks pada MVP.

---

## 5. System Architecture Requirements

### AR-001 Runtime

MVP harus dapat menjalankan container Next.js frontend, ASP.NET Core API, Python RAG Worker, PostgreSQL, dan Qdrant melalui Docker Compose pada satu VPS.

### AR-001A Frontend Boundary

Next.js tidak boleh menggantikan ASP.NET Core sebagai backend utama atau mengakses PostgreSQL maupun Qdrant secara langsung. Core business logic, authentication, authorization, Chat/Q&A API, document search API, admin ingestion API, rate limiting, dan application logging tetap berada di ASP.NET Core Web API.

### AR-001B Worker Boundary

Python RAG Worker harus tetap menjadi internal processing service dan tidak boleh diekspos sebagai public-facing API.

### AR-002 Storage

PDF hasil download dari API BPS disimpan di local persistent storage VPS pada MVP.

### AR-003 Future Storage Migration

Sistem harus mempertimbangkan kemungkinan migrasi PDF ke object storage jika skala meningkat.

### AR-004 Database

PostgreSQL digunakan untuk:

- user/auth metadata;
- role;
- metadata dokumen;
- ingestion job status;
- ingestion logs;
- chat history;
- document search/filter data.

### AR-005 Vector Database

Qdrant digunakan untuk:

- dense vector;
- sparse vector;
- hybrid retrieval;
- metadata payload per chunk.

### AR-006 Parser Modularity

Parser dibuat modular agar PyMuPDF dapat diganti atau dibandingkan dengan parser lain di masa depan.

---

## 6. Functional Requirements

### 6.1 Authentication and Access Control

#### FR-AUTH-001 Public Registration

Sistem harus memungkinkan user melakukan self-registration.

#### FR-AUTH-002 Email-Password Login

Sistem harus menyediakan login email-password.

#### FR-AUTH-003 Google OAuth

Sistem harus mendukung Google OAuth pada MVP.

#### FR-AUTH-004 Role-Based Basic Access

Sistem harus membedakan minimal role berikut:

- Guest;
- Registered User;
- Admin/System Maintainer.

#### FR-AUTH-005 Admin Protection

Endpoint dan UI admin ingestion hanya boleh diakses oleh Admin/System Maintainer.

#### FR-AUTH-006 Future OAuth

GitHub OAuth, Telegram OAuth, dan Hugging Face OAuth tidak masuk MVP dan dicatat sebagai future plan.

---

### 6.2 Guest Mode

#### FR-GUEST-001 Prompt Limit

Guest hanya boleh mengirim maksimal 1 prompt.

#### FR-GUEST-002 Citation for Guest

Jika sistem menjawab substantif kepada guest, jawaban tetap harus memiliki citation.

#### FR-GUEST-003 No History

Sistem tidak menyimpan atau menampilkan riwayat chat untuk guest sebagai fitur user-facing.

#### FR-GUEST-004 Guest Restriction

Guest tidak boleh mengakses search dokumen penuh atau fitur lanjutan.

---

### 6.3 Document Ingestion

#### FR-ING-001 Trigger Ingestion

Admin/System Maintainer dapat menjalankan ingestion melalui admin UI sederhana atau endpoint internal.

#### FR-ING-002 API Protection

Endpoint ingestion harus dilindungi auth/API key/internal token.

#### FR-ING-003 Source

Sistem mengambil metadata dan/atau PDF dari API BPS.

#### FR-ING-004 Corpus Filter

Sistem memfilter dokumen sesuai corpus MVP:

- wilayah DKI Jakarta;
- level provinsi;
- 5 tahun terakhir;
- maksimal 300 dokumen jika jumlah memungkinkan.

#### FR-ING-005 PDF Download

Sistem mengunduh PDF dari sumber BPS jika URL tersedia.

#### FR-ING-006 PDF Storage

Sistem menyimpan PDF ke local storage VPS.

#### FR-ING-007 Retry

Sistem melakukan retry beberapa kali jika download/parsing/embedding gagal. Jumlah retry final: TBD.

#### FR-ING-008 Failed Status

Jika tetap gagal, dokumen diberi status `failed` dan ingestion dokumen lain tetap dilanjutkan.

#### FR-ING-009 Logging

Sistem menyimpan log error ingestion dan log ringkas untuk admin UI.

#### FR-ING-010 No User Upload

Sistem tidak menyediakan upload dokumen oleh user pada MVP.

---

### 6.4 PDF Parsing and Text Extraction

#### FR-PARSE-001 Parser

Sistem menggunakan PyMuPDF sebagai parser utama MVP.

#### FR-PARSE-002 Text Layer Only

MVP hanya mendukung PDF digital dengan text layer.

#### FR-PARSE-003 No OCR

Sistem tidak menjalankan OCR pada MVP.

#### FR-PARSE-004 Unsupported Scan

PDF scan tanpa text layer diberi status `unsupported_or_extraction_failed`.

#### FR-PARSE-005 Page Metadata

Sistem harus mempertahankan informasi halaman untuk citation.

#### FR-PARSE-006 Docling Future

Docling tidak masuk parser production MVP dan hanya dicatat sebagai kandidat eksperimen/future plan.

---

### 6.5 Cleaning and Preprocessing

#### FR-CLEAN-001 Header Footer

Sistem boleh menghapus header/footer berulang jika terdeteksi.

#### FR-CLEAN-002 Whitespace

Sistem melakukan normalisasi spasi dan newline.

#### FR-CLEAN-003 Hyphenated Words

Sistem boleh menggabungkan hyphenated words jika aman.

#### FR-CLEAN-004 Page Number Noise

Sistem boleh menghapus nomor halaman yang mengganggu, tetapi tetap menyimpan metadata halaman.

#### FR-CLEAN-005 Heading Preservation

Sistem mempertahankan struktur heading jika terdeteksi.

#### FR-CLEAN-006 No Aggressive Cleaning

Sistem tidak boleh melakukan cleaning agresif yang berisiko menghapus angka, satuan, periode, wilayah, atau definisi statistik.

---

### 6.6 Table Handling

#### FR-TABLE-001 Simple Table Text

Tabel sederhana diekstrak sebagai teks.

#### FR-TABLE-002 Simple Table Markdown

Tabel sederhana boleh diekstrak sebagai markdown table jika memungkinkan.

#### FR-TABLE-003 Complex Table Best-Effort

Tabel kompleks diproses best-effort dan tidak dijamin akurat.

#### FR-TABLE-004 Low Structure Confidence

Jika tabel rusak atau struktur tidak jelas, sistem menyimpan teks mentah dengan metadata `low_structure_confidence`.

---

### 6.7 Chunking

#### FR-CHUNK-001 Strategy

Sistem menggunakan recursive character/text splitter sebagai strategi awal.

#### FR-CHUNK-002 Chunk Size

Chunk size awal adalah 500–800 tokens.

#### FR-CHUNK-003 Chunk Overlap

Chunk overlap awal adalah 20%.

#### FR-CHUNK-004 Chunk Metadata

Setiap chunk wajib memiliki metadata:

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
- `low_structure_confidence` jika relevan;
- `url_sumber`.

---

### 6.8 Embedding and Vector Indexing

#### FR-EMB-001 Embedding Provider

Embedding menggunakan Cloudflare Workers AI saja dengan model
`@cf/qwen/qwen3-embedding-0.6b` pada target MVP.

#### FR-EMB-002 No Embedding Fallback

Tidak ada fallback embedding provider.

#### FR-EMB-003 Embedding Failure

Jika embedding provider gagal, sistem menampilkan error dan tidak otomatis memakai embedding model berbeda.

#### FR-EMB-005 Versioned Collection and Dimension Verification

Provider/model embedding tidak boleh dicampur dengan vector yang sudah ada.
Perubahan provider/model memerlukan collection Qdrant berversi baru dan full
corpus reindex. Dimensi output harus diverifikasi live dari configured model,
memastikan semua vector berdimensi sama dan non-zero, lalu dikunci sebelum
collection baru dibuat. Pembuatan collection harus gagal aman jika dimensi
terverifikasi tidak cocok dengan konfigurasi.

#### FR-EMB-004 Qdrant Storage

Embedding dan chunk payload disimpan di Qdrant.

---

### 6.9 Retrieval

#### FR-RET-001 Hybrid Retrieval

Sistem menggunakan hybrid retrieval dengan Qdrant dense vector + sparse vector.

#### FR-RET-002 Candidate Size

Candidate awal:

- dense top-20;
- sparse top-20.

#### FR-RET-003 Fusion

Sistem menggabungkan hasil dense dan sparse menggunakan Reciprocal Rank Fusion/RRF.

#### FR-RET-004 Final Top-K

Top-K final sebelum generation adalah top-10 chunk.

#### FR-RET-005 No Fixed Numeric Threshold

MVP tidak menggunakan threshold skor numerik tetap.

#### FR-RET-006 Retrieval Sufficiency Rule

Sistem tetap harus memiliki retrieval sufficiency rule sebelum menjawab.

#### FR-RET-007 Minimum Citation Source

Minimal harus ada chunk relevan yang dapat dijadikan citation untuk jawaban substantif.

#### FR-RET-008 Insufficient Source Behavior

Jika chunk tidak cukup relevan, sistem memberi jawaban parsial dengan keterbatasan atau menolak menjawab substantif.

#### FR-RET-009 Future Threshold

Threshold numerik ditentukan setelah baseline evaluasi retrieval.

---

### 6.10 Metadata Filtering

#### FR-FILTER-001 Default Retrieval

Default retrieval tidak memakai filter eksplisit.

#### FR-FILTER-002 Year Filter

Jika user menyebut tahun, sistem boleh memakai filter tahun.

#### FR-FILTER-003 Topic Filter

Jika user menyebut topik/subjek, sistem boleh memakai filter topik jika metadata tersedia.

#### FR-FILTER-004 Document Title Priority

Jika user menyebut judul dokumen, sistem boleh memprioritaskan dokumen tersebut.

#### FR-FILTER-005 Region Default

Wilayah default selalu DKI Jakarta pada MVP.

#### FR-FILTER-006 Filter Caution

Filter tidak boleh terlalu ketat sampai membuang sumber relevan.

---

### 6.11 Generation

#### FR-GEN-001 Primary Provider

Generation primary menggunakan NVIDIA NIM.

#### FR-GEN-002 Fallback Provider

Jika generation primary gagal, sistem boleh mencoba Cloudflare Workers AI sebagai fallback.

#### FR-GEN-003 Experimental Provider

OpenCode Zen / DeepSeek V4 Flash Free hanya experimental only.

#### FR-GEN-004 Model Specific TBD

Model generation spesifik masih TBD.

#### FR-GEN-005 Context Bound

Generator hanya boleh menjawab berdasarkan chunk yang diberikan.

#### FR-GEN-006 No Unsupported Facts

Generator tidak boleh membuat angka, periode, wilayah, satuan, atau definisi di luar sumber.

#### FR-GEN-007 No Unsupported Trend/Causality

Generator tidak boleh menyimpulkan tren atau kausalitas tanpa sumber eksplisit.

#### FR-GEN-008 Language

Sistem mengikuti bahasa pertanyaan user.

#### FR-GEN-009 Adaptive Format

Format jawaban adaptif mengikuti pertanyaan user, dengan default jawaban langsung singkat dan citation.

---

### 6.12 Citation

#### FR-CITE-001 Citation Required

Semua jawaban substantif harus memiliki citation.

#### FR-CITE-002 Citation Metadata

Citation minimal menampilkan:

- judul dokumen;
- tahun publikasi;
- wilayah;
- halaman jika tersedia;
- URL dokumen atau halaman BPS;
- potongan teks sumber melalui hover/click.

#### FR-CITE-003 Inline Citation

Citation ditampilkan di akhir klaim/paragraf utama.

#### FR-CITE-004 Source Panel

Sistem dapat menampilkan panel sumber.

#### FR-CITE-005 No Citation Failure

Jika citation tidak tersedia, jawaban dianggap tidak memenuhi standar RINGKAS.

#### FR-CITE-006 No User Score

Skor relevansi retrieval/generation tidak ditampilkan ke user umum.

---

### 6.13 Chat History

#### FR-CHAT-001 Store Chat

Sistem menyimpan pertanyaan dan jawaban untuk user login.

#### FR-CHAT-002 Store Citation Reference

Sistem menyimpan referensi citation yang digunakan dalam jawaban.

#### FR-CHAT-003 No Guest History

Guest tidak memiliki riwayat chat user-facing.

---

### 6.14 Document Search

#### FR-SEARCH-001 Search by Keyword

User login dapat mencari dokumen berdasarkan kata kunci.

#### FR-SEARCH-002 Search by Metadata

User login dapat mencari/filter dokumen berdasarkan metadata jika tersedia.

#### FR-SEARCH-003 Search Result Metadata

Hasil search menampilkan metadata dasar seperti judul, tahun, wilayah, topik/subjek jika tersedia, dan URL sumber.

#### FR-SEARCH-004 Guest Restriction

Guest tidak mendapatkan search dokumen penuh.

---

### 6.15 Admin UI

#### FR-ADMIN-001 UI Scope

Admin UI MVP hanya mencakup:

- trigger ingestion;
- status job;
- log ringkas.

#### FR-ADMIN-002 No Upload

Admin UI MVP tidak mencakup upload dokumen oleh user.

#### FR-ADMIN-003 No Complex Dashboard

Admin UI MVP tidak mencakup dashboard analytics kompleks.

#### FR-ADMIN-004 No Full Document Management

Admin UI MVP tidak mencakup edit/delete massal/reprocess detail.

---

### 6.16 Evaluation

#### FR-EVAL-001 Automated First

Sistem evaluasi menggunakan pendekatan automated-first.

#### FR-EVAL-002 RAGAS

RAGAS digunakan sebagai evaluasi otomatis utama/awal.

#### FR-EVAL-003 LLM-as-Judge

LLM-as-judge boleh digunakan sebagai bantuan evaluasi.

#### FR-EVAL-004 Dataset Size

Dataset evaluasi awal berisi 100 pertanyaan.

#### FR-EVAL-005 Dataset Verification

Semua pertanyaan evaluasi diverifikasi manual sebelum digunakan.

#### FR-EVAL-006 Evidence Chunk

Jawaban referensi atau evidence chunk harus dibuat/ditandai dari dokumen BPS.

#### FR-EVAL-007 Topic Coverage

Pertanyaan evaluasi harus mencakup topik utama corpus DKI Jakarta dan variasi definisi, angka, periode, wilayah, metodologi, dan pencarian dokumen.

#### FR-EVAL-008 Manual Audit

Manual audit minimal 20% dari dataset evaluasi awal.

#### FR-EVAL-009 Manual Audit Scope

Manual audit memeriksa citation accuracy dan correctness angka/periode/wilayah/satuan/definisi pada subset kecil.

#### FR-EVAL-010 Claim Boundary

Hasil evaluasi disebut baseline awal MVP dan tidak boleh diklaim sebagai akurasi menyeluruh.

---

## 7. Data Requirements

### DR-001 Document Metadata Required

Metadata wajib:

- judul publikasi;
- tahun publikasi;
- wilayah;
- level wilayah;
- URL halaman publikasi BPS atau identifier sumber;
- status ingestion;
- waktu ingestion;
- hash/checksum file.

### DR-002 Document Metadata Required If Available

Metadata disimpan jika tersedia:

- tanggal rilis;
- topik/subjek;
- nomor katalog;
- nomor publikasi;
- URL PDF;
- bahasa dokumen;
- jumlah halaman;
- sumber API/endpoint.

### DR-003 Ingestion Status

Status ingestion minimal:

- `pending`;
- `running`;
- `success`;
- `failed`;
- `unsupported_or_extraction_failed`.

### DR-004 Extraction Method

Setiap chunk menyimpan `extraction_method`. Untuk MVP nilainya adalah `text_layer`.

### DR-005 Low Structure Confidence

Chunk dari tabel/struktur yang tidak jelas dapat diberi flag `low_structure_confidence`.

---

## 8. Non-Functional Requirements

### NFR-001 Grounding

Semua jawaban substantif harus grounded ke chunk yang di-retrieve dan memiliki citation.

### NFR-002 Reliability

Kegagalan satu dokumen dalam ingestion tidak boleh menghentikan seluruh ingestion batch.

### NFR-003 Maintainability

Parser, embedding provider, generation provider, retrieval, dan reranking harus dibuat modular sejauh realistis untuk MVP.

### NFR-004 Security Basic

Sistem harus menerapkan proteksi dasar:

- auth untuk user login;
- role admin;
- endpoint ingestion protected;
- rate limit guest;
- quota prompt;
- token/response cap;
- basic abuse/spam control.

### NFR-005 Privacy

Riwayat chat user tidak boleh dapat diakses user lain.

### NFR-006 Auditability

Sistem harus menyimpan metadata sumber, halaman, dan citation reference agar jawaban dapat diaudit.

### NFR-007 Performance TBD

Target latency, throughput, dan concurrency masih TBD.

### NFR-008 Cost Control

Sistem harus memiliki pembatasan penggunaan karena public registration dibuka.

### NFR-009 Storage Control

Sistem harus mempertimbangkan kapasitas local storage VPS dan kemungkinan migrasi ke object storage.

---

## 9. External Interfaces

### EI-001 API BPS

Sistem mengambil metadata dan/atau PDF dari API BPS. Detail endpoint, parameter, response schema, limit, dan terms masih TBD dan harus diverifikasi sebelum implementasi penuh.

### EI-002 NVIDIA NIM

Digunakan untuk:

- generation primary;
- embedding provider.

Model spesifik, rate limit, dan availability masih TBD.

### EI-003 Cloudflare Workers AI

Digunakan sebagai generation fallback. Model spesifik, rate limit, dan availability masih TBD.

### EI-004 Google OAuth

Digunakan untuk login OAuth pada MVP.

### EI-005 OpenCode Zen

OpenCode Zen / DeepSeek V4 Flash Free hanya experimental only, bukan provider primary.

---

## 10. Error Handling Requirements

### ERR-001 Insufficient Source

Jika sumber tidak cukup, sistem memberi jawaban parsial dengan keterbatasan atau menolak menjawab substantif.

### ERR-002 No Citation

Jika citation tidak tersedia, jawaban substantif tidak boleh dianggap valid.

### ERR-003 PDF Download Failure

Jika PDF gagal di-download, sistem retry dan jika tetap gagal memberi status `failed`.

### ERR-004 PDF Unsupported

PDF scan tanpa text layer diberi status `unsupported_or_extraction_failed`.

### ERR-005 Embedding Provider Failure

Jika embedding provider gagal, sistem menampilkan error dan tidak otomatis mengganti embedding model.

### ERR-006 Generation Primary Failure

Jika NVIDIA NIM generation gagal, sistem boleh mencoba Cloudflare Workers AI fallback.

### ERR-007 Ingestion Partial Failure

Jika satu dokumen gagal, ingestion dokumen lain tetap dilanjutkan.

---

## 11. Evaluation Requirements

### EV-001 Automated-First

Evaluasi menggunakan RAGAS sebagai evaluasi otomatis utama/awal.

### EV-002 Manual Audit Minimum

Manual audit minimal 20 pertanyaan dari 100 pertanyaan evaluasi awal.

### EV-003 Evidence Grounding

Evidence chunk atau ground truth source harus ditandai dari dokumen BPS.

### EV-004 Retrieval Metrics

Recall@K, MRR, nDCG, dan Hit Rate boleh dihitung jika ground truth tersedia.

### EV-005 Generation Metrics

Generation dinilai menggunakan:

- faithfulness/groundedness;
- answer relevance;
- citation accuracy;
- correctness angka/periode/wilayah/satuan/definisi pada subset audit.

### EV-006 Evaluation Claim

Hasil evaluasi adalah baseline awal MVP, bukan klaim akurasi menyeluruh.

---

## 12. Acceptance Criteria Summary

MVP secara sistem dianggap memenuhi SRD jika:

1. Auth dan role dasar berjalan.
2. Guest dapat mencoba satu prompt dengan citation.
3. Registered user dapat chat, search dokumen, dan melihat riwayat.
4. Admin dapat trigger ingestion dari UI sederhana.
5. Ingestion API BPS berjalan untuk corpus DKI Jakarta 5 tahun terakhir.
6. PDF digital berhasil diparsing dengan PyMuPDF.
7. Chunk metadata lengkap tersimpan.
8. Embedding tersimpan di Qdrant.
9. Hybrid retrieval dense + sparse dengan RRF berjalan.
10. Generation menghasilkan jawaban berbasis chunk.
11. Citation tersedia untuk semua jawaban substantif.
12. Sistem menolak/menahan jawaban jika sumber tidak cukup.
13. Evaluation harness awal berjalan dengan dataset 100 pertanyaan.
14. Manual audit 20% dilakukan untuk baseline awal.

---

## 13. Open Questions / TBD

1. Endpoint API BPS spesifik.
2. API response schema BPS.
3. Model generation NVIDIA NIM spesifik.
4. Verifikasi live dimensi output model embedding Cloudflare.
5. Model Cloudflare Workers AI fallback spesifik.
6. Sparse vector method di Qdrant.
7. Qdrant collection schema final.
8. PostgreSQL schema final.
9. Prompt template final.
10. Reranker provider/model jika feature flag diaktifkan.
11. Exact rate limit guest.
12. Exact quota registered user.
13. Email verification implementation.
14. Latency/performance target.
15. Backup strategy.
16. Deployment detail VPS.
17. UI/UX detail chat, search, citation panel, dan admin.

---

## 14. Traceability to PRD

| PRD Feature | SRD Section |
|---|---|
| Authentication | 6.1 |
| Guest Trial Mode | 6.2 |
| Chat/Q&A | 6.11, 6.12, 6.13 |
| Citation | 6.12 |
| Search Dokumen | 6.14 |
| Riwayat Chat | 6.13 |
| Admin UI | 6.15 |
| Ingestion | 6.3 |
| Parsing | 6.4–6.6 |
| Retrieval | 6.8–6.10 |
| Evaluation | 6.16, 11 |

---

## 15. Relationship to Technical Documents

Dokumen ini perlu diturunkan lagi menjadi:

1. `TECHNICAL_SPEC.md`
2. `DATABASE_SCHEMA.md`
3. `QDRANT_COLLECTION_SCHEMA.md`
4. `API_SPEC.md`
5. `RAG_PIPELINE_SPEC.md`
6. `PROMPTING_SPEC.md`
7. `EVALUATION_PLAN.md`
8. `TASKS.md`
9. `AGENTS.md`
