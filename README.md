# RINGKAS

RINGKAS is a planned MVP for retrieval-based Q&A over BPS statistical publications.

## Baseline Docs

- [Project Brief](docs/RINGKAS_PROJECT_BRIEF.md)
- [PRD](docs/RINGKAS_PRD.md)
- [SRD](docs/RINGKAS_SRD.md)
- [Technical Spec](docs/RINGKAS_TECHNICAL_SPEC.md)
- [Tasks](docs/RINGKAS_TASKS.md)
- [Agent Rules](docs/RINGKAS_AGENTS.md)

## Architecture Guardrails

- Main backend: ASP.NET Core.
- Frontend: React + Vite.
- Internal RAG worker: Python only, not a public backend.
- Database: PostgreSQL.
- Vector database: Qdrant.
- Deployment: one VPS with Docker Compose.
- PDF storage: `/data/ringkas/pdfs`.
- MVP is text-first.
- OCR is out of scope.
- Do not add features that are not defined in the baseline docs.

## Status

This repository currently documents the MVP plan and implementation backlog. It does not claim completed product features.
