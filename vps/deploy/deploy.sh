#!/usr/bin/env bash
# Lumencore VPS deploy script
# Run on VPS from /opt/lumencore after git pull
set -euo pipefail

REPO_ROOT="/opt/lumencore"
COMPOSE_FILE="$REPO_ROOT/lumencore/docker-compose.phase2.yml"
ENV_FILE="$REPO_ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.example and fill in secrets first."
  exit 1
fi

echo "==> Pulling latest images / rebuilding..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build --pull

echo "==> Stopping old containers..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down --remove-orphans

echo "==> Starting stack..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

echo "==> Waiting for health checks..."
sleep 10
docker compose -f "$COMPOSE_FILE" ps

echo "==> Deploy complete."
