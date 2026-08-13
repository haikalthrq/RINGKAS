#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/infra/docker-compose.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
RINGKAS_DATA_ROOT="${RINGKAS_DATA_ROOT:?Set RINGKAS_DATA_ROOT to the runtime data directory}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"

if [[ "$RINGKAS_DATA_ROOT" == "/" || ! -d "$RINGKAS_DATA_ROOT" ]]; then
  echo "RINGKAS_DATA_ROOT must be an existing non-root directory" >&2
  exit 1
fi

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
  compose+=(-f "$COMPOSE_OVERRIDE_FILE")
fi

mkdir -p "$DEST"
"${compose[@]}" exec -T postgres sh -c 'pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$DEST/postgres.dump"
tar -C "$RINGKAS_DATA_ROOT" -czf "$DEST/pdfs.tar.gz" pdfs
test -d "$RINGKAS_DATA_ROOT/keys" || mkdir -p "$RINGKAS_DATA_ROOT/keys"
tar -C "$RINGKAS_DATA_ROOT" -czf "$DEST/keys.tar.gz" keys

"${compose[@]}" stop qdrant
restart_qdrant() {
  "${compose[@]}" start qdrant >/dev/null
}
trap restart_qdrant EXIT
tar -C "$RINGKAS_DATA_ROOT" -czf "$DEST/qdrant.tar.gz" qdrant

(cd "$DEST" && sha256sum postgres.dump pdfs.tar.gz keys.tar.gz qdrant.tar.gz > SHA256SUMS)
echo "Backup created: $DEST"
