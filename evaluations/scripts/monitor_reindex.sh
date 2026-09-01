#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHECKPOINT="$ROOT_DIR/evaluations/reindex_v2.json"
LOG="$ROOT_DIR/evaluations/reindex_v2.log"
MONITOR_LOG="$ROOT_DIR/evaluations/reindex_monitor.log"
TARGET=98974

completed_count() {
  python3 -c 'import json, pathlib, sys; path=pathlib.Path(sys.argv[1]); print(len(json.loads(path.read_text())["completed_ids"]) if path.exists() else 0)' "$CHECKPOINT"
}

while true; do
  completed="$(completed_count)"
  if (( completed >= TARGET )); then
    printf '%s completed=%s/%s\n' "$(date -Is)" "$completed" "$TARGET" >> "$MONITOR_LOG"
    exit 0
  fi

  if ! pgrep -f 'python -m ringkas_worker.reindex' >/dev/null; then
    printf '%s restarting completed=%s/%s\n' "$(date -Is)" "$completed" "$TARGET" >> "$MONITOR_LOG"
    sudo docker compose --env-file "$ROOT_DIR/.env" \
      -f "$ROOT_DIR/infra/docker-compose.yml" \
      -f "$ROOT_DIR/infra/docker-compose.production.yml" \
      run --rm --no-deps \
      --volume "$ROOT_DIR/evaluations:/evaluation:rw" \
      -e QDRANT_DENSE_DISTANCE=cosine \
      -e QDRANT_REINDEX_CHECKPOINT_PATH=/evaluation/reindex_v2.json \
      --entrypoint python rag-query -m ringkas_worker.reindex >> "$LOG" 2>&1 &
  else
    printf '%s running completed=%s/%s\n' "$(date -Is)" "$completed" "$TARGET" >> "$MONITOR_LOG"
  fi
  sleep 60
done
