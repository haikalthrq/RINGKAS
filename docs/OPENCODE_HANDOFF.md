# RINGKAS OpenCode Local Handoff

## 1. Overview & Context

This document is the execution handoff for continuing development and operational tasks using **OpenCode on this local machine** (`d:\My Files\Personal Project\RINGKAS`).

- **OS / Environment**: Windows (PowerShell / Command Prompt)
- **Git Branch**: `main`
- **Working Tree**: Clean, synchronized with `origin/main`
- **Toolchain**:
  - **.NET SDK**: 9.0 (`dotnet`)
  - **Python**: 3.12+ managed with `uv` (`services/rag-worker`)
  - **Node.js**: 20+ & npm (`apps/web`)
  - **Docker**: Local Docker Desktop (PostgreSQL on port 5432, Qdrant on port 6333)

---

## 2. Architecture & Service Boundaries

```
[User Browser]
       │
       ▼ (Port 3000)
[apps/web (Next.js 14 App Router, TypeScript)]
       │
       │ (Port 5000 / HTTP /api/*)
       ▼
[apps/api (ASP.NET Core 9 Web API)] ─── Source of truth (Auth, Rate limits, Chat, Admin Ingestion)
       │
       │ (Internal HTTP with RAG_INTERNAL_TOKEN, Port 8000)
       ▼
[services/rag-worker (FastAPI rag-query & Ingestion Worker)]
       │                     │
       ▼                     ▼
[PostgreSQL 16]       [Qdrant Vector DB]
(Port 5432)           (Port 6333)
                      Collection: ringkas_chunks_cf_qwen3_embedding_v2
                      Dense: 1024-dim cosine (@cf/qwen/qwen3-embedding-0.6b)
                      Sparse: FastEmbed Qdrant/bm25 with RRF fusion
```

### Non-Negotiable Constraints (from AGENTS.md)
1. **Main Gateway**: ASP.NET Core is the main backend and single source of truth for auth, domain logic, and chat/search endpoints.
2. **Internal Python Service**: `rag-query` and `rag-worker` are internal services; they are never exposed directly to external clients.
3. **Citations & Grounding**: All substantive answers must include citations (title, year, region, page when available, excerpt, source URL). Zero tolerance for fabricated statistics, dates, or regions.
4. **Sufficiency & Refusal**: When retrieved evidence is insufficient or question is out-of-scope (e.g. future dates, unsupported regions), system must refuse substantively and state evidence insufficiency.
5. **Text-First MVP**: PyMuPDF is the primary parser. OCR and production Docling are out of scope. User document upload is out of scope.

---

## 3. Current Implementation & Evaluation Status

| Component | Status | Details |
|---|---|---|
| **Backlog P0 & P1** | 100% Complete | Tasks `T-0001` through `T-0704` in `docs/RINGKAS_TASKS.md` are marked `done`. |
| **P0 Hardening** | Implemented | Persistent Data Protection keys, Google OAuth external login, ingestion heartbeat leasing & recovery, backup/restore scripts (`scripts/backup/`), release preflight script (`scripts/release/preflight.sh`). |
| **Live RAGAS Baseline** | 100% Complete | 100/100 stratified samples evaluated (300/300 finite metrics) with Cloudflare Workers AI (`@cf/openai/gpt-oss-120b`). Report: `evaluations/ragas_report.json`.<br>• Faithfulness: **0.3634** (36.34%)<br>• Context Precision: **0.0614** (6.14%)<br>• Context Recall: **0.1447** (14.47%) |
| **API Unit Tests** | Passing | `dotnet test tests/api/Ringkas.Api.Tests.csproj` (127 passed). |
| **Worker Unit Tests** | Passing | `uv run --project services/rag-worker --extra test --frozen pytest` (730 passed, 59 skipped). |
| **Web Typecheck & Build**| Passing | `npm --prefix apps/web run typecheck` & `npm --prefix apps/web run build` pass without warnings. |

---

## 4. Local Run & Verification Commands

### Start Database Dependencies
```powershell
docker compose up -d postgres qdrant
```

### Run Backend API
```powershell
dotnet run --project apps/api/Ringkas.Api.csproj
```
*(Runs on `http://localhost:5000` or port configured in `apps/api/Properties/launchSettings.json`)*

### Run Internal Python Query Service
```powershell
uv run --project services/rag-worker uvicorn rag_worker.query_service:app --port 8000
```

### Run Frontend UI
```powershell
npm --prefix apps/web run dev
```
*(Opens on `http://localhost:3000`)*

### Run All Test Suites
```powershell
# API unit tests
dotnet test tests/api/Ringkas.Api.Tests.csproj --no-restore

# Worker unit tests
uv run --project services/rag-worker --extra test --frozen pytest

# Web typecheck & production build
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

---

## 5. Next Immediate Tasks for OpenCode

### Task 1: Complete 20-Question Manual Audit (Gate D-09)
- **Target File**: `services/rag-worker/manual_audit_template.csv`
- **Scope**: Questions `q-001` through `q-020` in the stratified evaluation set.
- **Action**: Review model answers against ground-truth BPS DKI Jakarta publications and fill columns:
  - `citation_correctness`, `groundedness`, `number_accuracy`, `period_accuracy`, `region_accuracy`, `unit_accuracy`, `definition_accuracy`, `page_correctness`, `source_correctness`, `reviewer_verdict`, `reviewer_notes`.
  - Change `audit_status` from `pending` to `verified`.

### Task 2: Local End-to-End Smoke Test & UI Verification
- Start all services locally.
- Test user flows in browser (`http://localhost:3000`):
  1. Guest user asking 1 prompt (quota enforcement check).
  2. Register / login via email & password.
  3. Asking substantive DKI Jakarta statistical questions and inspecting citations, excerpts, and source URLs.
  4. Asking out-of-corpus or future questions to verify grounded refusal behavior.
  5. Navigating chat history (`/chat/[id]`).
  6. Document search (`/search`).
  7. Admin ingestion dashboard (`/admin/ingestion`).

### Task 3: Corpus Snapshot Reconciliation
- Reconcile source document count: 263 publications vs 264 snapshot mentioned in older notes.

---

## 6. Key Reference Files

- Agent Rules & Guardrails: `AGENTS.md`
- Tasks Checklist: `docs/RINGKAS_TASKS.md`
- Technical Specification: `docs/RINGKAS_TECHNICAL_SPEC.md`
- Evaluation Report: `evaluations/ragas_report.json`
- Metrics Summary: `evaluations/metrics_summary.md`
- Manual Audit Template: `services/rag-worker/manual_audit_template.csv`
- OpenCode Config: `opencode.json`
