# RINGKAS Technical Specification

**Project:** RINGKAS — Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik  
**Document type:** Technical Specification  
**Version:** 1.0  
**Status:** Draft Accepted for MVP Planning  
**Generated date:** 2026-07-08  
**Primary source:** RINGKAS Project Brief, PRD, SRD, and Technical Elicitation Canvas v2.1

---

## 1. Purpose

Dokumen ini menjelaskan spesifikasi teknis MVP RINGKAS. Fokus dokumen ini adalah menjawab **bagaimana sistem dibangun**, bukan mendefinisikan ulang scope produk.

Dokumen ini menjadi acuan untuk:

1. AI agent supervisor/orchestrator.
2. Coding agent/sub-agent.
3. Developer/System Maintainer.
4. Penyusunan `TASKS.md`, `AGENTS.md`, dan implementation backlog.
5. Evaluasi teknis pipeline RAG.

---

## 2. Technical Summary

RINGKAS MVP dibangun sebagai aplikasi web RAG berbasis dokumen publikasi BPS DKI Jakarta. Backend utama menggunakan **ASP.NET Core**, sedangkan proses RAG berat dijalankan oleh **Python RAG Worker** internal.

Keputusan arsitektur inti:

| Area | Keputusan MVP |
|---|---|
| Main backend | ASP.NET Core |
| Frontend | React + Vite |
| RAG processing | Python RAG Worker internal |
| Database | PostgreSQL |
| Vector database | Qdrant |
| Deployment | Satu VPS |
| Containerization | Docker Compose |
| PDF storage | Local folder VPS: `/data/ringkas/pdfs` |
| Parser | PyMuPDF via Python worker |
| OCR | Tidak masuk MVP |
| Chunking | LangChain `RecursiveCharacterTextSplitter` |
| Retrieval | Qdrant dense + sparse vector retrieval |
| Fusion | Reciprocal Rank Fusion / RRF |
| Generation primary | NVIDIA NIM |
| Generation fallback | Cloudflare Workers AI |
| Embedding provider | NVIDIA NIM only |
| Auth | ASP.NET Core Identity + Google OAuth via backend |
| Admin UI | Sederhana: trigger ingestion, status job, log ringkas |

---

## 3. Scope Boundaries

### 3.1 In Scope MVP

- Web application dengan frontend React + Vite.
- ASP.NET Core sebagai public-facing backend/API.
- Python RAG Worker sebagai internal processing service.
- Ingestion publikasi BPS DKI Jakarta 5 tahun terakhir.
- Corpus maksimal 300 publikasi untuk MVP.
- PDF digital text-layer parsing dengan PyMuPDF.
- Cleaning, chunking, embedding, dan indexing ke Qdrant.
- Hybrid retrieval menggunakan dense + sparse vector.
- Chat/Q&A berbasis dokumen dengan citation.
- Document search berdasarkan metadata/kata kunci.
- Guest trial 1 prompt dengan citation.
- User login/register.
- Google OAuth.
- Chat history untuk user login.
- Admin/System Maintainer role.
- Admin UI sederhana untuk ingestion.
- Evaluation harness automated-first menggunakan RAGAS/LLM-as-judge + manual audit 20%.

### 3.2 Out of Scope MVP

- OCR pipeline.
- PDF scan support.
- Docling sebagai parser production.
- Vision/multimodal understanding untuk grafik/gambar.
- Fine-tuning LLM.
- Training embedding model sendiri.
- Public API pihak ketiga.
- Upload dokumen oleh user.
- Admin dashboard kompleks.
- Audit log kompleks.
- Dashboard analytics penggunaan.
- Native mobile app.
- Multi-language support formal termasuk bahasa daerah.
- Query langsung ke database statistik BPS real-time.
- Validasi angka terhadap sumber eksternal di luar corpus.

---

## 4. High-Level Architecture

```text
+---------------------------+
|        React + Vite       |
|  Web UI: chat, search,    |
|  auth, admin ingestion    |
+-------------+-------------+
              |
              | HTTPS / REST API
              v
+---------------------------+
|       ASP.NET Core API    |
| Auth, roles, chat API,    |
| document search, admin,   |
| rate limit, app logging   |
+------+------+-------------+
       |      |
       |      | job table polling / status updates
       |      v
       |  +-----------------------+
       |  | Python RAG Worker     |
       |  | ingestion, download,  |
       |  | PyMuPDF parsing,      |
       |  | cleaning, chunking,   |
       |  | embedding, Qdrant,    |
       |  | evaluation harness    |
       |  +----------+------------+
       |             |
       v             v
+-------------+   +----------------+
| PostgreSQL  |   | Qdrant         |
| metadata,   |   | dense+sparse   |
| users, jobs,|   | vectors, chunk |
| chat, logs  |   | payloads       |
+-------------+   +----------------+
       |
       v
+---------------------------+
| Local PDF Storage         |
| /data/ringkas/pdfs        |
+---------------------------+
```

---

## 5. Service Responsibilities

### 5.1 ASP.NET Core API

ASP.NET Core adalah **backend utama** dan satu-satunya public-facing backend untuk MVP.

Tanggung jawab:

- Email-password auth.
- Google OAuth via backend.
- Role management: `guest`, `user`, `admin/system_maintainer`.
- Chat/Q&A API.
- Chat history API.
- Document search API.
- Citation/source API.
- Admin ingestion trigger API.
- Admin ingestion status API.
- Rate limit dan quota enforcement.
- Application logging.
- Usage logging untuk kontrol biaya/rate limit.
- Membuat ingestion job record di PostgreSQL.
- Membaca status/log ringkas ingestion dari PostgreSQL.

ASP.NET Core **tidak dipaksa** menjalankan PDF parsing, chunking, RAGAS, atau processing berat lain secara langsung.

### 5.2 Python RAG Worker

Python RAG Worker adalah service internal, bukan public API.

Tanggung jawab:

- Polling ingestion job dari PostgreSQL.
- Mengambil metadata publikasi dari API BPS.
- Filter publikasi DKI Jakarta 5 tahun terakhir.
- Download PDF ke local storage.
- Parsing PDF digital text-layer menggunakan PyMuPDF.
- Menandai PDF tanpa text layer sebagai `unsupported_or_extraction_failed`.
- Cleaning text.
- Chunking dengan LangChain `RecursiveCharacterTextSplitter`.
- Membuat embedding menggunakan NVIDIA NIM.
- Menyimpan vector dan payload ke Qdrant.
- Menyimpan metadata dokumen/chunk ke PostgreSQL.
- Menjalankan evaluation harness.
- Menulis job status dan log ringkas ke PostgreSQL.

Python worker tidak boleh terekspos ke public internet.

---

## 6. Repository Structure

Monorepo modular digunakan agar AI agent dan developer mudah menjaga konteks.

```text
ringkas/
  apps/
    web/                    # React + Vite frontend
    api/                    # ASP.NET Core backend API
  services/
    rag-worker/             # Python ingestion/RAG/evaluation worker
  infra/
    docker-compose.yml
    caddy/                  # optional reverse proxy config
    nginx/                  # optional if Nginx selected later
    postgres/
    qdrant/
  docs/
    PROJECT_BRIEF.md
    PRD.md
    SRD.md
    TECHNICAL_SPEC.md
    API_CONTRACT.md         # future
    EVALUATION_PLAN.md      # future
  scripts/
    dev/
    ingestion/
    backup/
  tests/
    api/
    worker/
    e2e/
```

Rules:

- Frontend, API, worker, infra, dan docs harus dipisah jelas.
- Shared API contracts disimpan di `docs/` atau `contracts/` jika nanti dibutuhkan.
- Python worker tidak boleh mencampur logic UI/backend auth.
- ASP.NET backend tidak boleh diam-diam mengaktifkan OCR atau parser non-MVP.

---

## 7. Deployment Specification

### 7.1 Target Deployment

MVP menggunakan satu VPS untuk:

- ASP.NET Core API.
- React + Vite frontend.
- PostgreSQL.
- Qdrant.
- Python RAG Worker.
- Local PDF storage.

### 7.2 Containerization

Docker Compose digunakan untuk MVP.

Services minimal:

```text
postgres
qdrant
rag-worker
api
web
reverse-proxy    # optional but recommended
```

Catatan:

- PostgreSQL dan Qdrant wajib container jika keputusan container tetap dipakai.
- Python RAG Worker direkomendasikan container untuk dependency isolation.
- ASP.NET API dan frontend boleh container juga untuk reproducibility.
- Untuk debugging lokal, API/frontend boleh dijalankan langsung tanpa container, tetapi deployment spec tetap berbasis Docker Compose.

### 7.3 Storage Paths

Local PDF storage:

```text
/data/ringkas/pdfs
```

Suggested persistent paths:

```text
/data/ringkas/pdfs
/data/ringkas/postgres
/data/ringkas/qdrant
/data/ringkas/logs
/data/ringkas/backups
```

### 7.4 Backup Requirements

Backup wajib direncanakan untuk:

- PostgreSQL database.
- Qdrant volume/snapshot.
- PDF folder.
- `.env` template tanpa secrets.
- Ingestion job logs jika disimpan di file.

Backup frequency MVP: TBD.

### 7.5 Domain and HTTPS

Status: TBD.

Options:

- Caddy for automatic HTTPS.
- Nginx + Certbot.
- Temporary subdomain during MVP.

Technical Spec recommendation: use Caddy if no strong preference.

---

## 8. Environment Configuration

Required environment variables should be split by component.

### 8.1 ASP.NET API

```env
ASPNETCORE_ENVIRONMENT=Development
DATABASE_URL=postgresql://...
JWT_SECRET=TBD
AUTH_COOKIE_DOMAIN=TBD
GOOGLE_CLIENT_ID=TBD
GOOGLE_CLIENT_SECRET=TBD
NVIDIA_NIM_API_KEY=TBD
CLOUDFLARE_ACCOUNT_ID=TBD
CLOUDFLARE_WORKERS_AI_TOKEN=TBD
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=TBD_OPTIONAL
PDF_STORAGE_PATH=/data/ringkas/pdfs
GUEST_PROMPT_QUOTA=1
REGISTERED_DAILY_QUOTA=TBD
```

### 8.2 Python RAG Worker

```env
DATABASE_URL=postgresql://...
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=TBD_OPTIONAL
NVIDIA_NIM_API_KEY=TBD
PDF_STORAGE_PATH=/data/ringkas/pdfs
BPS_API_KEY=TBD_IF_REQUIRED
BPS_BASE_URL=TBD
INGESTION_POLL_INTERVAL_SECONDS=10
CHUNK_SIZE_MIN=500
CHUNK_SIZE_MAX=800
CHUNK_OVERLAP_PERCENT=20
OCR_ENABLED=false
```

Do not commit secrets.

---

## 9. Data Storage Design

### 9.1 PostgreSQL Responsibilities

PostgreSQL stores:

- User accounts.
- Auth/role data.
- Chat sessions and messages.
- Document metadata.
- Chunk metadata mirror/reference.
- Ingestion jobs.
- Ingestion logs.
- Usage logs.
- Evaluation dataset and results if needed.

### 9.2 Initial Tables

#### `users`

Managed by ASP.NET Core Identity. Exact schema may follow Identity defaults.

Additional profile fields may include:

| Field | Type | Notes |
|---|---|---|
| id | uuid/text | Identity user id |
| display_name | text | nullable |
| role | text | user/admin, or via Identity roles |
| created_at | timestamptz | required |
| last_login_at | timestamptz | nullable |

#### `documents`

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | uuid | yes | internal document id |
| title | text | yes | publication title |
| publication_year | int | yes | year |
| release_date | date | if available | from API if available |
| region | text | yes | DKI Jakarta |
| region_level | text | yes | province |
| topic | text | if available | subject/category |
| catalog_number | text | if available | BPS metadata |
| publication_number | text | if available | BPS metadata |
| source_page_url | text | yes | BPS page or identifier |
| pdf_url | text | if available | source PDF URL |
| local_pdf_path | text | if downloaded | `/data/ringkas/pdfs/...` |
| language | text | if available | likely Indonesian |
| page_count | int | derived | from parser |
| ingestion_status | text | yes | pending/downloaded/parsed/indexed/failed |
| checksum | text | yes | deduplication |
| created_at | timestamptz | yes | system timestamp |
| ingested_at | timestamptz | nullable | when processed |
| error_message | text | nullable | last error |

#### `chunks`

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | uuid | yes | internal chunk id |
| document_id | uuid | yes | FK documents |
| chunk_index | int | yes | order in document |
| text | text | yes | chunk text or normalized text |
| page_start | int | nullable | citation |
| page_end | int | nullable | citation |
| section_heading | text | nullable | if detected |
| extraction_method | text | yes | `text_layer` for MVP |
| low_structure_confidence | bool | yes | true for uncertain tables/layout |
| source_url | text | yes | BPS source or PDF URL |
| qdrant_point_id | text | yes | vector point id |
| created_at | timestamptz | yes | timestamp |

#### `ingestion_jobs`

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | uuid | yes | job id |
| requested_by_user_id | text/uuid | yes | admin user id |
| status | text | yes | queued/running/completed/failed/cancelled |
| scope_region | text | yes | DKI Jakarta |
| scope_year_start | int | yes | derived from 5-year window |
| scope_year_end | int | yes | current year or config |
| max_documents | int | yes | 300 |
| started_at | timestamptz | nullable | job start |
| completed_at | timestamptz | nullable | job end |
| created_at | timestamptz | yes | timestamp |
| error_summary | text | nullable | high-level error |

#### `ingestion_logs`

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | uuid | yes | log id |
| job_id | uuid | yes | FK ingestion_jobs |
| document_id | uuid | nullable | FK documents |
| level | text | yes | info/warn/error |
| message | text | yes | log message |
| metadata_json | jsonb | nullable | structured details |
| created_at | timestamptz | yes | timestamp |

#### `chat_sessions`

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | uuid | yes | session id |
| user_id | text/uuid | yes | authenticated user |
| title | text | nullable | generated or first message |
| created_at | timestamptz | yes | timestamp |
| updated_at | timestamptz | yes | timestamp |

#### `chat_messages`

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | uuid | yes | message id |
| session_id | uuid | yes | FK chat_sessions |
| role | text | yes | user/assistant/system |
| content | text | yes | message body |
| citations_json | jsonb | nullable | cited chunks/docs |
| provider | text | nullable | NVIDIA/Cloudflare |
| created_at | timestamptz | yes | timestamp |

#### `usage_logs`

| Field | Type | Required | Notes |
|---|---|---:|---|
| id | uuid | yes | log id |
| user_id | text/uuid | nullable | guest can be null |
| ip_hash | text | nullable | privacy-aware IP hash |
| action | text | yes | chat/search/ingest/etc |
| token_input | int | nullable | if available |
| token_output | int | nullable | if available |
| provider | text | nullable | generation/embedding provider |
| created_at | timestamptz | yes | timestamp |

---

## 10. Qdrant Design

### 10.1 Collection

Suggested collection name:

```text
ringkas_chunks_v1
```

### 10.2 Vector Types

MVP uses hybrid retrieval:

- Dense vector from NVIDIA NIM embedding model.
- Sparse vector for lexical retrieval.

Exact sparse method: TBD.

Important rule:

> Do not claim BM25 implementation unless an actual BM25 engine or BM25-equivalent scoring is implemented.

### 10.3 Payload Metadata

Each Qdrant point should include:

```json
{
  "document_id": "uuid",
  "chunk_id": "uuid",
  "title": "string",
  "publication_year": 2026,
  "region": "DKI Jakarta",
  "region_level": "province",
  "topic": "string_or_null",
  "page_start": 1,
  "page_end": 2,
  "section_heading": "string_or_null",
  "chunk_index": 0,
  "extraction_method": "text_layer",
  "low_structure_confidence": false,
  "source_url": "https://...",
  "pdf_url": "https://..."
}
```

---

## 11. Authentication and Roles

### 11.1 Auth

MVP auth:

- ASP.NET Core Identity for email-password.
- Google OAuth via ASP.NET backend.
- Session/JWT strategy: TBD in implementation.

Recommended for MVP:

- If frontend and API are served under same domain: secure cookie/session auth.
- If frontend and API are separated by domain/subdomain: JWT access token + refresh token via secure HTTP-only cookie may be considered.

### 11.2 Roles

| Role | Capabilities |
|---|---|
| guest | 1 prompt trial, citation visible, no chat history, no full document search |
| user | chat, citation, search documents, chat history |
| admin/system_maintainer | user capabilities + ingestion trigger/status/log admin UI |

Admin restrictions:

- Admin UI does not allow user document upload.
- Admin UI does not include dashboard analytics complex.
- Admin UI does not include full document management such as mass edit/delete/reprocess detail.

---

## 12. API Endpoint Specification

Endpoint naming is preliminary and can be refined during implementation.

### 12.1 Auth Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | public | Register email-password user |
| POST | `/api/auth/login` | public | Login |
| POST | `/api/auth/logout` | user | Logout |
| GET | `/api/auth/me` | user | Current user profile/session |
| GET | `/api/auth/google` | public | Start Google OAuth |
| GET | `/api/auth/google/callback` | public | Google OAuth callback |

### 12.2 User/Profile Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/users/me` | user | Get profile |
| PATCH | `/api/users/me` | user | Update basic profile, if needed |

### 12.3 Chat/Q&A Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/chat` | guest/user | Ask question |
| GET | `/api/chat/sessions` | user | List chat sessions |
| GET | `/api/chat/sessions/{id}` | user | Read chat session |
| DELETE | `/api/chat/sessions/{id}` | user | Delete own chat session, optional |

Chat request minimal:

```json
{
  "message": "string",
  "session_id": "uuid_or_null"
}
```

Chat response minimal:

```json
{
  "answer": "string",
  "citations": [
    {
      "document_id": "uuid",
      "chunk_id": "uuid",
      "title": "string",
      "year": 2026,
      "region": "DKI Jakarta",
      "page_start": 1,
      "page_end": 2,
      "source_url": "https://...",
      "snippet": "string"
    }
  ],
  "source_sufficiency": "sufficient|partial|insufficient",
  "provider": "nvidia_nim|cloudflare_workers_ai"
}
```

### 12.4 Document Search Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/documents/search` | user | Search documents by title/year/topic/keyword |
| GET | `/api/documents/{id}` | user | Document metadata detail |

Search query params:

```text
q=keyword
year=2024
topic=poverty
page=1
page_size=20
```

### 12.5 Citation/Source Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/sources/chunks/{chunkId}` | user | Retrieve citation chunk/snippet |
| GET | `/api/sources/documents/{documentId}` | user | Retrieve document source metadata |

### 12.6 Admin Ingestion Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/admin/ingestion/jobs` | admin | Create ingestion job |
| GET | `/api/admin/ingestion/jobs` | admin | List ingestion jobs |
| GET | `/api/admin/ingestion/jobs/{id}` | admin | Get job status |
| GET | `/api/admin/ingestion/jobs/{id}/logs` | admin | Get job logs |

Admin job creation request:

```json
{
  "region": "DKI Jakarta",
  "year_start": 2022,
  "year_end": 2026,
  "max_documents": 300,
  "force_reprocess": false
}
```

### 12.7 Health Check

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | public/internal | API health |
| GET | `/api/health/dependencies` | admin/internal | PostgreSQL/Qdrant/provider status |

---

## 13. Ingestion Job Flow

### 13.1 Trigger Flow

```text
Admin UI
  -> ASP.NET Admin API
    -> create ingestion_jobs row: queued
      -> Python worker polls job
        -> job status: running
        -> API BPS metadata retrieval
        -> filter corpus scope
        -> download PDFs
        -> parse PDFs
        -> clean/chunk
        -> embed
        -> index Qdrant
        -> update PostgreSQL document/chunk metadata
        -> job status: completed or failed
```

### 13.2 Job Status

Allowed statuses:

```text
queued
running
completed
failed
cancelled
```

### 13.3 Document Processing Status

Allowed document statuses:

```text
metadata_fetched
downloaded
parsed
chunked
embedded
indexed
failed
unsupported_or_extraction_failed
```

### 13.4 Failure Handling

- Retry download/parsing/embedding several times. Exact retry count: TBD.
- If a document fails, mark document as `failed` or `unsupported_or_extraction_failed`.
- Continue processing other documents.
- Log error in `ingestion_logs`.
- Do not fail the entire job because of one document unless systemic failure occurs.

---

## 14. PDF Parsing Specification

### 14.1 Parser

Parser MVP:

- PyMuPDF in Python RAG Worker.
- Text-layer extraction only.
- OCR disabled.
- Parser interface must be created so parser can be replaced or compared later.
- Docling is future plan / experimental candidate, not production MVP parser.

### 14.2 Unsupported PDFs

If a PDF has no usable text layer:

- Mark as `unsupported_or_extraction_failed`.
- Do not run OCR.
- Log reason.
- Continue other documents.

### 14.3 Extraction Metadata

Each chunk must store:

```text
extraction_method = text_layer
```

If layout/table structure is uncertain:

```text
low_structure_confidence = true
```

---

## 15. Text Cleaning Specification

Cleaning MVP:

- Remove repeated header/footer where confidently detected.
- Normalize spaces and newlines.
- Merge hyphenated words cautiously.
- Remove disruptive page numbers where confidently detected.
- Preserve detected headings/sections.
- Preserve page information for citation.
- Avoid aggressive cleaning that may remove or alter numbers, units, regions, periods, indicator names, or definitions.

Do not perform semantic rewriting during cleaning.

---

## 16. Table Handling Specification

MVP rules:

- Simple tables may be extracted as text.
- Simple tables may be converted to markdown table if reliable.
- Complex tables are best-effort only.
- Complex tables are not prioritized as primary retrieval source.
- If table structure is damaged, preserve raw text with `low_structure_confidence = true`.
- Do not claim accurate extraction of complex tables without evaluation.

---

## 17. Chunking Specification

### 17.1 Strategy

MVP chunking:

- Recursive character/text splitting.
- Implemented using LangChain `RecursiveCharacterTextSplitter` in Python worker.
- Future fallback: custom recursive splitter if LangChain dependency is too heavy.

### 17.2 Initial Parameters

| Parameter | Value |
|---|---|
| Chunk size | 500–800 tokens |
| Overlap | 20% |
| Split awareness | page/section metadata preserved where available |

Exact tokenization method: TBD.

### 17.3 Required Chunk Metadata

Each chunk must include:

- `document_id`
- `chunk_id`
- `title`
- `publication_year`
- `region`
- `region_level`
- `page_start`
- `page_end`
- `section_heading` if available
- `chunk_index`
- `extraction_method = text_layer`
- `low_structure_confidence`
- `source_url`
- `pdf_url` if available

---

## 18. Embedding and Indexing Specification

### 18.1 Embedding Provider

- Provider: NVIDIA NIM.
- Model name: TBD after checking availability in account.
- No embedding fallback.

Reason:

> Embedding fallback is not allowed automatically because different embedding models may produce incompatible dimensions/vector spaces.

### 18.2 Indexing

Python worker writes:

- Document metadata to PostgreSQL.
- Chunk metadata to PostgreSQL.
- Dense and sparse vectors to Qdrant.
- Qdrant payload should contain citation metadata.

### 18.3 Re-indexing Policy

If embedding model changes:

- Create a new Qdrant collection version.
- Re-embed all chunks.
- Do not mix embeddings from different models in the same vector space unless explicitly designed.

---

## 19. Retrieval Specification

### 19.1 Retrieval Type

MVP retrieval:

- Qdrant dense vector retrieval.
- Qdrant sparse vector retrieval.
- Fusion using RRF.

### 19.2 Candidate Counts

Initial candidate retrieval:

```text
dense_top_k = 20
sparse_top_k = 20
```

Final chunks sent to generation:

```text
final_top_k = 10
```

Note:

- Top-10 is accepted for MVP but may be optimized after evaluation.
- Top-10 may increase prompt token usage and noise.

### 19.3 Metadata Filtering

Default:

- No explicit metadata filter.
- Region is implicitly DKI Jakarta because MVP corpus is DKI Jakarta only.

Conditional filter behavior:

- If user mentions year, system may apply year filter.
- If user mentions topic/subcategory, system may apply topic filter if metadata exists.
- If user mentions document title, system may prioritize that document.
- Filters must not be too strict.
- Filter behavior must be evaluated after retrieval baseline.

### 19.4 Retrieval Sufficiency Rule

No fixed numeric threshold in MVP initial release.

However, the system must still have a sufficiency rule:

- There must be at least one relevant chunk that can be cited.
- If retrieved chunks are weak/unclear, answer must be partial with explicit limitation or refuse substantive answer.
- No claim that answer is correct solely because retrieval score is high.
- Numeric thresholds are determined after baseline evaluation.

---

## 20. Generation Specification

### 20.1 Provider Policy

| Role | Provider |
|---|---|
| Primary generation | NVIDIA NIM |
| Fallback generation | Cloudflare Workers AI |
| Experimental only | OpenCode Zen / DeepSeek V4 Flash Free |

Model names: TBD after availability check.

### 20.2 Prompt Rules

The generation prompt must enforce:

- Answer only based on provided chunks.
- Do not invent numbers, periods, regions, units, definitions, or methodology.
- If sources are insufficient, state limitation or refuse substantive answer.
- Every substantive claim must have citation.
- Do not infer trends/causality unless explicitly supported by source.
- Do not present retrieval score as answer accuracy.

### 20.3 Answer Language

Default behavior:

- Follow user question language.
- If unclear, use Bahasa Indonesia.

### 20.4 Answer Format

Adaptive format:

- Default: direct concise answer with citation.
- Bullet points if multiple points.
- Table only if source supports structured comparison.
- Summary + detail if requested.
- Do not force every answer to use all formats.

### 20.5 Citation Placement

- Citation inline or at end of paragraph/claim.
- Source panel may show document metadata and snippet.
- Snippet can be shown on hover/click in UI.

---

## 21. Citation Policy

Citation metadata shown to user:

- Document title.
- Publication year.
- Region.
- Page number if extracted.
- Source URL or BPS document/page URL.
- Snippet/potongan teks sumber via hover/click.

Rules:

- All substantive answers require citation.
- If citation is unavailable, answer does not meet RINGKAS standard.
- If source is insufficient, system must not answer substantively.
- Closest chunks may be shown without claiming certainty.
- Do not expose raw retrieval scores to general users.
- Retrieval/generation scores are developer/evaluation only.

---

## 22. Frontend Specification

### 22.1 Framework

Frontend MVP:

- React + Vite.

### 22.2 Main Pages

| Page | Auth | Description |
|---|---|---|
| Home/Landing | public | Intro + guest prompt |
| Login/Register | public | Email-password and Google OAuth |
| Chat | guest/user | Ask questions and view answers/citations |
| Chat History | user | List and open previous chats |
| Document Search | user | Search documents by metadata/keyword |
| Admin Ingestion | admin | Trigger ingestion, status, log ringkas |

### 22.3 Admin UI Boundary

Admin UI MVP only includes:

- Trigger ingestion job.
- View job status.
- View short logs.

Admin UI must not include:

- User document upload.
- Full document management.
- Mass edit/delete/reprocess detail.
- Complex analytics dashboard.

---

## 23. Rate Limit and Quota

### 23.1 MVP Rules

- Guest: 1 prompt.
- Registered user: daily quota TBD.
- Rate limit per IP.
- Rate limit per user.
- Admin not subject to normal chat quota.
- Admin still subject to abuse protection for sensitive endpoints.
- Final quota determined after provider limit estimation.

### 23.2 Abuse Control

Required:

- Email verification: recommended.
- Rate limit on auth endpoints.
- Rate limit on chat endpoint.
- Rate limit on admin ingestion endpoint.
- Basic usage logging.
- Token/output length limit: TBD.

---

## 24. Logging and Monitoring

### 24.1 Required Logs

- Application log.
- Ingestion job log.
- Worker log.
- Retrieval debug log for developer.
- Error log.
- Usage log for cost/rate-limit tracking.

### 24.2 Log Visibility

General users:

- No logs.

Admin/System Maintainer:

- Ingestion status.
- Short ingestion logs.
- Failed document count.
- Error summary.

Developer:

- Full logs via server/container logs.
- Retrieval debug logs if enabled.

---

## 25. Evaluation Harness Specification

### 25.1 Evaluation Approach

RINGKAS uses automated-first evaluation:

- RAGAS as automated evaluation baseline.
- LLM-as-judge as helper.
- Manual evaluation minimized but not removed.

### 25.2 Dataset

Initial evaluation dataset:

- 100 questions.
- Generated with LLM assistance.
- Manually verified before use.
- Evidence chunks or ground truth source marked from BPS documents.
- Covers main topics in DKI Jakarta corpus.
- Question types include: definitions, numbers, periods, region, methodology, and document search.

### 25.3 Manual Audit

Manual audit:

- 20% of initial evaluation dataset.
- With 100 questions, manual audit = 20 questions.
- Checks citation accuracy.
- Checks correctness of numbers, period, region, unit, and definitions.

Operational recommendation:

- Cases that fail or look suspicious in automated evaluation should be prioritized for manual review if possible.

### 25.4 Evaluation Claims

- Evaluation result is baseline MVP only.
- Do not claim system is fully accurate across all BPS documents.
- Final minimum metrics are determined after baseline experiment.
- If many citation/number errors are found, pipeline must be fixed before being considered acceptable.

---

## 26. Error Handling

### 26.1 API Errors

API must return structured errors:

```json
{
  "error_code": "string",
  "message": "string",
  "details": {}
}
```

Common error codes:

```text
AUTH_REQUIRED
FORBIDDEN
RATE_LIMITED
QUOTA_EXCEEDED
SOURCE_INSUFFICIENT
PROVIDER_UNAVAILABLE
INGESTION_JOB_FAILED
DOCUMENT_NOT_FOUND
VALIDATION_ERROR
INTERNAL_ERROR
```

### 26.2 Worker Errors

Worker must log:

- job id;
- document id if available;
- step name;
- error message;
- retry count;
- timestamp.

Worker must not crash the full job for a single failed PDF.

---

## 27. Security Requirements

- Admin endpoints require `admin/system_maintainer` role.
- Python worker is internal-only and not exposed publicly.
- Secrets stored only in environment variables or secret manager.
- No API keys committed to repository.
- Basic rate limit required for public endpoints.
- Guest prompt limited to 1.
- Admin sensitive endpoints still require abuse protection.
- Logs must avoid storing raw secrets or sensitive tokens.
- User data should not be exposed in retrieval logs unless necessary for debugging.

---

## 28. Testing Requirements

### 28.1 Backend API Tests

- Auth registration/login.
- Google OAuth callback behavior: TBD / integration test later.
- Role authorization.
- Chat endpoint with mocked retrieval/generation.
- Document search.
- Admin ingestion job creation.
- Rate limit behavior.

### 28.2 Worker Tests

- BPS metadata fetch mock.
- PDF download mock.
- PyMuPDF parsing on sample PDF.
- No-text-layer PDF marked unsupported.
- Cleaning preserves numbers/units.
- Chunking preserves metadata.
- Qdrant indexing mock/integration.
- Job status update.

### 28.3 Retrieval Tests

- Dense retrieval returns expected chunk for simple query.
- Sparse retrieval returns exact-match terms.
- RRF fusion works with dense + sparse candidates.
- Metadata filter behavior for year/topic/title.

### 28.4 Generation Tests

- Answer includes citation.
- Refuses answer if source insufficient.
- Does not invent number/period/region/unit.
- Handles partial source with limitation statement.

---

## 29. Implementation Sequence

Recommended implementation order:

1. Setup monorepo.
2. Setup Docker Compose for PostgreSQL and Qdrant.
3. Scaffold ASP.NET Core API.
4. Scaffold React + Vite frontend.
5. Scaffold Python RAG Worker.
6. Implement PostgreSQL schema and migrations.
7. Implement ingestion job table and admin trigger endpoint.
8. Implement worker polling and job status update.
9. Implement BPS metadata fetch and PDF download.
10. Implement PyMuPDF parser.
11. Implement cleaning and chunking.
12. Implement embedding and Qdrant indexing.
13. Implement hybrid retrieval and RRF.
14. Implement citation mechanism.
15. Implement generation pipeline with NVIDIA NIM.
16. Implement Cloudflare Workers AI fallback.
17. Implement chat API and chat UI.
18. Implement document search.
19. Implement auth and roles.
20. Implement admin UI simple.
21. Implement evaluation harness.
22. Implement logging, quota, rate limit.
23. Run baseline evaluation.
24. Fix retrieval/citation/answer errors.

Note:

> Evaluation harness should be implemented before the UI is considered complete, so RAG quality can be tested early.

---

## 30. Open Technical TBD

| Item | Status | Notes |
|---|---|---|
| Domain and HTTPS | TBD | Caddy recommended if no preference |
| NVIDIA NIM generation model | TBD | choose after account availability check |
| NVIDIA NIM embedding model | TBD | must be locked before indexing |
| Cloudflare Workers AI fallback model | TBD | fallback only |
| Registered user daily quota | TBD | after provider limit estimation |
| Session vs JWT | TBD | depends on deployment/domain setup |
| Sparse vector method in Qdrant | TBD | do not claim BM25 unless implemented |
| Retry count for ingestion failures | TBD | recommend 3 initial retries |
| Token/output length limit | TBD | needed for cost control |
| Backup frequency | TBD | must be decided before deployment |

---

## 31. Non-Negotiable Constraints for Agents

AI agents working on RINGKAS must obey:

1. ASP.NET Core is the main backend.
2. Python RAG Worker is internal processing service, not public backend.
3. OCR must not be implemented in MVP.
4. Docling must not be used as production parser in MVP.
5. PyMuPDF is the MVP parser.
6. Embedding provider is NVIDIA NIM only.
7. Do not add embedding fallback automatically.
8. All substantive answers require citation.
9. Do not expose retrieval score as answer accuracy.
10. Do not add user document upload.
11. Do not expand admin UI into full document management dashboard.
12. Do not add dashboard analytics complex.
13. Do not add public API for third parties.
14. Keep implementation modular.
15. Update docs when changing architecture or scope.

---

## 32. Next Documents

Recommended next files:

1. `TASKS.md` — granular implementation backlog.
2. `AGENTS.md` — AI agent execution rules and boundaries.
3. `API_CONTRACT.md` — detailed request/response schemas.
4. `DATABASE_SCHEMA.md` — SQL migration-oriented schema.
5. `EVALUATION_PLAN.md` — detailed RAGAS/manual audit workflow.
6. `DEPLOYMENT.md` — VPS and Docker Compose deployment guide.

---

## 33. Final Technical Position

RINGKAS MVP uses a hybrid technical architecture:

> **ASP.NET Core is the main backend/API for product-facing features, while Python RAG Worker is an internal processing service for ingestion, parsing, chunking, embedding, indexing, and evaluation.**

This architecture preserves the requirement that backend uses ASP.NET while keeping the RAG pipeline realistic and maintainable for PDF/RAG tooling.
