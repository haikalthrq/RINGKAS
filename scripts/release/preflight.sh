#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/infra/docker-compose.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-$ROOT_DIR/infra/docker-compose.production.yml}"

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
  compose+=(-f "$COMPOSE_OVERRIDE_FILE")
fi

"${compose[@]}" config --quiet

for service in postgres qdrant rag-query api web; do
  if ! "${compose[@]}" ps --status running --services | grep -Fxq "$service"; then
    echo "Required service is not running: $service" >&2
    exit 1
  fi
done

"${compose[@]}" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null
"${compose[@]}" exec -T rag-query python -c 'import urllib.request; urllib.request.urlopen("http://qdrant:6333/healthz", timeout=5)' >/dev/null

query='psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM ingestion_jobs WHERE status IN ('\''queued'\'','\''running'\'');"'
active_jobs=$("${compose[@]}" exec -T postgres sh -c "$query")
if [[ "$active_jobs" != "0" ]]; then
  echo "Ingestion jobs are still active: $active_jobs" >&2
  exit 1
fi

echo "Release preflight passed for the configured Compose topology."
