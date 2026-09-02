#!/usr/bin/env bash
set -euo pipefail
# Wrapper untuk RAGAS harness live
# Penggunaan: bash evaluations/scripts/run_ragas.sh
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATASET="$ROOT/evaluations/evaluation_dataset.json"
RESPONSES="$ROOT/evaluations/responses.json"
REPORT="$ROOT/evaluations/ragas_report.json"

set -a
. "$ROOT/.env"
set +a
RAGAS_LLM_API_KEY="${RAGAS_LLM_API_KEY:-${NVIDIA_NIM_API_KEY:-}}"
RAGAS_LLM_MODEL="${RAGAS_LLM_MODEL:-openai/gpt-oss-120b}"
RAGAS_LLM_BASE_URL="${RAGAS_LLM_BASE_URL:-https://integrate.api.nvidia.com/v1}"
RAGAS_LLM_PROVIDER="${RAGAS_LLM_PROVIDER:-openai}"
test -n "$RAGAS_LLM_API_KEY"

echo "Dataset: $DATASET"
echo "Responses: $RESPONSES"
echo "Report: $REPORT"

sudo docker run --rm \
  --volume "$ROOT/services/rag-worker:/app" \
  --volume "$ROOT/evaluations:/evaluation:rw" \
  --workdir /app \
  -e RAGAS_LLM_API_KEY="$RAGAS_LLM_API_KEY" \
  -e RAGAS_LLM_MODEL="$RAGAS_LLM_MODEL" \
  -e RAGAS_LLM_BASE_URL="$RAGAS_LLM_BASE_URL" \
  -e RAGAS_LLM_PROVIDER="$RAGAS_LLM_PROVIDER" \
  python:3.12-slim bash -lc '
    pip install --no-cache-dir uv >/dev/null &&
    uv run --extra evaluation --frozen python -m ringkas_worker.ragas_harness \
      --mode live \
      --dataset /evaluation/evaluation_dataset.json \
      --responses /evaluation/responses.json > /evaluation/ragas_report.json &&
    cat /evaluation/ragas_report.json
  '
