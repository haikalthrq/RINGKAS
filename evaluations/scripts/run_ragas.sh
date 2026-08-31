#!/usr/bin/env bash
set -euo pipefail
# Wrapper untuk RAGAS harness live
# Penggunaan: bash evaluations/scripts/run_ragas.sh
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATASET="$ROOT/evaluations/evaluation_dataset.json"
RESPONSES="$ROOT/evaluations/responses.json"
REPORT="$ROOT/evaluations/ragas_report.json"

RAGAS_KEY=$(grep NVIDIA_NIM_API_KEY "$ROOT/.env" | cut -d= -f2)
export RAGAS_LLM_API_KEY="$RAGAS_KEY"
export RAGAS_LLM_MODEL="nvidia/nemotron-3-nano-30b-a3b"
export RAGAS_LLM_BASE_URL="https://integrate.api.nvidia.com/v1"
export RAGAS_LLM_PROVIDER="openai"

echo "Dataset: $DATASET"
echo "Responses: $RESPONSES"
echo "Report: $REPORT"

# Coba dengan langchain-community 0.2.16 (yang terbukti work untuk import)
sudo docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.production.yml run --rm --no-deps \
  --volume "$DATASET:/app/evaluation_dataset.json:ro" \
  --volume "$RESPONSES:/app/responses.json:ro" \
  --volume "$ROOT/evaluations:/evaluation:rw" \
  -e RAGAS_LLM_API_KEY -e RAGAS_LLM_MODEL -e RAGAS_LLM_BASE_URL -e RAGAS_LLM_PROVIDER \
  --entrypoint bash rag-query -c "
pip install --no-cache-dir langchain-community==0.2.16 ragas==0.4.3 --quiet
python -m ringkas_worker.ragas_harness --mode live --dataset /app/evaluation_dataset.json --responses /app/responses.json > /evaluation/ragas_report.json || cat /evaluation/ragas_report.json
cat /evaluation/ragas_report.json
"
