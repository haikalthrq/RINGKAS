# RINGKAS VPS OpenCode Handoff

## Purpose

This file is the execution handoff for OpenCode on the VPS. The application
implementation is complete through P0 hardening. Continue from staging/beta
deployment and operational validation; do not rebuild completed application
features or claim public-production readiness before the remaining release
gates are closed.

## Repository Snapshot

- Repository: `https://github.com/haikalthrq/RINGKAS.git`
- Branch: `main`
- Handoff commit: `f46ae58 feat(evaluation): complete full 100-sample live RAGAS baseline` (or latest HEAD)
- Previous P0 commit: `f890e26 feat: execute production P0 hardening`
- Local verification at handoff:
  - API tests: `127 passed`
  - Worker tests: `730 passed, 59 skipped`
  - API build: passed with no warnings/errors
  - Web typecheck and production build: passed
  - Live RAGAS baseline: 100/100 stratified samples completed (300/300 finite metrics) with Cloudflare `@cf/openai/gpt-oss-120b` (report: `evaluations/ragas_report.json`)

Start by checking out the tracked branch state:

```bash
git clone https://github.com/haikalthrq/RINGKAS.git
cd RINGKAS
git checkout main
git pull --ff-only origin main
git log -1 --oneline
```

Do not commit credentials, downloaded PDFs, Qdrant data, PostgreSQL data,
backups, or a production `.env` file.

## Current Product State

| Area | Status | Notes |
|---|---|---|
| Architecture | complete | Next.js -> ASP.NET Core API -> internal Python RAG services -> PostgreSQL/Qdrant |
| Public backend boundary | complete | Only ASP.NET Core is public through Next.js `/api/*`; `rag-query` stays private |
| Auth | complete for current decision | Email/password and Google OAuth; email verification is intentionally excluded |
| Ingestion | complete | BPS metadata, PDF download, PyMuPDF extraction, cleaning, chunking, embedding, indexing, logs |
| Retrieval | complete | Dense + BM25 sparse, RRF, final Top-10, citation payloads, sufficiency/refusal guard |
| Chat/admin UI | complete | Citation-first chat, history, document search, admin ingestion trigger/status |
| P0 hardening | implemented | Production Compose overlay, secret boundaries, persistent Data Protection keys, retries, heartbeat recovery, backup/restore, release preflight |
| Evaluation baseline | complete | 100-sample live RAGAS baseline completed (report: `evaluations/ragas_report.json`); 20-question manual audit pending |
| Public production launch | blocked | VPS deployment, reverse proxy, migration execution, backup verification, and manual audit remain open |

## Corpus And Runtime Data

The Git repository does **not** contain application runtime data.

The last local corpus snapshot was:

| Item | Snapshot |
|---|---:|
| BPS DKI Jakarta publications returned by latest source | 263 |
| Indexed documents | 263 |
| PostgreSQL chunks | 98,974 |
| Qdrant points | 98,974 |
| Target Qdrant collection | `ringkas_chunks_cf_qwen3_embedding_v2` |
| Dense vector contract | 1024 dimensions, cosine |
| Embedding model | `@cf/qwen/qwen3-embedding-0.6b` |
| Sparse retrieval | FastEmbed `Qdrant/bm25` with Qdrant IDF |

An older snapshot mentioned 264 documents. Do not silently claim 264 is final.
Reconcile the difference with source evidence or explicitly record 263 as the
approved snapshot before a public launch.

For the VPS, choose one path:

1. Restore a verified backup containing PostgreSQL, Qdrant, PDFs, and Data
   Protection keys.
2. Start with empty persistent storage, apply migrations, then trigger a new
   admin ingestion job and wait for it to complete.

Do not copy only Qdrant or only PostgreSQL: citation integrity requires the
database metadata/chunks, Qdrant points, and PDF storage to remain consistent.

## Non-Negotiable Boundaries

- Keep ASP.NET Core as the only public backend.
- Keep `rag-query` and `rag-worker` internal. Never add public host ports for
  `rag-query`, PostgreSQL, or Qdrant.
- Keep PostgreSQL, Qdrant, PyMuPDF, and Cloudflare Qwen3 embeddings.
- Do not add OCR, production Docling, public user uploads, real-time BPS
  database querying, a public third-party API, payments, mobile native apps,
  fine-tuning, or a replacement backend/database/vector store.
- Preserve citation, source sufficiency, limitation, refusal, and
  no-fabrication guards.
- Do not hardcode or invent provider limits, model IDs, credentials, domain
  names, quota values, deployment capacity, or evaluation results.

The project rules are in `AGENTS.md`. Read these source-of-truth files before
editing application behavior:

```text
docs/RINGKAS_PROJECT_BRIEF.md
docs/RINGKAS_PRD.md
docs/RINGKAS_SRD.md
docs/RINGKAS_TECHNICAL_SPEC.md
docs/RINGKAS_TASKS.md
docs/PHASE6_RUNBOOK.md
docs/PHASE7_REVIEW.md
AGENTS.md
```

## Production Configuration

Use the base Compose file plus its production overlay:

```bash
docker compose --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.production.yml \
  config --quiet
```

Create an untracked `.env` from `.env.production.example`. Replace every
`<required...>` value with a real secret/value. The essential configuration is:

```text
RINGKAS_DATA_ROOT=/data/ringkas
POSTGRES_PASSWORD=
DATABASE_URL=postgresql://ringkas:<url-encoded-password>@postgres:5432/ringkas

QDRANT_COLLECTION_NAME=ringkas_chunks_cf_qwen3_embedding_v2
QDRANT_DENSE_VECTOR_SIZE=1024
QDRANT_DENSE_DISTANCE=cosine

PDF_STORAGE_PATH=/data/ringkas/pdfs
PDF_ALLOWED_HOSTS=
BPS_API_KEY=

CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL=@cf/qwen/qwen3-embedding-0.6b
CLOUDFLARE_WORKERS_AI_EMBEDDING_SECONDARY_ACCOUNT_ID=
CLOUDFLARE_WORKERS_AI_EMBEDDING_SECONDARY_API_TOKEN=
CLOUDFLARE_WORKERS_AI_EMBEDDING_TERTIARY_ACCOUNT_ID=
CLOUDFLARE_WORKERS_AI_EMBEDDING_TERTIARY_API_TOKEN=

RAG_INTERNAL_TOKEN=<same non-whitespace token of at least 32 chars for API and rag-query>
DATA_PROTECTION_KEYS_PATH=/data/ringkas/keys

NVIDIA_NIM_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
REGISTERED_DAILY_QUOTA=<positive integer decided by the operator>

INGESTION_RUNNING_JOB_TIMEOUT_SECONDS=21600
INGESTION_DOCUMENT_RETRY_COUNT=2
OCR_ENABLED=false
```

`PDF_ALLOWED_HOSTS` must contain exact allowed PDF hosts. Do not use wildcards.
Keep `QDRANT_DENSE_DISTANCE=cosine`; collection setup rejects an undefined or
incompatible vector contract.

The production overlay enforces these boundaries:

- PostgreSQL and Qdrant host ports are removed.
- Web binds only to `127.0.0.1:${WEB_PORT}`.
- API runs as `Production` and requires Data Protection keys under persistent
  storage.
- The ingestion worker requires the BPS, Cloudflare, Qdrant, PDF, retry, and
  recovery configuration.

## HTTPS And Reverse Proxy

The repository intentionally does not choose a proxy vendor, certificate
authority, or domain. Use the VPS operator's approved HTTPS reverse proxy.

The proxy must terminate TLS and forward only to:

```text
http://127.0.0.1:${WEB_PORT}
```

It must preserve `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`; redirect
HTTP to HTTPS; and leave PostgreSQL, Qdrant, and `rag-query` inaccessible from
the public network. See `infra/REVERSE_PROXY.md`.

After choosing the public HTTPS domain, add exactly this Google Console redirect
URI:

```text
https://<public-domain>/api/auth/google/provider-callback
```

Google OAuth creates/signs in users only when Google reports a verified email.
It deliberately does not automatically link a Google identity to an existing
email/password account merely because the email matches.

## Deployment Procedure

### 1. Prepare persistent directories

```bash
sudo install -d -m 0700 -o "$(id -u)" -g "$(id -g)" \
  /data/ringkas/postgres /data/ringkas/pdfs /data/ringkas/qdrant /data/ringkas/keys
```

Use the actual service account/group if Docker runs under another account.
The directory must survive container recreation.

### 2. Validate and start core services

```bash
docker compose --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.production.yml \
  up -d --build

docker compose --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.production.yml \
  ps
```

The ingestion worker is intentionally optional. It only runs with its Compose
profile:

```bash
docker compose --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.production.yml \
  --profile ingestion up -d rag-worker
```

Stop it once all planned ingestion jobs are terminal:

```bash
docker compose --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.production.yml \
  stop rag-worker
```

### 3. Apply migrations through the private Compose network

The current API startup does **not** auto-run EF migrations. The production
overlay intentionally hides PostgreSQL from the VPS host, so do not run
`dotnet ef database update` on the host using `@postgres`; that Docker hostname
is not host-resolvable.

Before first traffic, execute the one-shot EF migration procedure inside the
private Compose network:

```bash
docker compose --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.production.yml \
  run --rm \
  -v "${PWD}:/app" \
  -w /app \
  mcr.microsoft.com/dotnet/sdk:9.0 \
  sh -c "dotnet tool install --global dotnet-ef && export PATH=\"\$PATH:/root/.dotnet/tools\" && dotnet ef database update --project apps/api/Ringkas.Api.csproj --connection \"\$DATABASE_URL\""
```

Then verify that all migrations, including `20260810122540_AddIngestionJobHeartbeat`,
are successfully recorded:

```bash
docker compose --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.production.yml \
  exec postgres psql -U ringkas -d ringkas -c "SELECT \"MigrationId\" FROM \"__EFMigrationsHistory\" ORDER BY \"MigrationId\";"
```

This applies migrations cleanly without exposing PostgreSQL publicly or editing
the schema manually.

### 4. Populate or restore the corpus

For a restore, follow `scripts/backup/README.md`. Restore is destructive and
requires `CONFIRM_RESTORE=YES`.

For a clean deployment, bootstrap an administrator, trigger a scoped ingestion
job through the admin endpoint/UI, start the `ingestion` profile, and observe
its status/logs until terminal. `force_reprocess` is not supported. Failed jobs
are retried by creating a new allowed job, not by bypassing the documented flow.

The worker has:

- document-level bounded retry/backoff;
- a `heartbeat_at` lease while processing;
- startup recovery that returns stale `running` jobs to `queued` after
  `INGESTION_RUNNING_JOB_TIMEOUT_SECONDS`.

## Required Operational Checks

Run the release preflight only after core services are running and intended
ingestion jobs have completed:

```bash
export ENV_FILE="$PWD/.env"
export COMPOSE_FILE="$PWD/infra/docker-compose.yml"
export COMPOSE_OVERRIDE_FILE="$PWD/infra/docker-compose.production.yml"
bash scripts/release/preflight.sh
```

Then perform these manual smoke checks through the public HTTPS origin:

1. Confirm web, API, PostgreSQL, Qdrant, and `rag-query` health.
2. Confirm PostgreSQL/Qdrant/`rag-query` are not publicly reachable.
3. Register/login with email-password; email verification remains intentionally
   unimplemented.
4. Complete Google OAuth and confirm the callback lands on the requested local
   application path.
5. Submit a supported DKI Jakarta question. It must return a substantive answer
   with citations containing title, year, region, page when available, URL, and
   excerpt.
6. Submit an unsupported future question, for example September 2099. It must
   return `insufficient` and require refusal rather than inventing evidence.
7. Trigger a small ingestion job and confirm completion/logs; verify a retrieved
   chunk maps to both PostgreSQL metadata and Qdrant.
8. Create one backup, copy it away from the VPS, and test restore on a disposable
   environment before calling the VPS deploy recoverable.

## Backup And Restore

Backups include PostgreSQL, Qdrant, PDFs, and Data Protection keys:

```bash
export RINGKAS_DATA_ROOT=/data/ringkas
export BACKUP_DIR=/data/ringkas-backups
export ENV_FILE="$PWD/.env"
export COMPOSE_OVERRIDE_FILE="$PWD/infra/docker-compose.production.yml"
bash scripts/backup/backup.sh
```

The backup briefly stops Qdrant for a consistent filesystem copy. Copy the
timestamped backup directory to storage outside the VPS. See
`scripts/backup/README.md` before any restore.

## Release Gates Still Open

These are blockers for public production, not reasons to rewrite completed P0
code:

| Gate | Required evidence/action |
|---|---|
| VPS networking | Public domain, HTTPS proxy, firewall, and private service-port verification |
| EF migration execution | One-shot migration procedure inside the private Compose network; verify `AddIngestionJobHeartbeat` is applied |
| Secrets | Real untracked production `.env`; no fallback/default secrets |
| OAuth | Google Console credentials and public callback URI tested |
| Recovery | Backup copied off-host and restore tested on a disposable environment |
| Evaluation | Full 100-sample live RAGAS baseline completed (300/300 finite metrics on Cloudflare `@cf/openai/gpt-oss-120b`, report at `evaluations/ragas_report.json`: Faithfulness 0.3634, Context Precision 0.0614, Context Recall 0.1447); manual audit of 20 questions in `services/rag-worker/manual_audit_template.csv` remains pending |
| Corpus scope | Resolve and document 263 vs 264 publication snapshot |
| Provider operations | Record actual provider terms/limits/cost decisions; do not invent them |
| Quota | Operator selects a positive `REGISTERED_DAILY_QUOTA`; current limiter remains in-memory and resets on API restart |

Until all gates are closed, call the deployment `staging` or `beta`, not full
public production.

Note on evaluator selection: The full 100-sample live RAGAS baseline was completed
exclusively using Cloudflare Workers AI (`@cf/openai/gpt-oss-120b`) with multi-account
failover across Primary, Secondary, and Tertiary accounts, maintaining a single
unmixed judge. DeepSeek is supported in the codebase as an evaluator option via
`RAGAS_EVALUATOR_PROVIDER=deepseek`, but was not used for the production baseline.

## OpenCode VPS Execution Checklist & Step-by-Step Runbook

When continuing in OpenCode on the target VPS host, follow these exact phases in order:

### Phase 1: Checkout and Directory Preparation
1. Clone the repository and checkout `main`:
   ```bash
   git clone https://github.com/haikalthrq/RINGKAS.git
   cd RINGKAS
   git pull --ff-only origin main
   git log -1 --oneline
   ```
2. Create isolated persistent storage directories with restricted permissions (`0700`):
   ```bash
   sudo install -d -m 0700 -o "$(id -u)" -g "$(id -g)" \
     /data/ringkas/postgres /data/ringkas/pdfs /data/ringkas/qdrant /data/ringkas/keys
   ```

### Phase 2: Production Environment (`.env`)
1. Create untracked `.env` from template:
   ```bash
   cp .env.production.example .env
   chmod 600 .env
   ```
2. Fill real production secrets:
   - Strong `POSTGRES_PASSWORD` and matching `DATABASE_URL`
   - High-entropy `RAG_INTERNAL_TOKEN` (>= 32 chars)
   - Real `BPS_API_KEY`, `PDF_ALLOWED_HOSTS`
   - Real Cloudflare credentials (`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, etc.)
   - Real `NVIDIA_NIM_API_KEY`
   - Real Google OAuth credentials (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`)
   - Operator-defined `REGISTERED_DAILY_QUOTA` (e.g. 50)
3. Validate Compose configuration:
   ```bash
   docker compose --env-file .env \
     -f infra/docker-compose.yml \
     -f infra/docker-compose.production.yml \
     config --quiet
   ```

### Phase 3: Service Startup & EF Core Database Migrations
1. Start core services:
   ```bash
   docker compose --env-file .env \
     -f infra/docker-compose.yml \
     -f infra/docker-compose.production.yml \
     up -d --build
   ```
2. Apply database migrations inside the private Compose network:
   ```bash
   docker compose --env-file .env \
     -f infra/docker-compose.yml \
     -f infra/docker-compose.production.yml \
     run --rm \
     -v "${PWD}:/app" \
     -w /app \
     mcr.microsoft.com/dotnet/sdk:9.0 \
     sh -c "dotnet tool install --global dotnet-ef && export PATH=\"\$PATH:/root/.dotnet/tools\" && dotnet ef database update --project apps/api/Ringkas.Api.csproj --connection \"\$DATABASE_URL\""
   ```
3. Verify migration record:
   ```bash
   docker compose --env-file .env \
     -f infra/docker-compose.yml \
     -f infra/docker-compose.production.yml \
     exec postgres psql -U ringkas -d ringkas -c "SELECT \"MigrationId\" FROM \"__EFMigrationsHistory\" ORDER BY \"MigrationId\";"
   ```
   (Must include `20260810122540_AddIngestionJobHeartbeat`).

### Phase 4: Corpus Population / Ingestion
Choose ONE approach:
- **Approach A (Restore from backup)**:
  Follow `scripts/backup/README.md` and run `bash scripts/backup/restore.sh <backup-archive>`.
- **Approach B (Fresh ingestion)**:
  Start ingestion worker with profile:
  ```bash
  docker compose --env-file .env \
    -f infra/docker-compose.yml \
    -f infra/docker-compose.production.yml \
    --profile ingestion up -d rag-worker
  ```
  Trigger initial ingestion job via admin endpoint or UI, monitor worker logs (`docker compose logs -f rag-worker`), and stop `rag-worker` once completed.

### Phase 5: Reverse Proxy & Public Domain
1. Configure Caddy or Nginx according to `infra/REVERSE_PROXY.md`:
   - Terminate TLS with valid certificate (e.g. Let's Encrypt).
   - Reverse proxy exclusively to `http://127.0.0.1:${WEB_PORT}`.
   - Forward headers: `Host`, `X-Forwarded-For`, `X-Forwarded-Proto`.
   - Never expose ports 5432, 6333, or 8000 to public network.
2. In Google Cloud Console, register the OAuth callback URL:
   `https://<public-domain>/api/auth/google/provider-callback`

### Phase 6: Release Preflight & Operational Smoke Checks
1. Run automated preflight:
   ```bash
   export ENV_FILE="$PWD/.env"
   export COMPOSE_FILE="$PWD/infra/docker-compose.yml"
   export COMPOSE_OVERRIDE_FILE="$PWD/infra/docker-compose.production.yml"
   bash scripts/release/preflight.sh
   ```
2. Execute the 8 manual smoke checks described in "Required Operational Checks".

### Phase 7: Off-host Backup & Disaster Recovery Drill
1. Take a backup:
   ```bash
   export RINGKAS_DATA_ROOT=/data/ringkas
   export BACKUP_DIR=/data/ringkas-backups
   bash scripts/backup/backup.sh
   ```
2. Copy backup archive to off-host storage.
3. Test restoration on a test/staging instance to verify recovery capability.

### Phase 8: Complete 20-Question Manual Audit (Gate D-09)
1. Open `services/rag-worker/manual_audit_template.csv`.
2. Evaluate questions `q-001` through `q-020` against ground-truth BPS DKI Jakarta publications.
3. Record accuracy checks (`citation_correctness`, `groundedness`, `number_accuracy`, `period_accuracy`, `region_accuracy`, `unit_accuracy`, `definition_accuracy`, `page_correctness`, `source_correctness`, `reviewer_verdict`, `reviewer_notes`).
4. Update `audit_status` from `pending` to `verified` for all 20 questions.

## Commands For Code Changes

Only change code if the VPS task requires it. Before editing, read the relevant
task in `docs/RINGKAS_TASKS.md` and the applicable source-of-truth documents.
Keep changes minimal and preserve the architecture/grounding rules.

Run the appropriate verification before commit:

```bash
git diff --check
docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.production.yml config --quiet
dotnet test tests/api/Ringkas.Api.Tests.csproj --no-restore
dotnet build apps/api/Ringkas.Api.csproj --no-restore
uv run --project services/rag-worker --extra test --frozen pytest
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

## Reference Files

| Need | File |
|---|---|
| Production variable checklist | `.env.production.example` |
| Production Compose overlay | `infra/docker-compose.production.yml` |
| Reverse-proxy contract | `infra/REVERSE_PROXY.md` |
| Backup/restore procedure | `scripts/backup/README.md` |
| Release preflight | `scripts/release/README.md` |
| Evaluation and quota runbook | `docs/PHASE6_RUNBOOK.md` |
| Review decisions and remaining blockers | `docs/PHASE7_REVIEW.md` |
| Agent constraints | `AGENTS.md` |
