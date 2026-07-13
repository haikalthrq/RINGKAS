# RINGKAS

RINGKAS is a citation-first RAG application for BPS publications. The product
uses Next.js as the presentation layer, ASP.NET Core as the only public backend,
and internal Python services for ingestion and retrieval.

This README records the accepted live evidence for T-0607 ingestion and T-0608
chat. It does not replace the task status maintained by the Supervisor.

## Architecture

- `apps/web`: Next.js + TypeScript App Router presentation layer and API consumer.
- `apps/api`: ASP.NET Core API for auth, roles, chat, citations, admin ingestion, quotas, and logging.
- `services/rag-worker`: internal Python worker for BPS ingestion, PyMuPDF, chunking, Cloudflare embedding, PostgreSQL metadata, and Qdrant indexing.
- `rag-query`: private Python retrieval HTTP adapter on the Compose network.
- PostgreSQL: Identity, chat history, document/chunk metadata, jobs, and logs.
- Qdrant: versioned dense collection for the approved Cloudflare embedding model.
- `infra/docker-compose.yml`: local Compose topology.

Next.js never accesses PostgreSQL or Qdrant directly. The Python worker and
`rag-query` service are internal-only; ASP.NET Core is the public backend.

## Prerequisites

- Docker Desktop with Compose.
- .NET 10 SDK and `dotnet-ef`.
- Python 3.12+ and `uv` for worker checks.
- Node.js/npm for non-container web development.
- Local provider and database configuration. Keep all values in an untracked
  `.env`; never put credentials, cookies, passwords, tokens, or downloaded PDFs
  in documentation or source control.

## Configuration

Create the local file:

```powershell
Copy-Item .env.example .env
```

Required environment-variable names are listed below. Set values locally; this
document intentionally lists names rather than credentials or token values.

Runtime and storage:

```text
ASPNETCORE_ENVIRONMENT
WEB_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
DATABASE_URL
QDRANT_URL
QDRANT_API_KEY
QDRANT_COLLECTION_NAME
QDRANT_DENSE_VECTOR_SIZE
PDF_STORAGE_PATH
```

BPS and ingestion:

```text
BPS_API_KEY
BPS_BASE_URL
BPS_PUBLICATIONS_PATH
BPS_PUBLICATION_KEYWORD
INGESTION_POLL_INTERVAL_SECONDS
CHUNK_SIZE_MIN
CHUNK_SIZE_MAX
CHUNK_OVERLAP_PERCENT
OCR_ENABLED
```

Embedding and private retrieval:

```text
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL
RAG_QUERY_BASE_URL
RAG_QUERY_ALLOWED_AUTHORITIES
RAG_QUERY_TIMEOUT_SECONDS
RAG_INTERNAL_TOKEN
```

Generation:

```text
NVIDIA_NIM_API_KEY
NVIDIA_NIM_GENERATION_MODEL
NVIDIA_NIM_GENERATION_BASE_URL
NVIDIA_NIM_GENERATION_ALLOWED_HOSTS
NVIDIA_NIM_GENERATION_TIMEOUT_SECONDS
NVIDIA_NIM_GENERATION_SECONDARY_MODEL
NVIDIA_NIM_GENERATION_LIGHTWEIGHT_MODEL
CLOUDFLARE_WORKERS_AI_GENERATION_MODEL
CLOUDFLARE_WORKERS_AI_GENERATION_TIMEOUT_SECONDS
CLOUDFLARE_WORKERS_AI_EXPERIMENTAL_MODEL
```

Auth, OAuth, and quotas:

```text
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
AUTH_SECRET
GUEST_PROMPT_QUOTA
REGISTERED_DAILY_QUOTA
```

The live-verified embedding dimension is `1024` for
`@cf/qwen/qwen3-embedding-0.6b`. Changing the embedding model requires live
dimension verification, a new versioned collection, and a full reindex.

The generation order is locked exactly as follows:

1. `nvidia/nemotron-3-nano-30b-a3b`
2. `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
3. `mistralai/mistral-small-4-119b-2603`
4. `nvidia/nemotron-mini-4b-instruct`
5. `@cf/meta/llama-4-scout-17b-16e-instruct`

## Local Startup

Render and validate Compose before starting services:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml config --quiet
```

Apply all EF Core migrations using the same local `DATABASE_URL` that points to
the Compose PostgreSQL service:

```powershell
dotnet ef database update --project apps/api/Ringkas.Api.csproj --startup-project apps/api/Ringkas.Api.csproj
```

Start the full topology and inspect service state:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml ps
```

The public smoke base URL is `http://localhost:3000`. The web container rewrites
`/api/*` to ASP.NET Core. `rag-query` has no host port and must remain private.

## Admin Bootstrap

Registration creates the ordinary `user` role. API startup seeds the `guest`,
`user`, `admin`, and `system_maintainer` roles. Register a disposable local
account, then have a trusted database operator promote it to `admin` without
printing the password or account identifiers in logs:

```powershell
curl.exe -s -c admin.cookies -H "Content-Type: application/json" -d '{"email":"<temporary-admin-email>","password":"<temporary-password>"}' http://localhost:3000/api/auth/register | Out-Null
```

Run the role assignment inside PostgreSQL. Select the role by name; do not copy
or document role IDs:

```sql
BEGIN;
INSERT INTO "AspNetUserRoles" ("UserId", "RoleId")
SELECT u."Id", r."Id"
FROM "AspNetUsers" AS u
JOIN "AspNetRoles" AS r ON r."Name" = 'admin'
WHERE u."Email" = '<temporary-admin-email>'
ON CONFLICT DO NOTHING;
COMMIT;
```

Log in again after promotion so the cookie contains the role claim:

```powershell
curl.exe -s -c admin.cookies -b admin.cookies -H "Content-Type: application/json" -d '{"email":"<temporary-admin-email>","password":"<temporary-password>"}' http://localhost:3000/api/auth/login | Out-Null
```

## Ingestion Smoke Flow

Trigger one admin-authorized job through the public HTTP path:

```powershell
$job = curl.exe -s -b admin.cookies -H "Content-Type: application/json" -d '{"region":"DKI Jakarta","year_start":2022,"year_end":2026,"max_documents":1,"force_reprocess":false}' http://localhost:3000/api/admin/ingestion/jobs | ConvertFrom-Json
[pscustomobject]@{ JobIdPresent = -not [string]::IsNullOrWhiteSpace($job.id); JobStatus = $job.status }
```

Poll the returned job until `completed` or `failed`:

```powershell
$jobStatus = curl.exe -s -b admin.cookies http://localhost:3000/api/admin/ingestion/jobs/<job-id> | ConvertFrom-Json
[pscustomobject]@{ JobStatus = $jobStatus.status; ErrorPresent = -not [string]::IsNullOrWhiteSpace($jobStatus.error_summary) }
```

For a live run, configure the official BPS list endpoint
`https://webapi.bps.go.id/v1/api/list`, model `publication`, DKI Jakarta domain
`3100`, Indonesian language, and query-key authentication. Set
`BPS_PUBLICATION_KEYWORD` to the approved publication keyword locally; never
document the BPS key value.

Verify the completed job through all storage boundaries:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec -T postgres psql -U <postgres-user> -d <postgres-database> -c "SELECT title, publication_year, region, page_count, ingestion_status FROM documents WHERE title = 'Profil Kemiskinan Provinsi DKI Jakarta 2025';"
docker compose --env-file .env -f infra/docker-compose.yml exec -T postgres psql -U <postgres-user> -d <postgres-database> -c "SELECT count(*) FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE title = 'Profil Kemiskinan Provinsi DKI Jakarta 2025');"
$qdrant = Invoke-RestMethod http://localhost:6333/collections/ringkas_chunks_cf_qwen3_embedding_v1
[pscustomobject]@{ Status = 200; CollectionStatus = $qdrant.result.status; Points = $qdrant.result.points_count; Distance = $qdrant.result.config.params.vectors.distance }
```

The private retrieval check must return HTTP 200, the preferred publication
title and relevant content, and 10 citations. Do not print the bearer token or
raw excerpts when recording the check. `rag-query` is reached from inside the
Compose network; its internal contract is `POST /retrieve` with the configured
`RAG_INTERNAL_TOKEN`.

Run the check inside the private container and print only sanitized metadata:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec -T rag-query python -c "import json, os, urllib.request; request=urllib.request.Request('http://127.0.0.1:8081/retrieve', data=json.dumps({'question':'<known-answer-question>'}).encode(), headers={'Authorization':'Bearer '+os.environ['RAG_INTERNAL_TOKEN'],'Content-Type':'application/json'}); response=urllib.request.urlopen(request); payload=json.load(response); print(response.status, payload['citations'][0]['title'], bool(payload['citations'][0]['snippet']), len(payload['citations']))"
```

The accepted sanitized result was HTTP 200, preferred title, content present,
and 10 citations.

Accepted T-0607 result:

- The admin HTTP request reached PostgreSQL, the real worker, and official BPS ingestion.
- The preferred publication was `Profil Kemiskinan Provinsi DKI Jakarta 2025`.
- The PDF host was `webapi.bps.go.id`; PyMuPDF extracted 82 pages.
- The pipeline produced 192 chunks and Cloudflare vectors with dimension 1024.
- Qdrant contained 192 points, reported green status, and used cosine distance.
- Retrieval returned HTTP 200 with the preferred title/content and 10 citations.
- The corrective run intentionally retained this corpus for T-0608.

## Chat And Citation Smoke Flow

Ask a supported question only after the indexed corpus and private retrieval
path are ready:

```powershell
$chat = curl.exe -s -b admin.cookies -H "Content-Type: application/json" -d '{"message":"<known-answer-question>"}' http://localhost:3000/api/chat | ConvertFrom-Json
[pscustomobject]@{ Status = 200; Substantive = -not [string]::IsNullOrWhiteSpace($chat.answer); Provider = $chat.provider; CitationCount = @($chat.citations).Count }
```

Use a citation `chunk_id` from the response to verify the source endpoint. Keep
the response in a local variable and print only metadata while checking it:

```powershell
$chat = curl.exe -s -b admin.cookies -H "Content-Type: application/json" -d '{"message":"<known-answer-question>"}' http://localhost:3000/api/chat | ConvertFrom-Json
$citation = $chat.citations[0]
$source = curl.exe -s -b admin.cookies "http://localhost:3000/api/sources/chunks/$($citation.chunk_id)" | ConvertFrom-Json
[pscustomobject]@{ Status = 200; TitleMatches = $source.documentTitle -eq $citation.title; YearMatches = $source.publicationYear -eq $citation.year; RegionMatches = $source.region -eq $citation.region; PagesMatch = $source.pageStart -eq $citation.page_start -and $source.pageEnd -eq $citation.page_end; HttpsSource = $source.sourceUrl.StartsWith('https://'); ExcerptPresent = -not [string]::IsNullOrWhiteSpace($source.excerpt) }
```

Accepted T-0608 supported-query result:

- Public `http://localhost:3000/api/chat` returned HTTP 200 through ASP.NET Core and private `rag-query`.
- The response was substantive, used provider `nvidia_nim`, and contained 10 citations.
- Source endpoint metadata matched citation title, year, region, page range, HTTPS URL, and excerpt; citation labels resolved.
- The primary provider succeeded, so generation failover was not live-exercised.

Repair required before that accepted run: local `rag-query` configuration, DNS
resolution for the private service authority, and shared API/`rag-query`
internal-token configuration were corrected. No token values belong in this
documentation.

Verify refusal behavior with a separate disposable request:

```powershell
$unsupported = curl.exe -s -b admin.cookies -H "Content-Type: application/json" -d '{"message":"<unsupported-query-about-September-2099>"}' http://localhost:3000/api/chat | ConvertFrom-Json
[pscustomobject]@{ Status = 200; SourceSufficiency = $unsupported.source_sufficiency; Provider = $unsupported.provider; MentionsSeptember2099 = [bool]($unsupported.answer -match 'September 2099') }
```

Expected and accepted result: HTTP 200, insufficiency/refusal, no provider,
and no September 2099 or invented facts in the response.

## Cleanup

Remove only temporary users, sessions, messages, ingestion jobs, and job logs.
Keep the accepted indexed corpus and Qdrant collection for subsequent smoke
checks. Use a transaction and the disposable account marker locally:

```sql
BEGIN;
DELETE FROM chat_messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE user_id IN (SELECT "Id" FROM "AspNetUsers" WHERE "Email" = '<temporary-admin-email>'));
DELETE FROM chat_sessions WHERE user_id IN (SELECT "Id" FROM "AspNetUsers" WHERE "Email" = '<temporary-admin-email>');
DELETE FROM ingestion_logs WHERE job_id IN (SELECT id FROM ingestion_jobs WHERE requested_by_user_id IN (SELECT "Id" FROM "AspNetUsers" WHERE "Email" = '<temporary-admin-email>'));
DELETE FROM ingestion_jobs WHERE requested_by_user_id IN (SELECT "Id" FROM "AspNetUsers" WHERE "Email" = '<temporary-admin-email>');
DELETE FROM "AspNetUserRoles" WHERE "UserId" IN (SELECT "Id" FROM "AspNetUsers" WHERE "Email" = '<temporary-admin-email>');
DELETE FROM "AspNetUsers" WHERE "Email" = '<temporary-admin-email>';
COMMIT;
```

Delete local cookie files and remove containers without volumes if the corpus
must remain available:

```powershell
Remove-Item -LiteralPath admin.cookies -ErrorAction SilentlyContinue
docker compose --env-file .env -f infra/docker-compose.yml down
```

The accepted T-0607 corrective run retained the corpus. T-0608 cleanup removed
temporary users, sessions, and messages while retaining that corpus.

## Evaluation, Quotas, And Limitations

- The evaluation dataset has 100 pending slots and the manual audit template has 20 pending rows. No live RAGAS baseline or completed manual audit is claimed.
- Automated scores are baseline evidence only and cannot establish comprehensive accuracy.
- OCR is not implemented; PDFs without a usable text layer are unsupported.
- Docling is not a production parser.
- Sparse retrieval remains a placeholder; do not claim BM25.
- BPS/provider availability, limits, and terms remain operational prerequisites; the accepted BPS endpoint, model, domain, language, and query-key contract are documented above.
- Guest quota and registered-user daily quota state are in memory; process restart resets counters and the registered quota value remains TBD when blank.
- Generation failover was not exercised in the accepted live chat run.
- Complex table extraction is best-effort.
- Do not claim comprehensive accuracy across BPS documents.

Focused local checks remain available:

```powershell
uv run --project services/rag-worker --extra test --frozen pytest services/rag-worker/tests/test_evaluation_dataset.py services/rag-worker/tests/test_ragas_harness.py services/rag-worker/tests/test_manual_audit.py
uv run --project services/rag-worker --frozen python -m ringkas_worker.ragas_harness --mode sample
dotnet test tests/api/Ringkas.Api.Tests.csproj --no-restore
dotnet build apps/api/Ringkas.Api.csproj --no-restore
docker compose --env-file .env -f infra/docker-compose.yml config --quiet
```
