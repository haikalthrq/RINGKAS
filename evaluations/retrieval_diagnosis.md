# Retrieval Diagnosis

## Scope

The staging diagnostic measured the first 100 records from
`evaluations/evaluation_dataset.json` against their authoritative
`expected_chunk_id` values. It queried each retrieval channel independently.

## Result

| Channel | Candidate limit | Ground-truth hits | Recall |
|---|---:|---:|---:|
| Dense Qwen3 | 20 | 0/100 | 0.0% |
| Sparse BM25 | 20 | 7/100 | 7.0% |
| RRF | 30 | 7/100 | 7.0% |

The seven RRF hits all originated from the sparse channel. Dense retrieval
contributed no ground-truth result.

## Dense Vector Probe

The dense self-retrieval probe queried each record using its own authoritative
excerpt. None of 20 excerpts returned its source chunk in dense Top-20. The
same unrelated construction document was consistently ranked first.

Retrieving the stored dense vector for all 20 probe points found:

```text
dimension: 1024
norm: 0.0
minimum: 0.0
maximum: 0.0
hash: identical across every sampled vector
```

The restored Qdrant v2 dense vectors are zero vectors. This is an index-data
integrity issue, not a question-template or RRF implementation issue.

## Corrective Action

Run the supported full reindex from PostgreSQL authoritative chunks using the
approved Cloudflare `@cf/qwen/qwen3-embedding-0.6b` model and existing BM25
path. Persist its checkpoint outside the disposable container so interrupted
runs resume safely. Do not use the current evaluation metrics as a release
quality claim. Rerun the retrieval diagnostic and the 1000-Q evaluation only
after dense self-retrieval succeeds.
