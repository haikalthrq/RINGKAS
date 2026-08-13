#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/infra/docker-compose.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-}"
BACKUP_DIR="${BACKUP_DIR:?Set BACKUP_DIR to one backup timestamp directory}"
RINGKAS_DATA_ROOT="${RINGKAS_DATA_ROOT:?Set RINGKAS_DATA_ROOT to the runtime data directory}"

if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "Set CONFIRM_RESTORE=YES to replace the current database and Qdrant data" >&2
  exit 1
fi
if [[ "$RINGKAS_DATA_ROOT" == "/" || ! -d "$RINGKAS_DATA_ROOT" ]]; then
  echo "RINGKAS_DATA_ROOT must be an existing non-root directory" >&2
  exit 1
fi
for artifact in postgres.dump pdfs.tar.gz keys.tar.gz qdrant.tar.gz SHA256SUMS; do
  test -f "$BACKUP_DIR/$artifact" || { echo "Missing backup artifact: $artifact" >&2; exit 1; }
done

(cd "$BACKUP_DIR" && sha256sum --check SHA256SUMS)
compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
  compose+=(-f "$COMPOSE_OVERRIDE_FILE")
fi

"${compose[@]}" down
rm -rf "$RINGKAS_DATA_ROOT/qdrant"
rm -rf "$RINGKAS_DATA_ROOT/pdfs"
rm -rf "$RINGKAS_DATA_ROOT/keys"
tar -C "$RINGKAS_DATA_ROOT" -xzf "$BACKUP_DIR/qdrant.tar.gz"
tar -C "$RINGKAS_DATA_ROOT" -xzf "$BACKUP_DIR/pdfs.tar.gz"
tar -C "$RINGKAS_DATA_ROOT" -xzf "$BACKUP_DIR/keys.tar.gz"
"${compose[@]}" up -d postgres qdrant

for _ in {1..30}; do
  if "${compose[@]}" exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
    break
  fi
  sleep 2

cat "$BACKUP_DIR/postgres.dump" | "${compose[@]}" exec -T postgres sh -c 'pg_restore --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
echo "Restore completed. Start the remaining services and verify health before accepting traffic."
