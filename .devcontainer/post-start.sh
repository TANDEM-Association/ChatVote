#!/usr/bin/env bash
set -euo pipefail

echo "==> Starting Docker Compose services in background..."
cd /workspace
docker compose -f docker-compose.dev.yml --profile firebase --profile langfuse --profile ragflow up -d &

echo "==> Services starting in background. Use 'make check' to verify readiness."
echo "==> Run 'make dev' to start frontend + backend."
echo ""
echo "=== Default Dev Credentials ==="
echo ""
echo "  Langfuse (http://localhost:8652)"
echo "    Email:    admin@chatvote.local"
echo "    Password: chatvote123"
echo ""
echo "  RAGFlow (http://localhost:8680)"
echo "    Email:    admin@chatvote.local"
echo "    Password: chatvote123"
echo "    API key:  login → user avatar → API Keys"
echo ""
echo "  Firebase Emulators (http://localhost:4000)"
echo "    No credentials needed (emulator mode)"
echo ""
