# Phase 6 Runbook

This runbook is the reproducible Phase 6 implementation record. T-0607 and
T-0608 are recorded below using accepted sanitized live evidence. It does not
change task statuses.

## Evaluation Artifacts

- `services/rag-worker/evaluation_dataset.json` contains exactly 100 stable slots (`q-001` through `q-100`), pending until human verification.
- `services/rag-worker/ringkas_worker/evaluation_dataset.py` validates grounded evidence records.
- `services/rag-worker/manual_audit_template.csv` contains exactly 20 pending rows linked to `q-001` through `q-020`.
- `services/rag-worker/ringkas_worker/ragas_harness.py` has a deterministic no-secret fixture path and an explicit live RAGAS path.

The sample harness validates only its synthetic fixture and emits no metric
values. The initial MVP baseline label is reserved for a completed live RAGAS
evaluation. Manual audit is not complete until a human fills the 20 pending
rows.

## Quotas And Abuse Protection

- `GUEST_PROMPT_QUOTA` must remain exactly one. Guest state is partitioned by client IP and is in memory for the process lifetime.
- `REGISTERED_DAILY_QUOTA` is blank-disabled. A positive value enables an in-memory daily partition by authenticated user ID.
- Admin and system maintainer roles bypass only the registered daily quota; the short-window chat limiter still applies.
- Process restart resets in-memory quota counters.
- Admin ingestion POST and GET routes require `admin` or `system_maintainer` and use the named `AdminIngestion` limiter.
- Rejected requests return a structured HTTP 429 response without provider details or raw scores.

## Locked Generation Order

The configured generation attempts are locked exactly to this order:

1. `nvidia/nemotron-3-nano-30b-a3b`
2. `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
3. `mistralai/mistral-small-4-119b-2603`
4. `nvidia/nemotron-mini-4b-instruct`
5. `@cf/meta/llama-4-scout-17b-16e-instruct`

The first item is NVIDIA NIM primary. The second is the Cloudflare fallback;
the next two are NVIDIA reserve models and the last is the experimental
Cloudflare reserve. T-0608 used NVIDIA NIM successfully, so failover was not
live-exercised.

## Required Environment Names

Set values only in an untracked local `.env`. This list intentionally provides
environment-variable names, not credentials or secret values.

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
BPS_API_KEY
BPS_BASE_URL
BPS_PUBLICATIONS_PATH
BPS_PUBLICATION_KEYWORD
INGESTION_POLL_INTERVAL_SECONDS
CHUNK_SIZE_MIN
CHUNK_SIZE_MAX
CHUNK_OVERLAP_PERCENT
OCR_ENABLED
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
CLOUDFLARE_WORKERS_AI_EMBEDDING_MODEL
RAG_QUERY_BASE_URL
RAG_QUERY_ALLOWED_AUTHORITIES
RAG_QUERY_TIMEOUT_SECONDS
RAG_INTERNAL_TOKEN
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
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
AUTH_SECRET
GUEST_PROMPT_QUOTA
REGISTERED_DAILY_QUOTA
```

The accepted live embedding dimension is `1024` for the approved
`@cf/qwen/qwen3-embedding-0.6b` model. Reverify and reindex before changing
models. BPS authentication uses the documented `key` query parameter; never
record its value.

## Compose Startup And Migration

Create and validate local configuration:

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infra/docker-compose.yml config --quiet
```

Apply EF Core migrations with the same local database configuration:

```powershell
dotnet ef database update --project apps/api/Ringkas.Api.csproj --startup-project apps/api/Ringkas.Api.csproj
```

Start the complete topology:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
docker compose --env-file .env -f infra/docker-compose.yml ps
```

The public HTTP base is `http://localhost:3000`; Next.js rewrites `/api/*` to
ASP.NET Core. The API, worker, PostgreSQL, Qdrant, and `rag-query` communicate
inside Compose. `rag-query` has no public host port.

## Registration And Admin Role Bootstrap

API startup seeds `guest`, `user`, `admin`, and `system_maintainer`. Registration
creates a normal `user` account. Use a disposable account for a smoke run:

```powershell
curl.exe -s -c admin.cookies -H "Content-Type: application/json" -d '{"email":"<temporary-admin-email>","password":"<temporary-password>"}' http://localhost:3000/api/auth/register | Out-Null
```

After registration, a trusted database operator assigns the seeded `admin`
role by name. Do not expose PostgreSQL or record IDs/passwords:

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

Log in again to issue a cookie with the new role claim:

```powershell
curl.exe -s -c admin.cookies -b admin.cookies -H "Content-Type: application/json" -d '{"email":"<temporary-admin-email>","password":"<temporary-password>"}' http://localhost:3000/api/auth/login | Out-Null
```

## T-0607 Ingestion And Retrieval

Configure the official public BPS list contract locally:

- Endpoint: `https://webapi.bps.go.id/v1/api/list`.
- Model: `publication`.
- DKI Jakarta domain: `3100`.
- Language: `ind`.
- Authentication: query parameter `key`.
- `BPS_PUBLICATION_KEYWORD`: use the approved publication keyword locally; do not record its value.

Trigger one admin job:

```powershell
$job = curl.exe -s -b admin.cookies -H "Content-Type: application/json" -d '{"region":"DKI Jakarta","year_start":2022,"year_end":2026,"max_documents":1,"force_reprocess":false}' http://localhost:3000/api/admin/ingestion/jobs | ConvertFrom-Json
[pscustomobject]@{ JobIdPresent = -not [string]::IsNullOrWhiteSpace($job.id); JobStatus = $job.status }
```

Poll the returned job ID until it is terminal:

```powershell
$jobStatus = curl.exe -s -b admin.cookies http://localhost:3000/api/admin/ingestion/jobs/<job-id> | ConvertFrom-Json
[pscustomobject]@{ JobStatus = $jobStatus.status; ErrorPresent = -not [string]::IsNullOrWhiteSpace($jobStatus.error_summary) }
```

Verify PostgreSQL metadata and chunk count:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec -T postgres psql -U <postgres-user> -d <postgres-database> -c "SELECT title, publication_year, region, page_count, ingestion_status FROM documents WHERE title = 'Profil Kemiskinan Provinsi DKI Jakarta 2025';"
docker compose --env-file .env -f infra/docker-compose.yml exec -T postgres psql -U <postgres-user> -d <postgres-database> -c "SELECT count(*) FROM chunks WHERE document_id IN (SELECT id FROM documents WHERE title = 'Profil Kemiskinan Provinsi DKI Jakarta 2025');"
$qdrant = Invoke-RestMethod http://localhost:6333/collections/ringkas_chunks_cf_qwen3_embedding_v2
[pscustomobject]@{ Status = 200; CollectionStatus = $qdrant.result.status; Points = $qdrant.result.points_count; Distance = $qdrant.result.config.params.vectors.distance }
```

For private retrieval, send the sanitized known-answer request to
`POST http://127.0.0.1:8081/retrieve` from inside `rag-query`, using the token
already present in that container. Record only HTTP status, preferred title,
content-present boolean, and citation count. Never print the Authorization
header, token, or raw excerpt. The accepted retrieval result was HTTP 200 with
the preferred title/content and 10 citations.

The reproducible sanitized check is:

```powershell
docker compose --env-file .env -f infra/docker-compose.yml exec -T rag-query python -c "import json, os, urllib.request; request=urllib.request.Request('http://127.0.0.1:8081/retrieve', data=json.dumps({'question':'<known-answer-question>'}).encode(), headers={'Authorization':'Bearer '+os.environ['RAG_INTERNAL_TOKEN'],'Content-Type':'application/json'}); response=urllib.request.urlopen(request); payload=json.load(response); print(response.status, payload['citations'][0]['title'], bool(payload['citations'][0]['snippet']), len(payload['citations']))"
```

The accepted sanitized result was HTTP 200, preferred title, content present,
and 10 citations.

Accepted T-0607 evidence:

- Official BPS ingestion was reached through public admin HTTP, PostgreSQL, and the real worker.
- The preferred publication was `Profil Kemiskinan Provinsi DKI Jakarta 2025` from `webapi.bps.go.id`.
- PyMuPDF extracted 82 pages.
- The pipeline produced 192 chunks.
- Cloudflare embedding dimension was 1024.
- Qdrant reported 192 points, green status, and cosine distance.
- Retrieval returned HTTP 200 with preferred title/content and 10 citations.
- The corrective run intentionally retained this corpus for T-0608; temporary users and jobs were cleaned.

## T-0608 Chat, Source, And Refusal Verification

Use the public web path only after T-0607 has produced the retained indexed
corpus. Capture the response and print only sanitized metadata:

```powershell
$chat = curl.exe -s -b admin.cookies -H "Content-Type: application/json" -d '{"message":"<known-answer-question>"}' http://localhost:3000/api/chat | ConvertFrom-Json
[pscustomobject]@{ Status = 200; Substantive = -not [string]::IsNullOrWhiteSpace($chat.answer); Provider = $chat.provider; CitationCount = @($chat.citations).Count }
```

For the first returned citation, call the registered-user source endpoint with
its `chunk_id` and compare only metadata:

```powershell
$citation = $chat.citations[0]
$source = curl.exe -s -b admin.cookies "http://localhost:3000/api/sources/chunks/$($citation.chunk_id)" | ConvertFrom-Json
[pscustomobject]@{ Status = 200; TitleMatches = $source.documentTitle -eq $citation.title; YearMatches = $source.publicationYear -eq $citation.year; RegionMatches = $source.region -eq $citation.region; PagesMatch = $source.pageStart -eq $citation.page_start -and $source.pageEnd -eq $citation.page_end; HttpsSource = $source.sourceUrl.StartsWith('https://'); ExcerptPresent = -not [string]::IsNullOrWhiteSpace($source.excerpt) }
```

Compare metadata without recording raw source text. The accepted source check
matched title, year, region, page range, HTTPS URL, excerpt, and citation labels.

Accepted supported-query result:

- Public `http://localhost:3000/api/chat` returned HTTP 200 through ASP.NET Core and private `rag-query`.
- The answer was substantive, provider was `nvidia_nim`, and there were 10 citations.
- Source citation metadata matched the source endpoint.
- Failover was not exercised because the primary provider succeeded.

The run required a local `rag-query` repair: configuration, private-service DNS
authority, and shared API/`rag-query` token configuration were corrected. No
secret value is recorded here.

Verify the unsupported-query guard with a separate request:

```powershell
$unsupported = curl.exe -s -b admin.cookies -H "Content-Type: application/json" -d '{"message":"<unsupported-query-about-September-2099>"}' http://localhost:3000/api/chat | ConvertFrom-Json
[pscustomobject]@{ Status = 200; SourceSufficiency = $unsupported.source_sufficiency; Provider = $unsupported.provider; MentionsSeptember2099 = [bool]($unsupported.answer -match 'September 2099') }
```

Accepted unsupported-query result: HTTP 200, insufficiency/refusal, provider
none, and no September 2099 or invented facts.

## Cleanup Procedure

Delete only disposable smoke data, in dependency order: chat messages, chat
sessions, ingestion logs, ingestion jobs, user-role links, and temporary users.
Keep the accepted documents, chunks, PDFs, and Qdrant points for follow-up
checks. Do not delete the seeded roles or the retained corpus.

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

Remove local cookies and stop services without removing volumes:

```powershell
Remove-Item -LiteralPath admin.cookies -ErrorAction SilentlyContinue
docker compose --env-file .env -f infra/docker-compose.yml down
```

## Required Limitations And TBDs

- No OCR; scan PDFs without usable text are unsupported.
- No production Docling parser.
- Sparse retrieval is still a placeholder; do not claim BM25.
- Complex table extraction is best-effort.
- BPS/provider availability, limits, and terms remain prerequisites; the accepted BPS endpoint, model, domain, language, and query-key contract are fixed above.
- The evaluation dataset and 20% manual audit are not complete; no live RAGAS baseline is claimed.
- Quotas are in memory; process restarts reset counters and the registered daily quota value remains TBD when blank.
- Failover was not live-exercised in the accepted supported chat run.
- Automated or smoke-test evidence is not a claim of comprehensive accuracy.

## Focused Local Checks

```powershell
uv run --project services/rag-worker --extra test --frozen pytest services/rag-worker/tests/test_evaluation_dataset.py services/rag-worker/tests/test_ragas_harness.py services/rag-worker/tests/test_manual_audit.py
uv run --project services/rag-worker --frozen python -m ringkas_worker.ragas_harness --mode sample
dotnet test tests/api/Ringkas.Api.Tests.csproj --no-restore
dotnet build apps/api/Ringkas.Api.csproj --no-restore
docker compose --env-file .env -f infra/docker-compose.yml config --quiet
```
