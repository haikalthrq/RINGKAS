# RINGKAS RAG Worker

Internal Python process for polling ingestion jobs from PostgreSQL. It is not an
HTTP service and does not expose a port.

The default process performs non-mutating queue observation at the configured poll
interval. It never claims jobs when no ingestion processor is configured. Atomic
claim is available to an injected future processor, but processing activation is
reserved for the ingestion processor task.

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
