# RINGKAS_TASKS.md

Status: Implementation Backlog  
Project: RINGKAS — Retrieval Informasi Nasional Generatif untuk Kajian Arsip Statistik  
Baseline documents:
- `RINGKAS_PROJECT_BRIEF.md`
- `RINGKAS_PRD.md`
- `RINGKAS_SRD.md`
- `RINGKAS_TECHNICAL_SPEC.md`

---

## 1. Purpose

Dokumen ini berisi backlog implementasi granular untuk membangun MVP RINGKAS berdasarkan Project Brief, PRD, SRD, dan Technical Spec.

Dokumen ini boleh dipakai oleh:
- human developer;
- AI supervisor/orchestrator agent;
- coding sub-agent;
- reviewer teknis.

---

## 2. Important Integrity Note

Kolom `target_commit_date` di dokumen ini adalah **tanggal milestone / rencana commit**.

Backdate diperbolehkan.

---

## 3. Task Status Legend

| Status | Meaning |
|---|---|
| `todo` | Belum dikerjakan |
| `in_progress` | Sedang dikerjakan |
| `blocked` | Terhalang dependency |
| `review` | Menunggu review |
| `done` | Selesai |

---

## 4. Priority Legend

| Priority | Meaning |
|---|---|
| `P0` | Wajib untuk MVP core |
| `P1` | Penting untuk MVP stabil |
| `P2` | Nice-to-have / setelah core stabil |

---

## 5. Global Non-Negotiable Constraints

1. Main backend/API wajib menggunakan **ASP.NET Core Web API** sebagai source of truth untuk domain logic dan authorization.
2. Python hanya digunakan sebagai **internal RAG Worker**, bukan public-facing backend utama.
3. Frontend/web presentation layer wajib menggunakan **Next.js + TypeScript** dengan App Router sebagai API consumer terhadap ASP.NET Core.
4. Next.js tidak boleh mengakses PostgreSQL atau Qdrant secara langsung atau mengambil alih core backend responsibilities.
5. MVP bersifat **text-first**.
6. OCR tidak masuk MVP.
7. Parser utama MVP adalah **PyMuPDF** di Python RAG Worker.
8. Docling hanya future plan / kandidat eksperimen.
9. Vector database menggunakan **Qdrant**.
10. Metadata, auth, chat history, ingestion status, dan logs disimpan di **PostgreSQL**.
11. Deployment MVP menggunakan **1 VPS** dan **Docker Compose**.
12. PDF disimpan lokal di `/data/ringkas/pdfs`.
13. Semua jawaban substantif wajib punya citation.
14. Sistem tidak boleh membuat angka, periode, wilayah, satuan, atau definisi yang tidak ada di sumber.
15. Jika sumber tidak cukup, sistem wajib memberi batasan atau menolak menjawab substantif.
16. Evaluasi menggunakan automated-first approach, tetapi manual audit 20% tetap wajib.

---

## 6. Target Timeline Summary

| Phase | Date Range | Focus |
|---|---:|---|
| Phase 0 | 2026-06-01 to 2026-06-04 | Project docs, repo scaffold, baseline architecture |
| Phase 1 | 2026-06-05 to 2026-06-10 | ASP.NET API foundation, PostgreSQL, Identity |
| Phase 2 | 2026-06-11 to 2026-06-15 | Next.js + TypeScript frontend foundation |
| Phase 3 | 2026-06-16 to 2026-06-23 | Python RAG Worker, ingestion, parsing, chunking |
| Phase 4 | 2026-06-24 to 2026-06-30 | Embedding, Qdrant indexing, retrieval, citation, ingestion orchestration |
| Phase 5 | 2026-07-01 to 2026-07-04 | Generation, chat, document search, admin ingestion |
| Phase 6 | 2026-07-05 to 2026-07-07 | Evaluation harness, logging, rate limit, hardening |
| Phase 7 | 2026-07-08 | MVP integration review and documentation lock |

---

# 7. Implementation Tasks

## Phase 0 — Documentation and Repository Foundation

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0001 | 2026-06-04 | P0 | Docs | Add baseline project documentation | None | `docs/` contains Project Brief, PRD, SRD, Technical Spec, Tasks | All docs are present and linked from README | Docs drift from implementation | done |
| T-0002 | 2026-06-04 | P0 | Repo | Initialize monorepo structure | T-0001 | `apps/web`, `apps/api`, `services/rag-worker`, `infra`, `docs`, `scripts`, `tests` | Folder structure matches Technical Spec | Agent creates messy structure | done |
| T-0003 | 2026-06-04 | P0 | Repo | Add root README | T-0002 | Root `README.md` explains project, architecture, local setup outline | README references docs and constraints | README overclaims features | done |
| T-0004 | 2026-06-04 | P0 | Config | Add `.gitignore`, `.editorconfig`, environment examples | T-0002 | `.gitignore`, `.editorconfig`, `.env.example` | Secrets are not committed | Secret leakage | done |
| T-0005 | 2026-06-04 | P0 | Infra | Draft Docker Compose baseline | T-0002 | `infra/docker-compose.yml` with Next.js web, ASP.NET Core API, Python RAG Worker, PostgreSQL, and Qdrant placeholders | Compose file is syntactically valid | Container networking mistakes | done |
| T-0006 | 2026-06-04 | P1 | Contracts | Create API contract placeholder | T-0002 | `docs/contracts/api.md` or OpenAPI placeholder | Endpoint groups are listed | Contract not synced with backend | done |
| T-0007 | 2026-06-04 | P1 | Governance | Add contribution and agent safety notes | T-0001 | `docs/CONTRIBUTING.md` or section in README | Non-negotiable constraints are visible | Agent violates scope | done |

---

## Phase 1 — ASP.NET Core API Foundation

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0101 | 2026-06-05 | P0 | Backend | Scaffold ASP.NET Core Web API project | T-0002 | `apps/api` ASP.NET Core project | API runs locally and exposes `/health` | Wrong framework selected | done |
| T-0102 | 2026-06-05 | P0 | Backend | Add health check endpoint | T-0101 | `GET /health` | Returns healthy response | No deployment observability | done |
| T-0103 | 2026-06-06 | P0 | Database | Add PostgreSQL configuration | T-0101, T-0005 | API can connect to PostgreSQL | Connection string uses env var | Hardcoded credentials | done |
| T-0104 | 2026-06-06 | P0 | Database | Add initial EF Core setup | T-0103 | DbContext and first migration setup | Migration runs locally | Bad schema design | done |
| T-0105 | 2026-06-07 | P0 | Auth | Add ASP.NET Core Identity base | T-0104 | User tables and identity configuration | Email-password auth foundation exists | Overcomplicated auth | done |
| T-0106 | 2026-06-07 | P0 | Auth | Define roles: guest, user, admin/system_maintainer | T-0105 | Role seed or role constants | Admin-only policy can be applied | Role mismatch | done |
| T-0107 | 2026-06-08 | P0 | Auth | Implement registration and login endpoints | T-0105 | `/api/auth/register`, `/api/auth/login` | User can register/login in dev | Insecure token/session handling | done |
| T-0108 | 2026-06-08 | P0 | Auth | Implement current user/profile endpoint | T-0107 | `/api/me` | Returns authenticated user profile | Leaks sensitive fields | done |
| T-0109 | 2026-06-09 | P1 | Auth | Add email verification placeholder flow | T-0107 | Email verification status field and endpoint placeholder | Registration model supports verification | MVP public abuse risk | done |
| T-0110 | 2026-06-09 | P1 | Auth | Add Google OAuth backend placeholder | T-0107 | Google OAuth config structure | Config is env-based and disabled safely if missing | OAuth blocks local dev | done |
| T-0111 | 2026-06-10 | P0 | Rate Limit | Add rate limit middleware/policy placeholder | T-0107 | Per-IP/per-user rate limit structure | Guest and user can be limited | Abuse/cost explosion | done |
| T-0112 | 2026-06-10 | P1 | Logging | Add structured application logging | T-0101 | API logs app and error events | Logs include request ID/correlation ID if possible | Hard to debug production | done |

---

## Phase 2 — Next.js + TypeScript Frontend Foundation

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0201 | 2026-06-11 | P0 | Frontend | Scaffold Next.js + TypeScript application | T-0002 | `apps/web` Next.js + TypeScript project | App runs locally | Wrong frontend framework | done |
| T-0202 | 2026-06-11 | P0 | Frontend | Add Next.js App Router structure and layouts | T-0201 | App Router routes and layouts for home, login, register, chat, documents, admin | Navigation works locally | UX fragmentation | done |
| T-0203 | 2026-06-12 | P0 | Frontend | Add API client wrapper | T-0201, T-0107 | Shared API client using env API base URL | API calls centralized | Hardcoded API URL | done |
| T-0204 | 2026-06-12 | P0 | Frontend | Add auth pages | T-0107, T-0202 | Login/register UI | User can submit credentials | Auth state bugs | done |
| T-0205 | 2026-06-13 | P0 | Frontend | Add protected Next.js application layout | T-0204 | App Router layout for authenticated user pages | Protected pages redirect if unauthenticated | Broken route guards | done |
| T-0206 | 2026-06-13 | P1 | Frontend | Add admin route guard placeholder | T-0106, T-0205 | Admin page only visible for admin role | Non-admin cannot access UI route | Admin exposure | done |
| T-0207 | 2026-06-14 | P0 | Frontend | Add chat page skeleton | T-0202 | Next.js client/server components as needed for chat input, answer area, and citation placeholder | UI supports question submission placeholder | UI not aligned with citation policy | done |
| T-0208 | 2026-06-14 | P1 | Frontend | Add document search page skeleton | T-0202 | Next.js client/server components as needed for search input, filters, and result list | UI can display document cards | Search feature delayed | done |
| T-0209 | 2026-06-15 | P1 | Frontend | Add admin ingestion page skeleton | T-0206 | Next.js client/server components as needed for ingestion trigger, job status, and short log panels | Only admin can see page | Admin UI grows too much | done |

---

## Phase 3 — Python RAG Worker, Ingestion, Parsing, and Chunking

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0301 | 2026-06-16 | P0 | Worker | Scaffold Python RAG Worker | T-0002, T-0005 | `services/rag-worker` Python project | Worker starts locally/container | Worker becomes public backend | done |
| T-0302 | 2026-06-16 | P0 | Worker | Add worker configuration and env handling | T-0301 | Env config for DB, Qdrant, provider keys, PDF path | No secrets committed | Misconfigured production | done |
| T-0303 | 2026-06-17 | P0 | Database | Add ingestion job schema | T-0104 | `ingestion_jobs` table migration | Supports queued/running/completed/failed | Job status ambiguity | done |
| T-0304 | 2026-06-17 | P0 | Worker | Implement PostgreSQL job polling | T-0301, T-0303 | Worker polls queued jobs | Worker claims jobs safely | Duplicate processing | done |
| T-0305 | 2026-06-18 | P0 | Database | Add document metadata schema | T-0104 | `documents` table migration | Stores title, year, region, source URL, hash, status | Metadata incomplete | done |
| T-0306 | 2026-06-18 | P0 | Ingestion | Implement BPS API client placeholder | T-0301 | Client module with configurable endpoint | Can fetch or mock publication metadata | API assumptions wrong | done |
| T-0307 | 2026-06-19 | P0 | Ingestion | Implement PDF download and local storage | T-0306, T-0305 | PDFs saved to `/data/ringkas/pdfs` | File path and hash stored | Storage bloat | done |
| T-0308 | 2026-06-19 | P0 | Ingestion | Implement file hash deduplication | T-0307 | Hash/checksum stored | Duplicate PDFs are detected | Duplicate indexing | done |
| T-0309 | 2026-06-20 | P0 | Parsing | Implement PyMuPDF parser interface | T-0301, T-0307 | Parser extracts page text and page metadata | Digital PDF text can be extracted | Parser coupled too tightly | done |
| T-0310 | 2026-06-20 | P0 | Parsing | Handle PDF without text layer | T-0309 | Unsupported PDFs marked `unsupported_or_extraction_failed` | No OCR attempted | OCR accidentally added | done |
| T-0311 | 2026-06-21 | P0 | Cleaning | Implement conservative text cleaning | T-0309 | Header/footer cleanup, whitespace normalization, hyphenated word merge | Does not remove numbers/units/periods | Meaning altered by cleaning | done |
| T-0312 | 2026-06-21 | P1 | Parsing | Preserve page and section metadata where possible | T-0309 | Page start/end and optional heading captured | Chunks can cite pages | Citation weak | done |
| T-0313 | 2026-06-22 | P0 | Chunking | Implement recursive chunking with LangChain splitter | T-0311 | Chunk size 500–800 tokens, overlap 20% | Chunks generated consistently | Dependency too heavy | done |
| T-0314 | 2026-06-22 | P0 | Database | Add chunk metadata schema | T-0313 | `chunks` table or metadata record strategy | Stores chunk_id, document_id, page range, heading, source URL | Citation broken | done |
| T-0315 | 2026-06-23 | P1 | Worker | Add ingestion logs | T-0304 | Job logs stored for admin UI | Logs show error summary and progress | Debugging difficult | done |

---

## Phase 4 — Embedding, Qdrant Indexing, Retrieval, Citation, and Ingestion Orchestration

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0401 | 2026-06-24 | P0 | Vector DB | Add Qdrant collection setup script | T-0005, T-0314 | Collection created with dense and sparse vector support placeholder | Script idempotent | Wrong vector schema | done |
| T-0402 | 2026-06-24 | P0 | Embedding | Historical record: add NVIDIA NIM embedding client placeholder | T-0313 | Historical embedding client/config record | Historical record retained; superseded by approved Cloudflare migration tasks | Superseded provider decision could be mistaken for current target | done |
| T-0403 | 2026-06-25 | P0 | Embedding | Historical record: index chunk embeddings into Qdrant | T-0401, T-0402 | Historical Qdrant indexing record | Historical record retained; existing vectors must not be mixed with the new model | Existing vector space is incompatible with new model | done |
| T-0404 | 2026-06-25 | P1 | Retrieval | Implement dense retrieval | T-0403 | Query vector search returns top candidates | Returns chunk IDs and scores | Low recall | done |
| T-0405 | 2026-06-26 | P1 | Retrieval | Implement sparse retrieval placeholder | T-0401 | Sparse retrieval path exists | Can be mocked if sparse model pending | Hybrid not truly ready | done |
| T-0406 | 2026-06-26 | P0 | Retrieval | Implement RRF fusion | T-0404, T-0405 | Dense + sparse candidates fused | Config supports dense top-20 + sparse top-20 | Fusion bugs | done |
| T-0407 | 2026-06-27 | P0 | Retrieval | Implement top-K final selection | T-0406 | Final top-10 chunks selected for generation | Top-K configurable | Too much noise/token cost | done |
| T-0408 | 2026-06-27 | P0 | Citation | Implement citation payload builder | T-0314, T-0407 | Citation includes title, year, region, page, URL, excerpt | Every source chunk can generate citation | Invalid citation | done |
| T-0409 | 2026-06-28 | P0 | Retrieval | Implement retrieval sufficiency rule | T-0407, T-0408 | System detects insufficient evidence | Allows partial answer/refusal | Hallucination risk | done |
| T-0410 | 2026-06-28 | P1 | Logging | Add retrieval debug log for developer | T-0407 | Logs query, filters, candidates, selected chunks | Sensitive content handled carefully | Privacy/log bloat | done |
| T-0411 | 2026-06-29 | P1 | API | Add document search backend endpoint | T-0305 | `/api/documents/search` | Supports keyword/metadata basics | Search too broad | done |
| T-0412 | 2026-06-30 | P1 | API | Add citation/source endpoint | T-0408 | `/api/sources/{id}` or equivalent | Returns source excerpt and metadata | Exposes wrong source | done |
| T-0413 | 2026-06-30 | P0 | Worker | Wire end-to-end ingestion processor | T-0304, T-0308, T-0310, T-0312, T-0315, T-0403, T-0417 | Claimed jobs run metadata retrieval, download, deduplication, parsing, cleaning, chunking, Cloudflare embedding, versioned Qdrant indexing, status, and logging flow | A queued job reaches completed or failed deterministically only after the approved embedding migration/integration is complete; indexed chunks retain source mapping; unsupported and per-document failures are recorded without stopping the batch | Pipeline components remain disconnected or jobs become stuck; vectors may be written to the wrong collection | done |

### Batch 1 — Cloudflare Embedding Architecture Alignment

T-0402 and T-0403 above remain as historical completed implementation records.
They are superseded by the approved Cloudflare-only embedding target and do not
mean that the migration is complete.

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0414 | 2026-07-16 | P0 | Docs/Config | Lock Cloudflare Workers AI embedding architecture and configuration contract | T-0402, T-0403 | Source-of-truth docs and env examples define Cloudflare-only embedding, model identifier, separate generation variables, versioned collection contract, no fallback, live dimension verification requirement, and migration boundary | All source-of-truth docs are consistent; no vector dimension is invented; placeholders only; no application code, collection, or production data is changed | Documentation drift or accidental mixing of generation and embedding configuration | done |
| T-0415 | 2026-07-16 | P0 | Embedding | Implement Cloudflare Workers AI Qwen3 embedding client with sanitized errors, bounded timeout, batching, response validation, and tests | T-0414 | Worker client for `@cf/qwen/qwen3-embedding-0.6b` with safe configuration and tests | Calls the documented Cloudflare endpoint; uses bearer auth; supports string/array input batching; sanitizes errors; enforces bounded timeout; validates non-empty consistent vectors; tests pass without secrets | Provider response shape, limits, or availability differ from assumptions | done |
| T-0416 | 2026-07-16 | P0 | Vector DB/Embedding | Add live dimension verification, versioned Qdrant collection migration, and full reindex tooling | T-0414, T-0415 | Live dimension verifier, configuration lock, safe collection creation, migration tooling, and full corpus reindex command | Every returned vector has one consistent non-zero dimension; collection creation fails on mismatch; old and new vectors are never mixed; full corpus reindex is resumable/observable | Incorrect dimension or partial reindex can corrupt retrieval compatibility | done |
| T-0417 | 2026-07-16 | P0 | Worker/Retrieval | Integrate the new embedding client into indexing and query embedding, then verify dense retrieval uses one compatible vector space | T-0415, T-0416 | Indexing and query paths use the same approved model and versioned collection | Ingestion and query embedding use the Cloudflare client/model; dense vectors match the verified collection dimension; compatibility is tested; hybrid dense+sparse, RRF, and Top-10 remain intact; the sufficiency interface/path is not altered | Index/query model mismatch causes empty or incorrect dense retrieval | done |

---

## Phase 5 — Generation, Chat, Admin Ingestion, and UI Integration

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0501 | 2026-07-01 | P0 | Generation | Add NVIDIA NIM generation client | T-0407 | Generation client with env model name | Can call or mock provider | Provider unavailable | done |
| T-0502 | 2026-07-01 | P0 | Generation | Add Cloudflare Workers AI fallback client | T-0501 | Fallback client configured | Used only if primary fails | Fallback behavior hidden | done |
| T-0503 | 2026-07-02 | P0 | Generation | Implement grounded prompt template | T-0501, T-0408, T-0409 | Prompt enforces answer only from chunks | Refuses/limits unsupported claims | Prompt too permissive | todo |
| T-0504 | 2026-07-02 | P0 | API | Implement Chat/Q&A endpoint | T-0503, T-0407 | `/api/chat` or `/api/qa` | Returns answer, citations, limitations | No citation in answer | todo |
| T-0505 | 2026-07-03 | P0 | Database | Add chat session/history schema | T-0104, T-0504 | Tables for chat sessions/messages | User can retrieve own history | Privacy leak | todo |
| T-0506 | 2026-07-03 | P0 | API | Implement chat history endpoints | T-0505 | `/api/chats`, `/api/chats/{id}` | User sees own chat only | Cross-user exposure | todo |
| T-0507 | 2026-07-03 | P0 | Admin | Implement admin ingestion trigger endpoint | T-0303, T-0413 | `/api/admin/ingestion/jobs` | Admin can create a job that the worker can process | Unprotected endpoint or unprocessable job | todo |
| T-0508 | 2026-07-04 | P0 | Admin | Implement admin ingestion status endpoint | T-0303, T-0315 | `/api/admin/ingestion/jobs/{id}` | Admin sees status/log summary | Log leakage | todo |
| T-0509 | 2026-07-04 | P1 | Frontend | Connect chat UI to backend | T-0207, T-0504 | User can ask question from UI | Answer displays citations | UX hides limitations | todo |
| T-0510 | 2026-07-04 | P1 | Frontend | Connect document search UI to backend | T-0208, T-0411 | Search results displayed | Metadata visible | Search not useful | todo |
| T-0511 | 2026-07-04 | P1 | Frontend | Connect admin ingestion UI to backend | T-0209, T-0507, T-0508 | Admin can trigger and view job status | Role guard enforced | Admin UI scope creep | todo |

---

## Phase 6 — Evaluation, Quota, Hardening, and Integration

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0601 | 2026-07-05 | P0 | Evaluation | Add evaluation dataset schema/template | T-0408 | Template for 100 questions, reference answer, evidence chunk | Supports manual verification | Weak ground truth | todo |
| T-0602 | 2026-07-05 | P1 | Evaluation | Add RAGAS evaluation harness placeholder | T-0504, T-0601 | Script/notebook for automated evaluation | Can run on sample dataset | Misleading score | todo |
| T-0603 | 2026-07-05 | P1 | Evaluation | Add manual audit template | T-0601 | 20% audit sheet/template | Checks citation, angka, periode, wilayah, satuan, definisi | Manual audit skipped | todo |
| T-0604 | 2026-07-06 | P0 | Quota | Enforce guest 1-prompt quota | T-0111, T-0504 | Guest limited to one prompt | Guest cannot spam chat | Abuse risk | todo |
| T-0605 | 2026-07-06 | P1 | Quota | Add registered user daily quota placeholder | T-0111 | Configurable daily quota | Quota value env/config-based | Cost overrun | todo |
| T-0606 | 2026-07-06 | P1 | Security | Add admin endpoint abuse protection | T-0507, T-0508 | Admin endpoints still rate-limited/protected | Repeated ingestion abuse prevented | Resource exhaustion | todo |
| T-0607 | 2026-07-07 | P0 | Integration | End-to-end ingestion smoke test | T-0413, T-0507 | One sample document ingested to Qdrant through the admin-triggered job flow | Document chunks searchable after the working T-0413 Cloudflare embedding pipeline is available | Pipeline broken late | todo |
| T-0608 | 2026-07-07 | P0 | Integration | End-to-end chat smoke test | T-0504, T-0607 | User asks question and receives cited answer | No citation means failure | Hallucination | todo |
| T-0609 | 2026-07-07 | P1 | Docs | Update implementation docs | T-0607, T-0608 | README/docs include setup and known limitations | New dev/agent can run project | Docs stale | todo |

---

## Phase 7 — MVP Review and Documentation Lock

| Task ID | Target Commit Date | Priority | Area | Task | Dependencies | Expected Output | Acceptance Criteria | Risk | Status |
|---|---:|---|---|---|---|---|---|---|---|
| T-0701 | 2026-07-08 | P0 | Review | Run MVP scope review against Project Brief/PRD/SRD | T-0609 | Scope review checklist | No out-of-scope feature slipped in | Scope creep | todo |
| T-0702 | 2026-07-08 | P0 | Review | Run Technical Spec compliance review | T-0609 | Compliance notes | ASP.NET main backend + Python worker architecture intact | Architecture drift | todo |
| T-0703 | 2026-07-08 | P1 | Review | Identify remaining TBDs | T-0701 | List of unresolved decisions | Provider models/quota/session strategy listed | Hidden blockers | todo |
| T-0704 | 2026-07-08 | P1 | Docs | Lock task plan and prepare AGENTS.md input | T-0701, T-0702 | Clean task backlog ready for agents | AGENTS.md can reference tasks | Agent ambiguity | todo |

---

# 8. Suggested Commit Message Convention

Use concise, truthful messages:

```text
docs: add project brief and requirements baseline
chore: scaffold monorepo structure
feat(api): add ASP.NET health endpoint
feat(worker): add PyMuPDF parser interface
feat(retrieval): add RRF fusion pipeline
feat(chat): add grounded Q&A endpoint
test: add ingestion smoke test
docs: update MVP setup instructions
```

Do not use commit messages that imply a feature is complete if it is only a placeholder.

---

# 9. Recommended Agent Execution Rule

AI agents must execute tasks in dependency order. If a task requires unresolved provider credentials, unavailable API access, or unknown model names, the agent must implement a safe placeholder/configuration layer and mark the task as partially blocked instead of inventing provider-specific details.

---

# 10. Next Document

After this file, create:

```text
RINGKAS_AGENTS.md
```

Purpose:
- define agent roles;
- define allowed/disallowed actions;
- define task execution protocol;
- prevent scope creep;
- enforce documentation-first implementation.
