# RINGKAS RAG Worker

Internal Python process for polling ingestion jobs from PostgreSQL. It is not an
HTTP service and does not expose a port.

The default process performs non-mutating queue observation at the configured poll
interval. It never claims jobs when no ingestion processor is configured. The
existing processor remains fail-closed; the full T-0413 ingestion pipeline is not
active in this task. `MockTransport` is available as test injection. Production
construction uses `PdfDownloader.from_settings(settings)` without a transport,
which selects the validated production transport and enforces destination safety.
Its total PDF budget is checked before and after resolver, connection, redirect,
and stream phases, plus between chunks and after EOF. DNS remains subject to the
platform resolver, while an individual blocking read is bounded by the configured
read timeout; neither is interrupted with abandoned timeout threads.

Shutdown stops new observations/claims promptly while idle. An active database
query or future handler is not forcibly interrupted by this scaffold.

## Local run

```text
python -m venv .venv
python -m pip install -e ".[test]"
set DATABASE_URL=postgresql://ringkas:change-me-locally@localhost:5432/ringkas
python -m ringkas_worker
```

Copy `.env.example` to a local environment file only outside version control.

The processor preserves the existing schema and statuses. It has no automatic
retry, crash recovery, lease/heartbeat, force reprocess, sparse indexing, or
distributed PostgreSQL-Qdrant transaction. Concurrent checksum deduplication and
provider/model choices remain MVP limitations/TBD.

## Retrieval debug logging

The worker includes an injectable retrieval-debug logging foundation for developers.
It is disabled by default and is not yet wired to a complete chat or hybrid retrieval
orchestrator. When explicitly enabled, one bounded event may record query length and
representation status, resolved publication year and the presence of allowlisted text
filters, plus ordered rank/chunk/document summaries for available dense, sparse, fused,
and final stages. Candidate lists are capped independently.

Query and allowlisted textual filter previews may be recorded only with explicit
sensitive-text opt-in. Opted-in previews are bounded, normalized, and credential-redacted;
they are not unrestricted raw query logging. Candidate metadata such as source title,
topic, section heading, URLs, excerpts, vectors, and Qdrant payloads is always excluded.
Scores are also excluded by default and remain developer-only. Credentials, authorization
data, and user/session IDs are not logged. Logging failures are isolated and cannot affect
retrieval.
