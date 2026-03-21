#!/usr/bin/env bash
set -euo pipefail

echo "==> Starting Docker Compose services in background..."
cd /workspace
docker compose -f docker-compose.dev.yml --profile firebase --profile langfuse up -d &

echo "==> Services starting in background. Use 'make check' to verify readiness."
echo "==> Run 'make dev' to start frontend + backend."
