# Backup And Restore

These scripts are intended for a single-VPS deployment. They back up:

- PostgreSQL metadata, Identity, jobs, logs, and chat data;
- Qdrant storage;
- the PDF corpus under `RINGKAS_DATA_ROOT/pdfs`.
- ASP.NET Data Protection keys under `RINGKAS_DATA_ROOT/keys`.

The backup script briefly stops Qdrant so its filesystem copy is consistent.
PostgreSQL remains online while `pg_dump` runs.

## Backup

Run from the repository root on the deployment host:

```bash
export RINGKAS_DATA_ROOT=/data/ringkas
export BACKUP_DIR=/data/ringkas-backups
export ENV_FILE=/path/to/.env
export COMPOSE_OVERRIDE_FILE=/path/to/infra/docker-compose.production.yml
bash scripts/backup/backup.sh
```

Copy the timestamped directory to separate storage and retain at least one
known-good backup outside the VPS. Never commit backup artifacts.

## Restore

Restore is destructive and should be tested on a disposable host first:

```bash
export RINGKAS_DATA_ROOT=/data/ringkas
export BACKUP_DIR=/data/ringkas-backups/20260101T000000Z
export ENV_FILE=/path/to/.env
export COMPOSE_OVERRIDE_FILE=/path/to/infra/docker-compose.production.yml
export CONFIRM_RESTORE=YES
bash scripts/backup/restore.sh
```

After restore, run EF migration status, service health checks, Qdrant collection
verification, citation smoke tests, and an application login/chat smoke test.
