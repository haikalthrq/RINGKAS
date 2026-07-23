# Phase 7 Review

Review date: 2026-07-23
Evidence baseline: repository `main` at `d86c159`
Scope: T-0701, T-0702, T-0703, and T-0704 documentation lock

This is a Phase 7 snapshot. T-0417 was resolved after this review; the
resolution and live evidence are recorded in the final section below.

This document records implementation evidence only. It does not change the
Project Brief, PRD, SRD, or Technical Spec requirements.

## Executive Result

- The approved architecture is present: Next.js presentation layer, ASP.NET
  Core public API, internal Python services, PostgreSQL, Qdrant, and Compose.
- The accepted Phase 6 live evidence proves one official BPS ingestion path and
  one cited chat path. It does not prove the full corpus, failover execution, a
  live evaluation baseline, or a completed manual audit.
- At the Phase 7 baseline, production retrieval was dense-only. The Qdrant
  schema and RRF components had a sparse slot, but the live query path supplied
  an empty sparse result and indexing wrote dense vectors only. T-0417 resolved
  this after the review; see the resolution below.
- Google OAuth and email verification remain placeholders. Chat-history API
  storage exists, but the web application has no chat-history page or link.
- No prohibited MVP feature was found in application implementation. Prohibited
  terms found by repository search are in requirements, guardrails, or truthful
  limitation notes.
- The repository must not be described as production-ready until the listed
  deployment, retrieval, authentication, and evaluation decisions are closed.

## T-0701 MVP Scope Review

Status: reviewed

Status meanings in this section are `compliant`, `partial`, `missing`,
`out-of-scope implementation`, or `unresolved/TBD`.

### Capability Checklist

| MVP area | Status | Evidence and result |
|---|---|---|
| Email-password registration and login | compliant | `apps/api/Endpoints/AuthEndpoints.cs:26-68,118-149` implements both flows; cookie authentication is configured in `apps/api/Program.cs:20-45`. |
| Google OAuth | partial | Routes and configuration checks exist in `apps/api/Endpoints/AuthEndpoints.cs:112-116,191-204`, but both paths return `501 Not Implemented`. This does not satisfy PRD F-01's working Google OAuth requirement (`docs/RINGKAS_PRD.md:191-210`). |
| Email verification | partial | Status is exposed by Identity, but request and confirmation return placeholder `501` responses in `apps/api/Endpoints/AuthEndpoints.cs:71-109`; public registration therefore lacks the required verification mechanism. |
| Basic roles and admin authorization | compliant | Roles are defined and seeded in `apps/api/Auth/AppRoles.cs:3-10` and `apps/api/Auth/IdentityRoleSeeder.cs:7-22`; admin ingestion requires `admin` or `system_maintainer` in `apps/api/Endpoints/AdminIngestionEndpoints.cs:12-20`. |
| Guest one-prompt trial | compliant | Anonymous chat is rate-limited in `apps/api/Endpoints/ChatEndpoints.cs:19-23`; the guest quota is forced to exactly one in `apps/api/Auth/QuotaConfiguration.cs:8-23`; accepted behavior is recorded in `docs/PHASE6_RUNBOOK.md:19-25`. Persistence is a separate limitation. |
| Grounded chat/Q&A | compliant for verified path | `apps/api/Endpoints/ChatEndpoints.cs:290-333` refuses insufficient retrieval and rejects uncited generated output. Accepted supported and refusal checks are recorded in `docs/PHASE6_RUNBOOK.md:214-255`. |
| Citation display and source metadata | compliant | API source endpoints return document, page, URL, and excerpt fields in `apps/api/Endpoints/SourceEndpoints.cs:20-107`; the web citation panel renders metadata and excerpts in `apps/web/components/chat/chat-form.tsx:108-150`. |
| Document search | compliant for registered users | Authorization and keyword/year/topic filtering are implemented in `apps/api/Endpoints/DocumentEndpoints.cs:10-124`; the protected UI is `apps/web/src/app/(protected)/documents/page.tsx:1-12`. |
| Chat history | partial | Storage and ownership-filtered API routes exist in `apps/api/Endpoints/ChatEndpoints.cs:25-29,112-180`, but the built web routes contain no history page and `apps/web/components/site-header.tsx:7-17` has no history link. |
| Admin ingestion UI | compliant in scope | The UI contains only trigger, status, and short logs in `apps/web/src/app/(protected)/admin/page.tsx:73-129`; the backend exposes only create and status routes in `apps/api/Endpoints/AdminIngestionEndpoints.cs:12-20`. |
| BPS DKI Jakarta corpus ingestion | partial | Official endpoint, model, domain, language, and query-key authentication are implemented in `services/rag-worker/ringkas_worker/bps/client.py:22-35,101-149` and mapped in `bps/mapper.py:16-49`. Phase 6 proves one accepted publication, not the complete five-year corpus (`README.md:225-233`). The admin request also accepts arbitrary positive year ranges (`AdminIngestionEndpoints.cs:168-184`). |
| Digital PDF text-first parsing | compliant | PyMuPDF is the production parser and no-text PDFs return `unsupported_or_extraction_failed` in `services/rag-worker/ringkas_worker/parsers.py:83-135`; OCR is rejected by configuration in `config.py:173-178`. |
| Summary based on a question | compliant at MVP Plus capability level | The chat path accepts natural-language questions and applies the same grounded generation policy in `apps/api/Generation/GroundedPromptTemplate.cs:7-22`. No full-document or per-chapter summary feature was added. |
| Automated-first evaluation | partial | The dataset has 100 pending records (`services/rag-worker/evaluation_dataset.json:1-6`), the audit template has 20 pending rows (`manual_audit_template.csv:1-21`), and the harness has a deterministic fixture path. No live RAGAS baseline or completed audit is claimed (`docs/PHASE6_RUNBOOK.md:7-17`). |
| Public abuse controls | partial | Guest and short-window per-IP/per-user limits exist in `apps/api/Program.cs:52-65,179-236`; registered daily quota is optional and in memory. The limitation is explicitly recorded in `README.md:305-316`. |

### Findings By Severity

#### Critical

- None identified as a prohibited scope-creep implementation.

#### Major

- Google OAuth and email verification are not implemented, despite being MVP
  product requirements. Evidence: `apps/api/Endpoints/AuthEndpoints.cs:71-116,191-204`.
- Full MVP corpus readiness is not evidenced. Phase 6 accepted one publication
  and one retrieval result, not all DKI Jakarta publications in the five-year
  window. Evidence: `README.md:225-233` and `docs/PHASE6_RUNBOOK.md:203-212`.
- Registered-user quota is blank-disabled by default and process-local. This is
  a documented public-registration limitation, not a hidden feature. Evidence:
  `apps/api/Auth/QuotaConfiguration.cs:26-39` and `docs/PHASE6_RUNBOOK.md:21-24`.
- Chat history is available through the API but not user-facing in the web
  application. Evidence: `apps/api/Endpoints/ChatEndpoints.cs:25-29` and the
  built route list, which contains no history route.
- The 100-question evaluation dataset and 20-question audit are templates only;
  no baseline quality claim is valid. Evidence: `evaluation_dataset.json:3-6`,
  `manual_audit_template.csv:1-21`, and `docs/PHASE6_RUNBOOK.md:14-17`.

#### Minor

- The admin UI intentionally shows the current job rather than a historical job
  list. This is within the narrow MVP admin scope, not scope creep.
- The web application exposes no full document-management, upload, or analytics
  screens; this is compliant with the admin boundary.

### Prohibited Feature Search

No out-of-scope implementation was found for:

- user document upload;
- OCR pipeline;
- production Docling;
- guaranteed complex-table extraction;
- visual chart or image interpretation;
- real-time BPS database/statistics queries;
- native mobile app;
- payment or subscription;
- public third-party API;
- multi-tenant organizations;
- complex analytics dashboard;
- fine-tuning;
- custom embedding-model training;
- replacement of ASP.NET Core, PostgreSQL, Qdrant, or Next.js.

Evidence: application routes are limited to the mappings in
`apps/api/Program.cs:85-90`; worker dependencies in
`services/rag-worker/pyproject.toml:10-17` contain PyMuPDF and no OCR/Docling
dependency; `services/rag-worker/ringkas_worker/query_service.py:154-177`
starts only the private retrieval service; and the web build exposes only home,
login, register, chat, documents, and admin routes.

### Scope-Creep Result

**No scope creep found.** The repository contains deliberate placeholders and
limitations, but no prohibited product feature was silently implemented.

## T-0702 Technical Spec Compliance Review

Status: reviewed

### Compliance Matrix

| Technical area | Status | Evidence and drift |
|---|---|---|
| Monorepo structure | compliant | `apps/api`, `apps/web`, `services/rag-worker`, `infra`, `docs`, `scripts`, and `tests` exist and match `docs/RINGKAS_TECHNICAL_SPEC.md:207-248`. |
| Public backend boundary | compliant | ASP.NET maps the public endpoints in `apps/api/Program.cs:85-90`; Compose exposes only web port 3000, while API and `rag-query` use internal network exposure (`infra/docker-compose.yml:86-159`). |
| Internal worker and `rag-query` boundary | compliant | Worker is a PostgreSQL poller (`services/rag-worker/ringkas_worker/__main__.py:65-92`); `rag-query` has no host port and requires an internal bearer token (`query_service.py:94-141`). |
| Next.js App Router boundary | compliant | App Router pages are under `apps/web/src/app`; relative API calls and the rewrite are in `apps/web/lib/api-client.ts:22-39` and `apps/web/next.config.ts:6-10`; no direct PostgreSQL/Qdrant client is present in web code. |
| PostgreSQL persistence and migrations | partial | Identity, documents, chunks, jobs, logs, and chat tables are modeled in `apps/api/Data/RingkasDbContext.cs:6-13,19-256` with migrations under `apps/api/Migrations`. The Technical Spec's `usage_logs` design (`docs/RINGKAS_TECHNICAL_SPEC.md:509-520`) has no corresponding model or migration. |
| Qdrant collection and 1024 dimension | partial | Versioned collection, dense/sparse schema, and live dimension verification exist in `services/rag-worker/ringkas_worker/qdrant_setup.py:16-20,138-184,223-243` and `dimension.py:35-94`; the sparse side is not populated or queried in production. `QDRANT_DENSE_DISTANCE` is blank by default in `infra/docker-compose.yml:48-55`, while setup requires it (`qdrant_setup.py:87-92`). |
| Cloudflare-only embedding | compliant at runtime | Indexing and dense query construction instantiate the Cloudflare client in `indexing.py:232-242` and `retrieval.py:221-231`; the approved model is enforced in `embedding/client.py:196-208`. Historical NVIDIA embedding classes remain but are not wired into runtime ingestion/query paths. |
| BPS ingestion contract | partial | The official endpoint contract and query parameters are fixed in `bps/client.py:22-35`; mapping accepts the verified `data[1]` publication array in `bps/mapper.py:16-49`. There is no pagination loop or automatic retry; `BpsClient.fetch_publications` performs one request (`bps/client.py:101-149`), consistent with the limitation in `services/rag-worker/README.md:32-37`. |
| PDF host validation and storage | partial | Destination validation, redirect validation, public-address checks, bounded size/time, and `/data/ringkas/pdfs` storage are implemented in `services/rag-worker/ringkas_worker/pdfs.py:72-128,151-258,286-426`; Compose passes `PDF_ALLOWED_HOSTS` as blank by default (`infra/docker-compose.yml:58-77`), which makes production downloader construction fail until an allowlist is supplied. |
| PyMuPDF and unsupported scan behavior | compliant | `PyMuPDFParser` uses `fitz`, extracts page text, preserves page metadata, and returns the required unsupported status for empty text (`parsers.py:7-12,83-135`). |
| Cleaning and chunk metadata | partial | Conservative cleanup and page/heading preservation exist in `cleaning.py:53-89`; chunk records contain citation metadata (`chunking.py:41-50`, `apps/api/Data/Chunk.cs:3-16`). The worker calls `RecursiveTextChunker(..., length_function=len)` (`__main__.py:47-55`), so the configured 500-800 range is characters, not tokens. `low_structure_confidence` is always written as `False` (`processor.py:213-220`, `db/chunks.py:69-79`). |
| Dense retrieval | compliant | The approved Cloudflare query embedding is validated against configured dimension and sent to Qdrant with dense top-20 (`retrieval.py:246-288`). |
| Sparse retrieval truthfulness | critical drift | The Qdrant sparse reader accepts an externally built `SparseQuery` (`sparse_retrieval.py:81-117,199-224`), but no sparse encoder or sparse index write exists. Indexing writes only `vector={DENSE_VECTOR_NAME: ...}` (`indexing.py:335-345`). The live query engine explicitly creates an empty sparse result (`query_service.py:56-60`). |
| RRF and final Top-10 | partial | RRF and final selection are implemented and tested (`fusion.py:152-200`, `selection.py:101-150`), but production RRF receives dense candidates plus an empty sparse candidate set. The accepted Phase 6 retrieval result therefore proves ten citations, not hybrid retrieval. |
| Retrieval sufficiency guard | compliant with known quality limitation | `QualitativeRetrievalSufficiencyEvaluator` requires citable evidence and returns limitation/refusal states (`sufficiency.py:259-292`); `query_service.py:61-90` applies the result before API generation. Relevance is deterministic lexical assessment and semantic entailment remains future work (`sufficiency.py:94-129,291-292`). |
| Five-model generation order | compliant in code/tests | `FailoverGenerationClient` builds the ordered five attempts (`apps/api/Generation/FailoverGenerationClient.cs:14-22`), and the locked-order test covers all models (`tests/api/Generation/GenerationClientTests.cs:418-452`). Phase 6 only live-exercised the primary (`docs/PHASE6_RUNBOOK.md:38-41`). |
| Citation fields and source endpoint | compliant | Retrieval validates title, year, region, page range, URL, and snippet (`apps/api/Retrieval/InternalRetrievalClient.cs:110-132`); the source API returns the persisted excerpt and metadata (`apps/api/Endpoints/SourceEndpoints.cs:25-46`). Generation rejects lines without valid citation labels (`apps/api/Endpoints/ChatEndpoints.cs:295-333`). |
| Authentication, authorization, quota, and rate limit | partial | Cookie auth, Identity, role policies, guest quota, short-window limits, and admin ingestion limits exist (`Program.cs:20-65,179-236`; `AdminIngestionEndpoints.cs:12-20`). Google OAuth/email verification are placeholders, registered quota is optional/in-memory, and there is no durable usage-log table. |
| Docker Compose single-VPS topology | compliant as local topology | Compose includes PostgreSQL, Qdrant, worker, private `rag-query`, API, and web (`infra/docker-compose.yml:3-184`). Domain/HTTPS, reverse proxy choice, exact VPS size, and backups remain unresolved. |
| Secret handling and environment examples | partial | `.env` is ignored by `.gitignore:20-27`, and the tracked-secret check found no tracked `.env`, PDF, database, cookie, token, or secret artifact. The worker example documents `PDF_ALLOWED_HOSTS` (`services/rag-worker/.env.example:19-27`), but the root Compose example omits it and defaults it blank. |
| Evaluation dataset, RAGAS, manual audit | partial | Dataset and audit structure exist, and the harness blocks live evaluation until data is verified and evaluator settings are supplied (`ragas_harness.py:57-120`). No live baseline or completed 20% audit exists. |
| Phase 6 live evidence | partial by design | Accepted evidence proves official BPS path, 82-page PDF, 192 chunks, dimension 1024, 192 Qdrant points, ten retrieval citations, and cited chat/refusal behavior (`README.md:225-275`). It does not prove sparse retrieval, failover, full-corpus coverage, or evaluation quality. |

### Technical Findings By Severity

#### Critical

1. **At the Phase 7 baseline, required hybrid retrieval was not the production
   retrieval path.** The collection declared sparse support, but indexing wrote
   dense vectors only and `QueryEngine.query` supplied no sparse candidates.
   T-0417 resolved this after the review; see the resolution below.

#### Major

1. **Chunk sizing is not token-based.** The configured values are described as
   tokens, but the worker passes `len` to a character splitter. Evidence:
   `services/rag-worker/ringkas_worker/__main__.py:47-55` and
   `chunking.py:66-84`. The Technical Spec also leaves exact tokenization TBD
   at `docs/RINGKAS_TECHNICAL_SPEC.md:846-864`.
2. **Ingestion retry requirement is not implemented.** The SRD requires retries
   for download/parsing/embedding (`docs/RINGKAS_SRD.md:230-236`), while the
   worker README explicitly says it has no automatic retry
   (`services/rag-worker/README.md:32-37`).
3. **Public authentication requirements are incomplete.** Google OAuth and
   email verification return `501 Not Implemented`, as detailed above.
4. **Usage logging required by the Technical Spec is absent.** Request logs and
   ingestion logs exist, but the specified `usage_logs` data structure is not in
   the DbContext or migrations. Evidence: `apps/api/Data/RingkasDbContext.cs:6-13`
   and `docs/RINGKAS_TECHNICAL_SPEC.md:388-400,509-520`.
5. **Cost/output controls are incomplete.** Chat input is capped at 2,000
   characters (`apps/api/Endpoints/ChatEndpoints.cs:238-247`), but provider
   requests do not set an output/token cap and the Technical Spec leaves it TBD
   (`docs/RINGKAS_TECHNICAL_SPEC.md:1117-1138`).

#### Minor / Residual Drift

1. `low_structure_confidence` is modeled but always false in the ingestion
   path, so uncertain table/layout structure is not represented faithfully.
2. The API surface is narrower than the preliminary Technical Spec table:
   `/health` is mapped instead of `/api/health`, and list/history-detail,
   document-detail, logout, and dedicated ingestion-log routes are not all
   present. Core implemented MVP routes remain protected and functional.
3. Compose has no reverse-proxy service and exposes the local web port directly;
   this is acceptable for local smoke testing but not a resolved HTTPS deployment.

### Architecture Result

**ASP.NET Core remains the only public backend, Python remains internal, and the
Next.js boundary is intact.** The main architecture is compliant. The retrieval
implementation drift recorded by this Phase 7 snapshot was resolved by T-0417.

## T-0703 Remaining TBD Register

Duplicates from the source documents are consolidated below. A status of
`known limitation` is not presented as a completed decision.

| ID | Item and current status | Source references | Required evidence/owner | Blocks |
|---|---|---|---|---|
| D-01 | BPS, NVIDIA, and Cloudflare terms, quotas, rate limits, and deployment availability remain unresolved. | `docs/RINGKAS_PROJECT_BRIEF.md:827-836`; `docs/PHASE6_RUNBOOK.md:282-292` | Provider account documentation and a deployment capacity estimate; owner is not assigned in the source docs. | Production deployment and public registration |
| D-02 | Registered-user daily quota is blank-disabled and process-local. | `apps/api/Auth/QuotaConfiguration.cs:26-39`; `docs/RINGKAS_TECHNICAL_SPEC.md:1359`; `README.md:313` | Provider cost/limit estimate and an explicit quota decision; owner not documented. | Production public access |
| D-03 | Session versus JWT is unresolved in the source docs; current code uses ASP.NET cookie auth. | `docs/RINGKAS_TECHNICAL_SPEC.md:573-587`; `apps/api/Program.cs:28-45` | Record or approve the deployment auth decision; do not infer cross-domain behavior from local Compose. | Documentation/deployment lock, not current same-origin smoke |
| D-04 | Domain and HTTPS provider are TBD; current Compose exposes local HTTP. | `docs/RINGKAS_TECHNICAL_SPEC.md:315-325`; `infra/docker-compose.yml:161-175` | Select and verify Caddy, Nginx/Certbot, or another approved deployment path; owner not documented. | Production deployment |
| D-05 | Exact VPS size and storage capacity are not specified. | `docs/RINGKAS_PROJECT_BRIEF.md:747-750,732-733` | Measure PDF/Qdrant/PostgreSQL footprint and provider workload; owner not documented. | Production capacity decision |
| D-06 | Resolved after Phase 7: BM25 via FastEmbed `Qdrant/bm25` is indexed and queried in the versioned v2 collection with Qdrant IDF weighting. | `services/rag-worker/ringkas_worker/sparse_retrieval.py`; live v2 reindex/query evidence below | None for T-0417; continue monitoring provider availability and deployment configuration. | None for T-0417 |
| D-07 | Reranker provider/model is optional and unresolved. | `docs/RINGKAS_TECHNICAL_SPEC.md:506-512,1361`; `docs/RINGKAS_PROJECT_BRIEF.md:260-261` | Only decide after baseline retrieval and provider cost review. | Neither for MVP without reranker |
| D-08 | Evaluation baseline, final target metrics, and metric thresholds are unresolved. | `docs/RINGKAS_PROJECT_BRIEF.md:670-678`; `docs/RINGKAS_TECHNICAL_SPEC.md:1207-1212` | Complete verified dataset, live RAGAS run, and manual interpretation; owner not documented. | Evaluation claim and quality gate |
| D-09 | Manual audit is not complete; 20 rows remain pending. | `services/rag-worker/manual_audit_template.csv:1-21`; `docs/PHASE6_RUNBOOK.md:7-17` | Human review of at least 20 verified questions; reviewer owner not assigned. | Baseline quality claim |
| D-10 | Token/output limit is TBD; only request character length is currently bounded. | `docs/RINGKAS_TECHNICAL_SPEC.md:1133-1138`; `apps/api/Endpoints/ChatEndpoints.cs:238-247` | Provider-specific cost/limit decision and an output cap. | Production public access |
| D-11 | Ingestion retry count is TBD and no automatic retry is implemented. | `docs/RINGKAS_SRD.md:230-236`; `docs/RINGKAS_TECHNICAL_SPEC.md:770-776,1362`; `services/rag-worker/README.md:32-37` | Choose and verify retry/backoff behavior without hiding per-document failures. | Ingestion reliability acceptance |
| D-12 | Backup frequency and operational backup strategy are TBD; backup script directory is empty except `.gitkeep`. | `docs/RINGKAS_TECHNICAL_SPEC.md:303-313`; `scripts/backup/.gitkeep` | Define and test PostgreSQL, Qdrant, PDF, and log backups; owner not documented. | Production deployment |
| D-13 | Monitoring, log retention, and storage-retention details are not finalized. | `docs/RINGKAS_TECHNICAL_SPEC.md:1142-1170`; `docs/RINGKAS_PROJECT_BRIEF.md:732-733` | Define retention, alerting, storage-capacity monitoring, and privacy limits; owner not documented. | Production operations |
| D-14 | In-memory quota reset on process restart is a documented limitation, not a hidden completed decision. | `docs/PHASE6_RUNBOOK.md:19-24`; `README.md:305-316` | Decide whether persistence is required before public deployment. | Production abuse control |
| D-15 | Cloudflare Llama 4 Scout is configured as an experimental last-resort model and has not been promoted by evaluation. | `docs/RINGKAS_TECHNICAL_SPEC.md:1356-1358`; `docs/PHASE6_RUNBOOK.md:30-41` | Evaluate it before treating it as a trusted fallback; no promotion decision is made here. | Neither if experimental status remains explicit |
| D-16 | Email verification implementation is unresolved and currently a placeholder. | `docs/RINGKAS_PRD.md:196-202`; `apps/api/Endpoints/AuthEndpoints.cs:71-109` | Choose delivery/confirmation implementation and test it; owner not documented. | Public registration acceptance |
| D-17 | Google OAuth implementation is unresolved and currently a placeholder. | `docs/RINGKAS_PRD.md:196-210`; `apps/api/Endpoints/AuthEndpoints.cs:112-116,191-204` | Complete provider callback/session flow and integration test; owner not documented. | MVP authentication acceptance |
| D-18 | Exact tokenization method is TBD while implementation currently counts characters. | `docs/RINGKAS_TECHNICAL_SPEC.md:846-864`; `services/rag-worker/ringkas_worker/__main__.py:52` | Approve a token-counting method and revalidate chunk size/overlap. | Technical chunking compliance |
| D-19 | PDF allowed-host configuration is deployment-specific and required; Compose defaults it blank. | `services/rag-worker/.env.example:19-27`; `infra/docker-compose.yml:58-65`; `services/rag-worker/ringkas_worker/pdfs.py:85-88` | Set and verify exact BPS PDF host allowlist without weakening SSRF defenses. | New deployment/worker startup |
| D-20 | Qdrant dense distance is blank in Compose setup defaults although collection setup requires it. | `infra/docker-compose.yml:48-55`; `services/rag-worker/ringkas_worker/qdrant_setup.py:87-92` | Supply the already live-verified collection distance or rerun live schema verification; do not invent a value. | New collection setup |
| D-21 | Latency, throughput, and concurrency targets are TBD. | `docs/RINGKAS_SRD.md:720-722,851-867` | Measure the accepted topology under the intended user load; owner not documented. | Scale/performance sign-off |

## T-0704 Task And Agent Lock

### Task Status Rules

- T-0001 through T-0609 remain `done` only where their task output is a
  completed implementation, accepted placeholder, or accepted Phase 6 evidence
  as stated by the task itself.
- T-0417 was changed from `done` to `blocked` during this Phase 7 review. It is
  now restored to `done` after the approved sparse path, v2 reindex, live hybrid
  retrieval, citation, and refusal checks recorded in the resolution below.
- T-0701, T-0702, T-0703, and T-0704 are marked `done` in
  `docs/RINGKAS_TASKS.md`.
- T-0704 was marked `done` only after the backlog and agent guidance patches
  were applied and the final verification commands were run.

### Agent Input

Future agents must read the canonical documents from `docs/` in this order:

1. `docs/RINGKAS_PROJECT_BRIEF.md`
2. `docs/RINGKAS_PRD.md`
3. `docs/RINGKAS_SRD.md`
4. `docs/RINGKAS_TECHNICAL_SPEC.md`
5. `docs/RINGKAS_TASKS.md`
6. `docs/RINGKAS_AGENTS.md`
7. `docs/PHASE6_RUNBOOK.md`
8. `docs/PHASE7_REVIEW.md`

T-0417 and D-06 are resolved. The remaining recommended work is to close the
deployment and evaluation items below; do not claim full production readiness
from the single-document live evidence alone.

In parallel, deployment planning must close D-01, D-02, D-04, D-10, D-12,
D-13, D-14, D-19, and D-20. Evaluation work must close D-08 and D-09. No agent
may convert any other register item into a final value without the required
evidence and an explicit source-of-truth update.

### Scope And Grounding Lock

- Keep ASP.NET Core as the only public backend and keep Python worker/
  `rag-query` private.
- Keep Next.js as an App Router presentation layer and API consumer only.
- Keep PostgreSQL, Qdrant, PyMuPDF, Cloudflare-only embedding, and the locked
  five-model generation order.
- Do not add OCR, production Docling, uploads, public third-party API, mobile,
  payment, complex analytics, fine-tuning, custom embedding training, or a
  replacement backend/database/vector store.
- Preserve citation, source sufficiency, refusal, and no-fabrication guards.
- Do not claim a full corpus, hybrid retrieval, completed evaluation, or
  production readiness from the accepted single-document Phase 6 evidence.

## Verification Record

The final verification results are recorded in the Phase 7 task report. The
required checks are:

```text
git diff --check
docker compose --env-file .env -f infra/docker-compose.yml config --quiet
dotnet test tests/api/Ringkas.Api.Tests.csproj --no-restore
dotnet build apps/api/Ringkas.Api.csproj --no-restore
uv run --project services/rag-worker --extra test --frozen pytest
npm run typecheck
npm run build
```

No commit or push is part of Phase 7.

## T-0417 Resolution

- The new target collection is `ringkas_chunks_cf_qwen3_embedding_v2`; the
  previous v1 collection remains untouched for rollback.
- Qdrant v2 has dense size 1024/cosine and named sparse `IDF` configuration.
- Live reindex used Cloudflare `@cf/qwen/qwen3-embedding-0.6b` plus FastEmbed
  `Qdrant/bm25`, processing 192 chunks with 192 indexed, 0 skipped, and 0 failed.
- Live retrieval returned dense 20 candidates, sparse 20 candidates, 30 fused
  candidates, and final Top-10 selection. The private retrieval adapter returned
  HTTP 200 with 10 citations for the supported DKI Jakarta question, while the
  September 2099 question returned HTTP 200 with `insufficient` and
  `requires_refusal=true`.
- Worker verification passed: 718 tests passed, 59 skipped, BM25 smoke encoding,
  lockfile validation, Compose config validation, and `git diff --check`.
- The long-running local containers still require deployment-specific
  `RAG_INTERNAL_TOKEN` and `PDF_ALLOWED_HOSTS`; those values remain unresolved
  and were not invented.
