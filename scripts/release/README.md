# Release Preflight

Run this on the deployment host after applying migrations, starting the core
services, and completing the intended ingestion run:

```bash
export ENV_FILE=/path/to/.env
export COMPOSE_FILE=/path/to/infra/docker-compose.yml
export COMPOSE_OVERRIDE_FILE=/path/to/infra/docker-compose.production.yml
bash scripts/release/preflight.sh
```

The check validates the production Compose configuration, required core
containers, PostgreSQL readiness, Qdrant health, and that no ingestion job is
still queued or running. It does not replace the supported-chat citation smoke
test, Google OAuth callback test, restore test, RAGAS evaluation, or manual
20-question audit.
