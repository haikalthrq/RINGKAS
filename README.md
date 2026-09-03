# RINGKAS
**National Generative Information Retrieval for Statistical Archives**  
*(Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik)*

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![.NET](https://img.shields.io/badge/.NET-10.0-purple.svg)](https://dotnet.microsoft.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16%20App%20Router-black.svg)](https://nextjs.org/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Qdrant](https://img.shields.io/badge/Vector%20DB-Qdrant-red.svg)](https://qdrant.tech/)

> **Ground statistical questions in official publications with exact page, table, and paragraph citations.**

---

## 📌 Overview

**RINGKAS** is an open-source, **citation-first** Retrieval-Augmented Generation (RAG) platform tailored for official publications from Statistics Indonesia (*Badan Pusat Statistik* / BPS), starting with the BPS DKI Jakarta regional corpus.

The greatest challenge of using generative AI on public statistical records is **hallucination**—models frequently fabricate figures, mix up time periods, confuse regions, or invent indicator definitions. RINGKAS prevents this through strict grounding constraints:

- **Mandatory Citations:** Every substantive claim must cite official BPS publications, providing the exact publication title, release year, page numbers, and original text excerpts.
- **Refusal on Insufficient Evidence:** If retrieved evidence does not support a clear, verifiable answer, the system explicitly refuses to guess instead of inventing data.
- **Direct Source Verification:** Users can inspect source references and navigate directly to official BPS document links.

---

## 🏛️ System Architecture

RINGKAS enforces a clean modular architecture separating the public web interface, domain backend, and internal RAG services:

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
                │    Internal RAG Hub    │
                ├────────────────────────┤
                │ • rag-query (Retrieval)│ ──► Qdrant Vector DB (Dense 1024-d)
                │ • rag-worker (Ingest & │ ──► PyMuPDF + Chunking Engine
                │   Cloudflare Embed)    │ ──► Local Storage /data/ringkas/pdfs
                └────────────────────────┘
```

### Core Components

| Component | Path | Technology | Role & Responsibility |
|---|---|---|---|
| **Frontend Web** | `apps/web` | Next.js 16, React, TypeScript | Presentation layer built with App Router. Features a mobile drawer navigation, instant bilingual (ID/EN) switching, citation cards, and an interactive chat workspace. |
| **Main API** | `apps/api` | ASP.NET Core (.NET 10), EF Core | The single public backend gateway. Manages authentication (Cookie + Google OAuth), user roles, quota enforcement, chat orchestration, citations, and admin ingestion endpoints. |
| **Vector Database** | `qdrant` | Qdrant | Stores and queries document chunk embeddings (1024-dimensional dense vectors via Cloudflare Workers AI `@cf/qwen/qwen3-embedding-0.6b`). |
| **Relational Database** | `postgres` | PostgreSQL 16 | Stores ASP.NET Identity users, chat sessions, message histories, document/chunk metadata, ingestion job queues, and audit logs. |
| **RAG Query Engine** | `services/rag-worker` (`rag-query`) | Python 3.12, FastAPI | Internal private HTTP service inside the Docker network for dense retrieval and chunk ranking from Qdrant. |
| **Ingestion Worker** | `services/rag-worker` | Python 3.12, PyMuPDF, `uv` | Downloads official BPS PDFs, extracts text page-by-page, performs recursive text chunking (500–800 tokens), and indexes embeddings. |

> **Security Boundary:** Next.js never accesses PostgreSQL or Qdrant directly. The Python services are strictly internal and only accessible by ASP.NET Core through internal bearer tokens.

---

## ✨ Key Features

1. **Evidence-First Citations:** Interactive source cards showing publication title, year, exact page numbers, and verified paragraph excerpts.
2. **Fully Responsive Mobile Experience:** Compact single-row navbar with a slide-over mobile drawer, touch-friendly tap targets, and generous spacing across all screen sizes.
3. **Bilingual Support (Indonesian & English):** Switch interface language on the fly with accurate statistical terminology.
4. **Multi-tier LLM Provider & Failover:**
   - **Primary:** `nvidia/nemotron-3-nano-30b-a3b`
   - **Secondary / Fallback:** `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
   - **Experimental:** `mistralai/mistral-small-4-119b-2603`
5. **Self-Service Admin Ingestion Pipeline:** Authorized admins can trigger document downloads and vector indexing by region, year range, and keyword directly via UI or API.

---

## 🚀 Quickstart Guide

### Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose
- [.NET 10 SDK](https://dotnet.microsoft.com/) with `dotnet-ef` tool
- [Python 3.12+](https://www.python.org/) with [uv](https://astral.sh/uv) (optional, for local worker testing)
- [Node.js 20+](https://nodejs.org/) (optional, for standalone frontend development)

### 1. Clone & Configure Environment
```bash
git clone https://github.com/haikalthrq/RINGKAS.git
cd RINGKAS

# Copy example environment configuration
cp .env.example .env
```

Open `.env` and fill in the required keys (never commit secrets or API tokens to Git):
- `DATABASE_URL` / `POSTGRES_*`
- `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`
- `NVIDIA_NIM_API_KEY`
- `BPS_API_KEY` (if querying the live BPS Web API)

### 2. Run Database Migrations
Apply EF Core migrations to prepare the PostgreSQL schema:
```bash
dotnet ef database update --project apps/api/Ringkas.Api.csproj --startup-project apps/api/Ringkas.Api.csproj
```

### 3. Launch with Docker Compose
```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
```

Verify service status:
```bash
docker compose --env-file .env -f infra/docker-compose.yml ps
```

Open your browser at:  
👉 **`http://localhost:3000`**

---

## 🔑 User Accounts & Admin Bootstrap

Public registration assigns the standard `user` role. Accessing the document ingestion dashboard requires the `admin` role.

### 1. Register a Local Account
Create an account via the web UI at `/register` or using curl:
```bash
curl -s -c admin.cookies -H "Content-Type: application/json" -d '{"email":"admin@ringkas.local","password":"Password123!"}' http://localhost:3000/api/auth/register
```

### 2. Promote Account to Admin (via PostgreSQL)
Execute this SQL statement directly on your PostgreSQL database:
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

Log in again after promotion so the session cookie includes the `admin` role claim.

---

## 📥 Ingesting BPS Publications

To index new BPS statistical publications:

1. Start the ingestion worker using the Compose profile:
   ```bash
   docker compose --env-file .env -f infra/docker-compose.yml --profile ingestion up -d rag-worker
   ```
2. Trigger an ingestion job via the Admin API (or navigate to `/admin` in the web UI):
   ```bash
   curl -s -b admin.cookies -H "Content-Type: application/json" -d '{"region":"DKI Jakarta","year_start":2023,"year_end":2025,"max_documents":1,"force_reprocess":false}' http://localhost:3000/api/admin/ingestion/jobs
   ```
3. The worker downloads the publication PDF, extracts text using PyMuPDF, chunks content, computes embeddings, and indexes vectors into Qdrant.

---

## 🧪 Testing & Verification

Run local verification suites:

```bash
# 1. Run ASP.NET Core API Unit Tests
dotnet test tests/api/Ringkas.Api.Tests.csproj

# 2. Run Python RAG Worker & Evaluation Tests
uv run --project services/rag-worker --extra test --frozen pytest services/rag-worker/tests/test_evaluation_dataset.py

# 3. Test Next.js Production Build
cd apps/web && npm run build
```

---

## 🌐 Production VPS Deployment

For production deployments on a VPS:

1. Use the production overlay `infra/docker-compose.production.yml`:
   ```bash
   docker compose --env-file .env.production -f infra/docker-compose.yml -f infra/docker-compose.production.yml up -d --build
   ```
2. The overlay closes public ports for PostgreSQL and Qdrant, and binds Next.js to loopback `127.0.0.1:${WEB_PORT}`.
3. Configure an external TLS reverse proxy (e.g., Nginx, Caddy) to terminate SSL and forward traffic to the Next.js port.
4. Schedule periodic backups using `scripts/backup/backup.sh`.

---

## ⚠️ Known Limitations

- **Text-First MVP:** Document processing relies on clean digital text layers via PyMuPDF. Scanned PDFs (image-only without OCR) are unsupported in this release.
- **Complex Tables:** Multi-span and nested table extraction is handled on a best-effort textual basis.
- **Corpus Scope:** The initial release focuses on publications from BPS Provinsi DKI Jakarta.

---

## 📄 Attribution & License

- Statistical publications and archives are sourced from [Badan Pusat Statistik (BPS) Republik Indonesia](https://www.bps.go.id/).
- Released under the [MIT License](LICENSE).
