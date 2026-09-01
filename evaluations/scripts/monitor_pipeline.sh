#!/usr/bin/env bash
# Quick monitor for the evaluation pipeline
# Usage: bash evaluations/scripts/monitor_pipeline.sh
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVAL_DIR="$ROOT_DIR/evaluations"

echo "=== RINGKAS Pipeline Monitor ==="
echo ""

# Dataset generation progress
CONTAINER=$(sudo docker ps --format '{{.Names}}' | grep 'rag-query-run-' | head -1)
if [[ -n "$CONTAINER" ]]; then
    LAST=$(sudo docker logs "$CONTAINER" --tail 1 2>&1 | grep -oP '\[\K[0-9]+(?=/1000)\]' || echo "0")
    echo "Dataset generation: ${LAST}/1000 (container: $CONTAINER)"
else
    echo "Dataset generation: container not running"
fi

# Checkpoint
if [[ -f "$EVAL_DIR/dataset_generation_checkpoint.json" ]]; then
    CKPT=$(python3 -c "import json; d=json.load(open('$EVAL_DIR/dataset_generation_checkpoint.json')); print(f'{len(d[\"records\"])}/{d.get(\"next_id\",0)}')" 2>/dev/null)
    echo "Checkpoint: $CKPT records"
fi

# Final dataset
if [[ -f "$EVAL_DIR/evaluation_dataset.json" ]]; then
    CAP=$(python3 -c "import json; print(json.load(open('$EVAL_DIR/evaluation_dataset.json'))['capacity'])" 2>/dev/null)
    echo "Dataset file: $CAP records"
fi

# Diagnostic
if [[ -f "$EVAL_DIR/retrieval_diagnostic_1000.json" ]]; then
    echo "Diagnostic: DONE"
else
    echo "Diagnostic: pending"
fi

# Responses
if [[ -f "$EVAL_DIR/responses.json" ]]; then
    echo "Responses: DONE"
else
    echo "Responses: pending"
fi

# Services
echo ""
echo "Services:"
sudo docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'postgres|qdrant|rag-query|api|web' | head -10

echo ""
echo "Resume pipeline: bash $ROOT_DIR/evaluations/scripts/run_all.sh"
