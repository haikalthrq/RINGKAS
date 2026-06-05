# RINGKAS API Contract Placeholder

Status: documentation-only, planned surface

This file is a placeholder contract derived from `docs/RINGKAS_TECHNICAL_SPEC.md`.
It does not claim implementation status or final schema stability.

## Notes

- Final request/response shapes are still TBD unless explicitly listed in the Technical Spec.
- Retrieval scores are not exposed to general users in this contract.
- Chat responses must include citations and a source sufficiency value.
- Session vs JWT auth details remain TBD in implementation.

## Endpoint Groups

### Auth

Planned endpoints:

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/register` | Planned email-password registration |
| POST | `/api/auth/login` | Planned login |
| POST | `/api/auth/logout` | Planned logout |
| GET | `/api/auth/me` | Planned current session/profile lookup |
| GET | `/api/auth/google` | Planned Google OAuth start |
| GET | `/api/auth/google/callback` | Planned Google OAuth callback |

Auth/session mechanics: TBD.

### User/Profile

| Method | Path | Notes |
|---|---|---|
| GET | `/api/users/me` | Planned profile read |
| PATCH | `/api/users/me` | Planned basic profile update, if needed |

Profile fields: TBD, limited to basic user/profile data.

### Chat/Q&A

| Method | Path | Notes |
|---|---|---|
| POST | `/api/chat` | Planned grounded question answering |
| GET | `/api/chat/sessions` | Planned list of user chat sessions |
| GET | `/api/chat/sessions/{id}` | Planned read chat session |
| DELETE | `/api/chat/sessions/{id}` | Optional planned delete own session |

Minimal planned chat response shape from Technical Spec:

```json
{
  "answer": "string",
  "citations": [
    {
      "document_id": "uuid",
      "chunk_id": "uuid",
      "title": "string",
      "year": 2026,
      "region": "DKI Jakarta",
      "page_start": 1,
      "page_end": 2,
      "source_url": "https://...",
      "snippet": "string"
    }
  ],
  "source_sufficiency": "sufficient|partial|insufficient",
  "provider": "nvidia_nim|cloudflare_workers_ai"
}
```

Exact generation routing, refusal wording, and citation formatting: TBD.

### Document Search

| Method | Path | Notes |
|---|---|---|
| GET | `/api/documents/search` | Planned search by title/year/topic/keyword |
| GET | `/api/documents/{id}` | Planned document metadata detail |

Planned query params:

```text
q=keyword
year=2024
topic=poverty
page=1
page_size=20
```

Search ranking and filtering details: TBD.

### Citation/Source

| Method | Path | Notes |
|---|---|---|
| GET | `/api/sources/chunks/{chunkId}` | Planned citation chunk/snippet retrieval |
| GET | `/api/sources/documents/{documentId}` | Planned document source metadata retrieval |

Returned citation payload should include source metadata and excerpt only. Exact field set: TBD.

### Admin Ingestion

| Method | Path | Notes |
|---|---|---|
| POST | `/api/admin/ingestion/jobs` | Planned create ingestion job |
| GET | `/api/admin/ingestion/jobs` | Planned list ingestion jobs |
| GET | `/api/admin/ingestion/jobs/{id}` | Planned job status |
| GET | `/api/admin/ingestion/jobs/{id}/logs` | Planned job logs |

Planned job creation payload from Technical Spec:

```json
{
  "region": "DKI Jakarta",
  "year_start": 2022,
  "year_end": 2026,
  "max_documents": 300,
  "force_reprocess": false
}
```

Validation rules and authorization details: TBD.

### Health Check

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Planned API health check |
| GET | `/api/health/dependencies` | Planned PostgreSQL/Qdrant/provider status check |

Health payload shape: TBD.
