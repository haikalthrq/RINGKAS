#!/usr/bin/env bash
set -euo pipefail
# Cloudflare-only wrapper for the resumable RAGAS live baseline.
# Usage: bash evaluations/scripts/run_ragas.sh
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATASET="$ROOT/evaluations/evaluation_dataset.json"
RESPONSES="$ROOT/evaluations/responses.json"
REPORT="$ROOT/evaluations/ragas_report.json"

set -a
. "$ROOT/.env"
set +a

echo "Dataset: $DATASET"
echo "Responses: $RESPONSES"
echo "Report: $REPORT"

sudo docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.production.yml run --rm --no-deps \
  --volume "$DATASET:/app/evaluation_dataset.json:ro" \
  --volume "$RESPONSES:/app/responses.json:ro" \
  --volume "$ROOT/evaluations:/evaluation:rw" \
  -e CLOUDFLARE_ACCOUNT_ID -e CLOUDFLARE_API_TOKEN \
  -e CLOUDFLARE_SECONDARY_ACCOUNT_ID -e CLOUDFLARE_SECONDARY_API_TOKEN \
  -e CLOUDFLARE_TERTIARY_ACCOUNT_ID -e CLOUDFLARE_TERTIARY_API_TOKEN \
  -e RAGAS_LLM_MODEL -e RAGAS_LLM_TIMEOUT_SECONDS -e RAGAS_LLM_MAX_RETRIES \
  -e RAGAS_LLM_MAX_WORKERS -e RAGAS_LLM_PREFLIGHT_SAMPLES \
  -e RAGAS_LLM_MAX_TOKENS -e RAGAS_LLM_TEMPERATURE \
  --entrypoint bash rag-query -c "
pip install --no-cache-dir langchain-community==0.3.31 langchain-openai==0.3.35 ragas==0.4.3 --quiet
python -m ringkas_worker.ragas_harness --mode live --dataset /app/evaluation_dataset.json --responses /app/responses.json > /evaluation/ragas_report.json || cat /evaluation/ragas_report.json
cat /evaluation/ragas_report.json
"
