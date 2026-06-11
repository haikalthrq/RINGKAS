# RINGKAS

RINGKAS is a web RAG project for BPS publication Q&A with mandatory citation.

## Status

This repository is in the foundation and planning stage. It is not a completed product yet, and this README does not claim that the backend, frontend, ingestion flow, retrieval pipeline, Docker Compose deployment, auth, or generation stack is already implemented.

## Architecture

- Frontend: Next.js + TypeScript dengan App Router.
- Main backend/API: ASP.NET Core.
- Internal processing service: Python RAG Worker.
- Database: PostgreSQL for auth, metadata, chat history, ingestion jobs, and logs.
- Vector database: Qdrant.
- MVP deployment: Docker Compose on a single VPS.
- Local PDF storage: `/data/ringkas/pdfs`.

## Source Of Truth

Follow these docs in order:

1. [Project Brief](docs/RINGKAS_PROJECT_BRIEF.md)
2. [PRD](docs/RINGKAS_PRD.md)
3. [SRD](docs/RINGKAS_SRD.md)
4. [Technical Spec](docs/RINGKAS_TECHNICAL_SPEC.md)
5. [Tasks](docs/RINGKAS_TASKS.md)
6. [Agent Rules](docs/RINGKAS_AGENTS.md)

These docs define the constraints for MVP scope, architecture, citation policy, and agent workflow.

## Local Setup Outline

Full runnable setup is not available yet. Current outline:

1. Review the source-of-truth docs above.
2. Copy `.env.example` to `.env` and fill in only the required local values.
3. Add or complete the service scaffolds under `apps/web`, `apps/api`, and `services/rag-worker`.
4. Use Docker Compose from `infra/` once the MVP infrastructure files exist.

## Non-Negotiable Constraints

- ASP.NET Core is the main backend/API.
- Python RAG Worker is internal processing only, not a public backend.
- Next.js + TypeScript dengan App Router adalah presentation layer; ASP.NET Core tetap main backend/API.
- PostgreSQL stores auth, metadata, chat history, ingestion jobs, and logs.
- Qdrant is the vector database.
- Docker Compose is the MVP deployment target.
- PDF storage stays at `/data/ringkas/pdfs`.
- MVP is text-first.
- OCR is not in MVP.
- PyMuPDF is the MVP parser.
- Docling is future-only, not the production parser.
- All substantive answers must include citation.
- If evidence is insufficient, the system must state the limitation or refuse the substantive answer.
