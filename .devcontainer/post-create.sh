#!/usr/bin/env bash
set -euo pipefail

# Source NVM (installed by devcontainer node feature)
export NVM_DIR="${NVM_DIR:-/usr/local/share/nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

echo "==> Setting up pnpm..."
mkdir -p "$HOME/.cache/node/corepack"
corepack enable
corepack prepare pnpm@latest --activate

echo "==> Configuring Poetry..."
poetry config virtualenvs.in-project true

echo "==> Installing Firebase CLI..."
npm install -g firebase-tools

# Set dummy Firebase credentials for emulator (avoids DefaultCredentialsError)
echo 'export GOOGLE_APPLICATION_CREDENTIALS="/workspace/.devcontainer/firebase-dummy-credentials.json"' >> "$HOME/.bashrc"
export GOOGLE_APPLICATION_CREDENTIALS="/workspace/.devcontainer/firebase-dummy-credentials.json"

echo "==> Creating .env files if missing..."
cd /workspace
[ ! -f CHATVOTE-BackEnd/.env ] && cp CHATVOTE-BackEnd/.env.example CHATVOTE-BackEnd/.env 2>/dev/null || true
[ ! -f CHATVOTE-FrontEnd/.env.local ] && cp CHATVOTE-FrontEnd/.env.local.example CHATVOTE-FrontEnd/.env.local 2>/dev/null || true

export CI=true
echo "==> Installing dependencies (backend + frontend in parallel)..."
(
  cd /workspace/CHATVOTE-BackEnd
  echo "[backend] poetry install..."
  poetry install --with dev
  echo "[backend] done"
) &
PID_BACKEND=$!

(
  cd /workspace/CHATVOTE-FrontEnd
  echo "[frontend] pnpm install..."
  pnpm install --frozen-lockfile
  echo "[frontend] done"
) &
PID_FRONTEND=$!

wait $PID_BACKEND || { echo "Backend install failed"; exit 1; }
wait $PID_FRONTEND || { echo "Frontend install failed"; exit 1; }

echo "==> post-create complete. Run 'make dev' to start all services."
