# RINGKAS
**Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![.NET](https://img.shields.io/badge/.NET-10.0-purple.svg)](https://dotnet.microsoft.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16%20App%20Router-black.svg)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Qdrant](https://img.shields.io/badge/Vector%20DB-Qdrant-red.svg)](https://qdrant.tech/)

> **Rujuk data statistik langsung ke dokumen aslinya.**  
> *Ground statistical questions in official BPS publications with exact page, table, and paragraph citations.*

---

## 📌 Sekilas Tentang RINGKAS

**RINGKAS** adalah platform pencarian dan tanya-jawab cerdas berbasis **Citation-First RAG** (*Retrieval-Augmented Generation*) yang dirancang khusus untuk arsip publikasi **Badan Pusat Statistik (BPS)** (dimulai dari korpus BPS Provinsi DKI Jakarta).

Tantangan terbesar penggunaan AI generatif pada data publik adalah **halusinasi statistik**—model sering kali mengarang angka, memutarbalikkan periode, atau salah menyebutkan satuan. RINGKAS menyelesaikan masalah ini dengan prinsip ketat:

- **Wajib Sitasi:** Setiap klaim substantif harus menyertakan kartu sitasi dokumen resmi BPS (judul publikasi, tahun rilis, nomor halaman, dan cuplikan teks asli).
- **Anti-Spekulasi:** Jika bukti dokumen yang relevan tidak mencukupi (*insufficient evidence*), sistem secara eksplisit menolak berspekulasi alih-alih mengarang jawaban.
- **Tautan Verifikasi Langsung:** Pengguna dapat memverifikasi langsung halaman rujukan melalui pranala ke arsip resmi BPS.

---

## 🏛️ Arsitektur Sistem

RINGKAS menerapkan arsitektur modular yang memisahkan frontend publik, backend bisnis, dan engine pemrosesan RAG internal:

```text
                       ┌─────────────────────────┐
                       │    Next.js Frontend     │
                       │ (App Router, TS, Shell) │
                       └────────────┬────────────┘
                                    │ HTTP (Reverse Proxy / BFF)
                                    ▼
                       ┌─────────────────────────┐
                       │  ASP.NET Core Web API   │  ◄── Main Public Backend
                       │ (.NET 10, Auth, Domain) │      (Single Source of Truth)
                       └─────┬──────────────┬────┘
            Internal RPC /   │              │ PostgreSQL
        Token-Auth HTTP Calls│              ▼
                             │      ┌─────────────────────────┐
                             │      │  PostgreSQL 16          │
                             │      │  (Auth, Sessions, Logs, │
                             │      │   Document Metadata)    │
                             │      └─────────────────────────┘
                             ▼
                ┌────────────────────────┐
                │    RAG Internal Hub    │
                ├────────────────────────┤
                │ • rag-query (Retrieval)│ ──► Qdrant Vector DB (Dense 1024-d)
                │ • rag-worker (Ingest & │ ──► PyMuPDF + Chunking Engine
                │   Cloudflare Embed)    │ ──► Local Storage /data/ringkas/pdfs
                └────────────────────────┘
```

### Komponen Utama

| Komponen | Direktori | Teknologi | Peran & Tanggung Jawab |
|---|---|---|---|
| **Frontend Web** | `apps/web` | Next.js 16, React, TypeScript | Antarmuka pengguna responsif (desktop, tablet, HP) dengan hamburger drawer, perutean dwibahasa (ID/EN), pratinjau kartu sitasi, dan ruang riset interaktif. |
| **Main API** | `apps/api` | ASP.NET Core (.NET 10), EF Core | Satu-satunya gerbang backend publik. Mengelola otentikasi (Cookie + OAuth Google), peran pengguna, kontrol kuota, orkestrasi chat, sitasi, dan API ingestion. |
| **Vector Database** | `qdrant` | Qdrant | Penyimpanan dan pencarian dense vector chunk publikasi (dimensi 1024 via Cloudflare `@cf/qwen/qwen3-embedding-0.6b`). |
| **Relational Database** | `postgres` | PostgreSQL 16 | Penyimpanan akun ASP.NET Identity, sesi chat, pesan, metadata dokumen, status job ingestion, dan log audit. |
| **RAG Query Engine** | `services/rag-worker` (`rag-query`) | Python 3.12, FastAPI | Layanan privat internal untuk pencarian dense retrieval dan perankingan chunk teks dari Qdrant. |
| **Ingestion Worker** | `services/rag-worker` | Python 3.12, PyMuPDF, `uv` | Mengunduh PDF resmi BPS, parsing teks halaman per halaman, memecah chunk secara rekursif (500–800 token), dan mengindeks embedding. |

> **Catatan Keamanan:** Next.js tidak pernah mengakses database atau Qdrant secara langsung. Layanan Python bersifat internal dan hanya dapat diakses oleh ASP.NET Core melalui token internal.

---

## ✨ Fitur Unggulan

1. **Evidence-First Citations:** Setiap jawaban dilengkapi kartu sumber yang dapat diklik untuk melihat judul publikasi, tahun, halaman spesifik, dan kutipan paragraf sumbernya.
2. **100% Responsif & Ergonomis:** Tampilan optimal di semua resolusi (ponsel 360px, tablet 768px, hingga desktop lebar) dengan navigasi satu baris dan panel laci samping (*drawer menu*).
3. **Dukungan Dwibahasa (ID / EN):** Pengalihan bahasa instan dari header dengan penyesuaian terminologi statistik yang akurat.
4. **Multi-tier LLM Provider & Failover:**
   - **Primary:** `nvidia/nemotron-3-nano-30b-a3b`
   - **Secondary / Fallback:** `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
   - **Experimental:** `mistralai/mistral-small-4-119b-2603`
5. **Pipeline Ingestion Mandiri:** Panel admin terproteksi untuk memicu pengindeksan publikasi BPS baru berdasarkan tahun dan kata kunci.

---

## 🚀 Panduan Instalasi Lokal (Quickstart)

### Prasyarat
- [Docker](https://www.docker.com/) & Docker Compose
- [.NET 10 SDK](https://dotnet.microsoft.com/) dan alat `dotnet-ef`
- [Python 3.12+](https://www.python.org/) dan [uv](https://astral.sh/uv) (opsional, untuk menjalankan test worker)
- [Node.js 20+](https://nodejs.org/) (opsional, untuk pengembangan web lokal)

### 1. Klon Repositori & Persiapan Konfigurasi
```powershell
git clone https://github.com/haikalthrq/RINGKAS.git
cd RINGKAS

# Salin konfigurasi environment
Copy-Item .env.example .env
```

Buka berkas `.env` dan lengkapi konfigurasi utama (API Key tidak boleh dikomit ke Git):
- `DATABASE_URL` / `POSTGRES_*`
- `CLOUDFLARE_ACCOUNT_ID` dan `CLOUDFLARE_API_TOKEN`
- `NVIDIA_NIM_API_KEY`
- `BPS_API_KEY` (jika mengaktifkan sinkronisasi langsung dari portal BPS)

### 2. Jalankan Migrasi Database
Jalankan migrasi EF Core untuk menyiapkan skema tabel di PostgreSQL:
```powershell
dotnet ef database update --project apps/api/Ringkas.Api.csproj --startup-project apps/api/Ringkas.Api.csproj
```

### 3. Jalankan Aplikasi dengan Docker Compose
```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
```

Periksa apakah seluruh kontainer telah berjalan:
```powershell
docker compose --env-file .env -f infra/docker-compose.yml ps
```

Buka peramban Anda di:  
👉 **`http://localhost:3000`**

---

## 🔑 Pengelolaan Akun & Peran Admin

Secara bawaan, registrasi publik memberikan peran `user`. Peran `admin` diperlukan untuk mengakses panel dan API ingestion dokumen.

### 1. Daftarkan Akun Baru
Daftar melalui antarmuka web di `/register` atau via HTTP:
```powershell
curl.exe -s -c admin.cookies -H "Content-Type: application/json" -d '{"email":"admin@ringkas.local","password":"Password123!"}' http://localhost:3000/api/auth/register
```

### 2. Promosikan Akun Menjadi Admin (via PostgreSQL)
Jalankan query SQL berikut langsung di database:
```sql
BEGIN;
INSERT INTO "AspNetUserRoles" ("UserId", "RoleId")
SELECT u."Id", r."Id"
FROM "AspNetUsers" AS u
JOIN "AspNetRoles" AS r ON r."Name" = 'admin'
WHERE u."Email" = 'admin@ringkas.local'
ON CONFLICT DO NOTHING;
COMMIT;
```

Setelah dipromosikan, lakukan login ulang agar cookie sesi memuat klaim peran `admin`.

---

## 📥 Memicu Pipeline Ingestion Dokumen BPS

Untuk mengindeks dokumen publikasi BPS baru:

1. Jalankan worker ingestion di profil Compose:
   ```powershell
   docker compose --env-file .env -f infra/docker-compose.yml --profile ingestion up -d rag-worker
   ```
2. Kirim permintaan job melalui API Admin (atau buka menu `/admin` di web):
   ```powershell
   curl.exe -s -b admin.cookies -H "Content-Type: application/json" -d '{"region":"DKI Jakarta","year_start":2023,"year_end":2025,"max_documents":1,"force_reprocess":false}' http://localhost:3000/api/admin/ingestion/jobs
   ```
3. Worker akan otomatis mengunduh PDF, mengekstrak teks dengan PyMuPDF, memotong chunk, membuat embedding, dan menyimpan vektor ke Qdrant.

---

## 🧪 Pengujian & Verifikasi (Testing)

Untuk memastikan keandalan kode sebelum commit:

```powershell
# 1. Jalankan Unit Test Backend ASP.NET Core
dotnet test tests/api/Ringkas.Api.Tests.csproj

# 2. Jalankan Test Evaluasi RAG Worker & Dataset
uv run --project services/rag-worker --extra test --frozen pytest services/rag-worker/tests/test_evaluation_dataset.py

# 3. Jalankan Pengujian Build Next.js
cd apps/web
npm run build
```

---

## 🌐 Panduan Deployment Produksi (VPS)

Untuk implementasi di server VPS publik:

1. Gunakan file overlay produksi `infra/docker-compose.production.yml`:
   ```bash
   docker compose --env-file .env.production -f infra/docker-compose.yml -f infra/docker-compose.production.yml up -d --build
   ```
2. Overlay ini otomatis mengunci port database (PostgreSQL dan Qdrant) agar tidak terbuka ke publik dan hanya mengikat port web ke `127.0.0.1`.
3. Pasang reverse proxy terluar (seperti Nginx atau Caddy) dengan sertifikat SSL/TLS untuk meneruskan trafik domain ke aplikasi Next.js.
4. Lakukan pencadangan berkala menggunakan skrip di `scripts/backup/backup.sh`.

---

## ⚠️ Batasan Sistem (Known Limitations)

- **Fokus Teks Digital (Text-First):** Pemrosesan dokumen mengandalkan lapisan teks digital asli menggunakan PyMuPDF. Dokumen pindaian (*scanned PDF*) tanpa teks atau OCR belum didukung pada versi MVP ini.
- **Tabel Kompleks:** Ekstraksi data tabular bertingkat dilakukan dengan pendekatan terbaik (*best-effort*) berbasis teks.
- **Batasan Wilayah Awal:** Korpus fokus awal mencakup publikasi resmi BPS Provinsi DKI Jakarta.

---

## 📄 Atribusi & Lisensi

- Publikasi dan data statistik bersumber dari arsip resmi [Badan Pusat Statistik (BPS) Republik Indonesia](https://www.bps.go.id/).
- Dikembangkan sebagai inisiatif aksesibilitas data terbuka dan penelitian sains data terverifikasi.
