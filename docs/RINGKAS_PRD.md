# Product Requirements Document (PRD) — RINGKAS RAG BPS

**Project Name:** RINGKAS  
**Full Name:** Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik  
**Document Type:** Product Requirements Document (PRD)  
**Status:** Initial Product Baseline  
**Version:** 1.0  
**Date:** 2026-07-08  
**Language:** Bahasa Indonesia  
**Source Document:** `RINGKAS_PROJECT_BRIEF.md`

---

## 1. Purpose

Dokumen ini mendefinisikan kebutuhan produk RINGKAS dari sisi pengguna, fitur, perilaku sistem, MVP scope, user journey, dan acceptance criteria produk.

PRD ini tidak menggantikan dokumen teknis rinci seperti SRD/SRS, Technical Architecture, API Spec, Database Schema, atau Task Backlog. PRD ini menjadi jembatan antara Project Brief dan dokumen implementasi teknis.

---

## 2. Product Summary

RINGKAS adalah web Retrieval-Augmented Generation (RAG) untuk pencarian, tanya jawab, dan ringkasan berbasis dokumen publikasi Badan Pusat Statistik (BPS). Sistem wajib menghasilkan jawaban yang grounded ke dokumen dalam corpus dan menyertakan citation ke sumber.

MVP RINGKAS berfokus pada publikasi BPS DKI Jakarta tingkat provinsi dalam 5 tahun terakhir. Sistem ditargetkan untuk validasi awal oleh 10–30 user internal, tetapi akses produk mengizinkan public self-registration sehingga perlu kontrol abuse dasar.

Produk disajikan melalui Next.js + TypeScript dengan App Router sebagai frontend/web presentation layer dan API consumer terhadap ASP.NET Core Web API. ASP.NET Core tetap menjadi main backend/API dan source of truth untuk domain logic, authentication, authorization, Chat/Q&A, document search, admin ingestion, rate limiting, dan application logging. Python RAG Worker tetap menjadi internal processing service. Next.js tidak mengakses PostgreSQL atau Qdrant secara langsung.

---

## 3. Background and Problem

Publikasi BPS berisi informasi statistik resmi yang penting, tetapi pengguna sering harus membaca banyak PDF panjang secara manual. Informasi tersebar berdasarkan wilayah, periode, topik, dan jenis publikasi. LLM umum tanpa grounding berisiko menghasilkan jawaban yang salah sumber, salah periode, salah wilayah, salah satuan, atau salah definisi.

RINGKAS dibuat untuk mempercepat pencarian dan pemahaman dokumen BPS, sekaligus menjaga akuntabilitas melalui citation dan kebijakan penolakan jawaban jika sumber tidak cukup.

---

## 4. Goals

### 4.1 Product Goals

1. Memungkinkan user bertanya tentang isi publikasi BPS dan menerima jawaban berbasis dokumen.
2. Menampilkan citation untuk setiap jawaban substantif.
3. Memungkinkan user mencari dokumen berdasarkan metadata/kata kunci.
4. Menyediakan riwayat chat untuk user login.
5. Menyediakan guest trial mode terbatas.
6. Menyediakan admin UI sederhana untuk ingestion dokumen dari API BPS.
7. Menyediakan baseline evaluasi kualitas RAG secara automated-first dengan manual audit minimal.

### 4.2 Non-Goals / Out of Scope MVP

Tidak masuk MVP:

1. Upload dokumen oleh user.
2. OCR atau pemrosesan PDF scan.
3. Pemahaman visual penuh atas grafik/gambar.
4. Ekstraksi tabel kompleks yang dijamin akurat.
5. Query langsung ke database statistik BPS real-time.
6. Integrasi data tabel BPS real-time.
7. Analisis statistik otomatis.
8. Visualisasi grafik otomatis.
9. Forecasting/prediksi indikator.
10. Rekomendasi kebijakan otomatis.
11. Fine-tuning LLM.
12. Training embedding model sendiri.
13. Mobile app native.
14. Payment/subscription.
15. Public API pihak ketiga.
16. Multi-user collaboration.
17. RBAC kompleks.
18. Dashboard analytics kompleks.
19. Audit log kompleks.
20. Integrasi WhatsApp/Telegram.
21. Voice input/output.
22. Multi-language support termasuk bahasa daerah.
23. OAuth GitHub, Telegram, dan Hugging Face.

---

## 5. Target Users

### 5.1 Primary Evaluation Users

- Tim internal kecil, sekitar 10–30 user.
- Digunakan untuk validasi awal kualitas sistem, usability, retrieval quality, citation quality, dan generation quality.

### 5.2 Secondary Users

- Mahasiswa.
- Peneliti.
- Pengguna publikasi BPS.
- Pengguna yang membutuhkan pencarian cepat terhadap dokumen statistik resmi.

### 5.3 Guest/Public User

Guest/Public User dapat mencoba sistem secara terbatas tanpa login.

Batasan guest:

- maksimal 1 prompt;
- tetap melihat citation minimal;
- tidak memiliki riwayat chat;
- tidak dapat search dokumen penuh;
- tidak dapat upload dokumen;
- tidak dapat mengakses fitur lanjutan.

---

## 6. User Personas

### P-01 — Internal Research User

**Deskripsi:** anggota tim internal yang ingin menguji sistem dan mencari informasi BPS secara cepat.  
**Kebutuhan:** jawaban cepat, citation jelas, hasil retrieval dapat diverifikasi.  
**Risiko:** salah percaya pada jawaban tanpa memeriksa sumber.

### P-02 — Mahasiswa/Peneliti

**Deskripsi:** pengguna yang membutuhkan rujukan statistik untuk kajian atau tugas akademik.  
**Kebutuhan:** menemukan dokumen, memahami definisi indikator, melihat sumber.  
**Risiko:** salah mengambil angka, tahun, wilayah, atau satuan.

### P-03 — Guest/Public Trial User

**Deskripsi:** pengguna publik yang ingin mencoba sistem sebelum membuat akun.  
**Kebutuhan:** mencoba satu prompt dan melihat apakah jawaban bersumber.  
**Risiko:** abuse/spam jika tidak dibatasi.

### P-04 — Admin/System Maintainer

**Deskripsi:** developer/admin teknis yang mengelola ingestion corpus.  
**Kebutuhan:** trigger ingestion, melihat status job, melihat log ringkas.  
**Risiko:** admin UI melebar menjadi dashboard kompleks.

---

## 7. Core User Journeys

### UJ-01 — Guest mencoba satu prompt

1. Guest membuka web RINGKAS.
2. Guest mengajukan satu pertanyaan.
3. Sistem melakukan retrieval pada corpus.
4. Sistem memberi jawaban dengan citation jika sumber cukup.
5. Sistem membatasi guest setelah satu prompt.

### UJ-02 — User register/login dan bertanya

1. User membuat akun atau login.
2. User masuk ke halaman chat.
3. User mengajukan pertanyaan.
4. Sistem mengambil chunk relevan.
5. Sistem menghasilkan jawaban dengan citation.
6. Sistem menyimpan riwayat chat user.

### UJ-03 — User mencari dokumen

1. User membuka fitur search dokumen.
2. User memasukkan keyword atau metadata seperti judul/tahun/topik.
3. Sistem menampilkan daftar dokumen relevan.
4. User dapat membuka metadata dan sumber dokumen.

### UJ-04 — User meminta ringkasan berbasis pertanyaan

1. User bertanya dalam bentuk permintaan ringkasan.
2. Sistem melakukan retrieval chunk relevan.
3. Sistem menghasilkan ringkasan berdasarkan sumber.
4. Sistem menampilkan citation.

### UJ-05 — Admin menjalankan ingestion

1. Admin login.
2. Admin membuka admin UI sederhana.
3. Admin menekan trigger ingestion.
4. Sistem menjalankan job ingestion.
5. Admin melihat status job dan log ringkas.

---

## 8. MVP Feature Requirements

### F-01 Authentication

**Description:** Sistem menyediakan registrasi dan login user.  
**Priority:** Must Have

Requirements:

- User dapat register sendiri.
- User dapat login menggunakan email dan password.
- User dapat login menggunakan Google OAuth.
- Sistem mendukung verifikasi email atau mekanisme verifikasi yang setara. Status implementasi detail: TBD.
- Sistem membedakan Guest, Registered User, dan Admin/System Maintainer.

Acceptance Criteria:

- User baru dapat membuat akun.
- User terdaftar dapat login/logout.
- User login dapat mengakses fitur chat dan riwayat.
- Admin dapat mengakses admin UI sederhana.
- Guest tidak memiliki akses ke riwayat chat atau search dokumen penuh.

---

### F-02 Guest Trial Mode

**Description:** Guest dapat mencoba sistem secara terbatas.  
**Priority:** Must Have

Requirements:

- Guest dapat mengirim maksimal 1 prompt.
- Guest tetap menerima citation minimal jika sistem menjawab substantif.
- Guest tidak memiliki riwayat chat.
- Guest tidak dapat menggunakan search dokumen penuh.
- Guest dikenai rate limit per IP.

Acceptance Criteria:

- Guest dapat mengirim satu pertanyaan.
- Setelah batas terpakai, sistem meminta guest login/register.
- Jawaban guest tetap memiliki citation jika bersifat substantif.

---

### F-03 Chat/Q&A Berbasis Dokumen

**Description:** User dapat bertanya tentang publikasi BPS dalam corpus.  
**Priority:** Must Have

Requirements:

- User dapat mengirim pertanyaan natural language.
- Sistem menjawab hanya berdasarkan chunk yang diberikan retrieval.
- Sistem menggunakan retrieval sufficiency rule sebelum menjawab substantif.
- Sistem tidak boleh membuat angka, periode, wilayah, satuan, atau definisi di luar sumber.
- Sistem menolak menjawab substantif jika sumber tidak cukup.

Acceptance Criteria:

- Jawaban substantif selalu memiliki citation.
- Jawaban menyebut keterbatasan jika sumber kurang.
- Jika tidak ada sumber cukup, sistem menolak menjawab substantif.
- Chat tersimpan untuk user login.

---

### F-04 Citation

**Description:** Sistem menampilkan citation untuk mendukung verifikasi sumber.  
**Priority:** Must Have

Citation minimal:

- judul dokumen;
- tahun publikasi;
- wilayah;
- halaman jika berhasil diekstrak;
- URL dokumen atau halaman BPS;
- potongan teks sumber melalui hover/click citation.

Requirements:

- Citation muncul inline pada klaim utama/paragraf.
- Sistem dapat menampilkan panel sumber.
- Skor relevansi tidak ditampilkan ke user umum.
- Jika citation tidak tersedia, jawaban dianggap tidak memenuhi standar RINGKAS.

Acceptance Criteria:

- Setiap jawaban substantif memiliki minimal satu citation.
- Citation mengarah ke dokumen dan halaman yang relevan jika halaman tersedia.
- User dapat melihat potongan teks sumber.

---

### F-05 Search Dokumen

**Description:** User dapat mencari publikasi dalam corpus.  
**Priority:** Must Have

Requirements:

- User dapat mencari berdasarkan kata kunci.
- User dapat mencari/memfilter berdasarkan metadata jika tersedia.
- Metadata yang dipakai dapat mencakup judul, tahun, wilayah, topik/subjek, dan URL sumber.
- Guest tidak mendapatkan search dokumen penuh.

Acceptance Criteria:

- User login dapat mencari dokumen.
- Sistem menampilkan daftar dokumen relevan.
- Hasil search menampilkan metadata dasar.

---

### F-06 Riwayat Chat

**Description:** User login dapat melihat riwayat chat.  
**Priority:** Must Have

Requirements:

- Sistem menyimpan pertanyaan dan jawaban user login.
- Sistem menyimpan waktu chat.
- Sistem menyimpan referensi citation yang digunakan dalam jawaban.
- Guest tidak memiliki riwayat chat.

Acceptance Criteria:

- User login dapat melihat chat sebelumnya.
- Riwayat tidak bocor ke user lain.

---

### F-07 Admin UI Sederhana

**Description:** Admin/System Maintainer dapat menjalankan ingestion.  
**Priority:** Must Have

Requirements:

- Admin dapat trigger ingestion dari UI sederhana.
- Admin dapat melihat status job.
- Admin dapat melihat log ringkas.
- Endpoint ingestion dilindungi API key/internal token atau auth setara.
- Admin UI tidak mencakup upload dokumen oleh user.
- Admin UI tidak mencakup dashboard analytics kompleks.
- Admin UI tidak mencakup edit/delete massal/reprocess detail.

Acceptance Criteria:

- Admin dapat memulai job ingestion.
- Status job tersimpan di database.
- Error ingestion dapat dilihat sebagai log ringkas.
- User biasa tidak dapat mengakses admin UI.

---

### F-08 Ringkasan Berbasis Pertanyaan

**Description:** User dapat meminta ringkasan berdasarkan pertanyaan tertentu.  
**Priority:** MVP Plus

Requirements:

- Ringkasan dibuat dari chunk relevan.
- Ringkasan wajib memiliki citation.
- Sistem tidak membuat ringkasan penuh dokumen/per bab sebagai MVP awal.

Acceptance Criteria:

- Jika user meminta ringkasan topik tertentu, sistem mengambil chunk relevan.
- Ringkasan menyebut sumber/citation.
- Jika sumber tidak cukup, sistem menyatakan keterbatasan.

---

## 9. Product Behavior Rules

### 9.1 Language

Sistem mengikuti bahasa pertanyaan user.

### 9.2 Default Answer Format

Default jawaban:

- langsung;
- singkat;
- menyertakan citation.

Format adaptif:

- bullet points jika jawaban berisi beberapa poin;
- tabel jika struktur informasi cocok dan sumber mendukung;
- ringkasan + detail jika user meminta penjelasan lebih panjang.

### 9.3 Refusal and Partial Answer

Sistem harus:

- memberi jawaban parsial dengan keterbatasan jika sumber hanya sebagian mendukung;
- menolak menjawab substantif jika sumber benar-benar tidak cukup;
- tidak membuat klaim tanpa citation.

---

## 10. Product Success Criteria

MVP dianggap berhasil secara produk jika:

1. User bisa register/login.
2. Guest bisa mencoba 1 prompt dengan citation.
3. User bisa mencari dokumen berdasarkan metadata/kata kunci.
4. User bisa bertanya dan menerima jawaban dengan citation.
5. User bisa melihat riwayat chat.
6. Admin/System Maintainer bisa menjalankan ingestion dari UI sederhana.
7. Sistem bisa memproses corpus BPS DKI Jakarta 5 tahun terakhir.
8. Sistem memberi batasan jika sumber tidak cukup.

---

## 11. Product Metrics

Metrik produk awal:

- jumlah registered user;
- jumlah guest prompt;
- jumlah chat user login;
- jumlah jawaban dengan citation valid;
- jumlah query yang ditolak karena sumber tidak cukup;
- jumlah dokumen berhasil di-ingest;
- jumlah dokumen gagal di-ingest;
- basic usage log untuk kontrol abuse dan debugging.

Catatan:

- Dashboard analytics kompleks tidak masuk MVP.
- Metrik ini cukup sebagai logging dasar dan monitoring awal.

---

## 12. Constraints

### 12.1 Product Constraints

- Public registration dibuka sehingga perlu abuse control.
- Guest hanya mendapat 1 prompt.
- Corpus MVP hanya DKI Jakarta tingkat provinsi.
- Search dokumen penuh hanya untuk user login.
- Admin UI harus tetap minimal.

### 12.2 Content Constraints

- Jawaban harus berbasis corpus.
- Semua klaim substantif harus memiliki citation.
- Tidak boleh membuat angka, periode, wilayah, satuan, atau definisi di luar sumber.
- Jika citation tidak tersedia, jawaban tidak memenuhi standar RINGKAS.

---

## 13. Risks

| Risk ID | Risiko Produk | Dampak | Mitigasi Produk |
|---|---|---|---|
| P-R01 | User terlalu percaya jawaban AI | Salah interpretasi statistik | Citation wajib dan refusal policy |
| P-R02 | Guest/public user abuse | Biaya/limit provider habis | Rate limit, quota, token cap |
| P-R03 | Search dokumen tidak cukup membantu | User sulit menemukan sumber | Metadata search dan keyword search |
| P-R04 | Admin UI melebar | Scope creep | Batasi hanya trigger/status/log |
| P-R05 | Corpus semua topik terlalu luas | Evaluasi dan UX noisy | Dataset evaluasi mencakup topik utama |
| P-R06 | Citation salah | Trust turun | Manual audit subset dan metadata halaman |

---

## 14. Open Questions / TBD

1. Detail UX chat page.
2. Detail UX citation hover/click.
3. Detail UX source panel.
4. Detail UX search dokumen.
5. Detail UX admin ingestion.
6. Email verification implementation.
7. Rate limit final untuk guest dan registered user.
8. Quota prompt final untuk user login.
9. Export jawaban PDF/Word: out-of-scope atau MVP Plus.
10. Exact product copy untuk refusal/partial answer.

---

## 15. Relationship to Other Documents

Dokumen lanjutan:

- `RINGKAS_SRD.md` untuk requirement sistem/software.
- `TECHNICAL_SPEC.md` untuk arsitektur implementasi.
- `TASKS.md` untuk backlog granular.
- `AGENTS.md` untuk aturan AI agent.
- `EVALUATION_PLAN.md` untuk detail evaluasi RAG.

