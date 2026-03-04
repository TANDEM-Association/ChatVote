#!/bin/bash
set -euo pipefail

# Only run in remote (cloud) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PROJECT_DIR"

LOG_PREFIX="[setup-cloud-session]"
log() { echo "$LOG_PREFIX $*"; }

# ── 1. Create .env files if missing ──────────────────────────────────────────
log "Checking .env files..."
if [ ! -f CHATVOTE-BackEnd/.env ]; then
  cp CHATVOTE-BackEnd/.env.local.template CHATVOTE-BackEnd/.env
  log "Created CHATVOTE-BackEnd/.env"
fi
if [ ! -f CHATVOTE-FrontEnd/.env.local ]; then
  cp CHATVOTE-FrontEnd/.env.local.template CHATVOTE-FrontEnd/.env.local
  log "Created CHATVOTE-FrontEnd/.env.local"
fi

# ── 2. Install backend dependencies (Poetry) ────────────────────────────────
if [ -f CHATVOTE-BackEnd/pyproject.toml ]; then
  if ! cd CHATVOTE-BackEnd && poetry env info -p &>/dev/null; then
    log "Installing backend dependencies..."
    poetry install --with dev 2>&1 | tail -1
  else
    # Check if venv exists and has packages
    VENV=$(poetry env info -p 2>/dev/null || true)
    if [ -z "$VENV" ] || [ ! -d "$VENV/lib" ]; then
      log "Installing backend dependencies..."
      poetry install --with dev 2>&1 | tail -1
    else
      log "Backend dependencies already installed"
    fi
  fi
  cd "$PROJECT_DIR"
fi

# ── 3. Install frontend dependencies (pnpm) ─────────────────────────────────
if [ -f CHATVOTE-FrontEnd/package.json ]; then
  if [ ! -d CHATVOTE-FrontEnd/node_modules ]; then
    log "Installing frontend dependencies..."
    cd CHATVOTE-FrontEnd && pnpm install --frozen-lockfile 2>&1 | tail -3
    cd "$PROJECT_DIR"
  else
    log "Frontend dependencies already installed"
  fi
fi

# ── 4. Install Firebase emulator tooling ─────────────────────────────────────
if [ -f CHATVOTE-BackEnd/firebase/package.json ]; then
  if [ ! -d CHATVOTE-BackEnd/firebase/node_modules ]; then
    log "Installing Firebase emulator tooling..."
    cd CHATVOTE-BackEnd/firebase && npm install 2>&1 | tail -1
    cd "$PROJECT_DIR"
  else
    log "Firebase emulator tooling already installed"
  fi
fi

# ── 5. Download Qdrant binary ────────────────────────────────────────────────
QDRANT_BIN="/tmp/qdrant"
if [ ! -f "$QDRANT_BIN" ]; then
  log "Downloading Qdrant binary..."
  ARCH=$(uname -m)
  if [ "$ARCH" = "x86_64" ]; then
    curl -sL "https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz" \
      -o /tmp/qdrant.tar.gz && tar xzf /tmp/qdrant.tar.gz -C /tmp/ && rm /tmp/qdrant.tar.gz
    log "Qdrant binary downloaded"
  elif [ "$ARCH" = "aarch64" ]; then
    curl -sL "https://github.com/qdrant/qdrant/releases/latest/download/qdrant-aarch64-unknown-linux-musl.tar.gz" \
      -o /tmp/qdrant.tar.gz && tar xzf /tmp/qdrant.tar.gz -C /tmp/ && rm /tmp/qdrant.tar.gz
    log "Qdrant binary downloaded"
  else
    log "WARNING: Unsupported architecture $ARCH for Qdrant binary"
  fi
else
  log "Qdrant binary already present"
fi

# ── 6. Pre-cache Firebase emulator JARs ──────────────────────────────────────
FIREBASE_CACHE="${HOME}/.cache/firebase/emulators"
mkdir -p "$FIREBASE_CACHE"

# Firestore emulator JAR
FIRESTORE_JAR="cloud-firestore-emulator-v1.19.8.jar"
if [ ! -f "$FIREBASE_CACHE/$FIRESTORE_JAR" ]; then
  log "Downloading Firestore emulator JAR..."
  curl -sL "https://storage.googleapis.com/firebase-preview-drop/emulator/$FIRESTORE_JAR" \
    -o "$FIREBASE_CACHE/$FIRESTORE_JAR"
  log "Firestore emulator JAR downloaded"
else
  log "Firestore emulator JAR already cached"
fi

# Emulator UI
UI_ZIP="ui-v1.15.0.zip"
if [ ! -f "$FIREBASE_CACHE/$UI_ZIP" ]; then
  log "Downloading Firebase emulator UI..."
  curl -sL "https://storage.googleapis.com/firebase-preview-drop/emulator/$UI_ZIP" \
    -o "$FIREBASE_CACHE/$UI_ZIP"
  log "Firebase emulator UI downloaded"
else
  log "Firebase emulator UI already cached"
fi

# ── 7. Start infrastructure services ────────────────────────────────────────
mkdir -p "$PROJECT_DIR/.logs"

# Start Qdrant if not already running
if ! python3 -c "import socket; s=socket.create_connection(('localhost', 6333), timeout=1); s.close()" 2>/dev/null; then
  if [ -f "$QDRANT_BIN" ]; then
    log "Starting Qdrant..."
    mkdir -p /tmp/qdrant_data/storage
    cat > /tmp/qdrant_config.yaml << 'QDCONF'
storage:
  storage_path: /tmp/qdrant_data/storage
service:
  host: 0.0.0.0
  http_port: 6333
  grpc_port: 6334
QDCONF
    "$QDRANT_BIN" --config-path /tmp/qdrant_config.yaml > "$PROJECT_DIR/.logs/qdrant.log" 2>&1 &
    echo $! > "$PROJECT_DIR/.logs/qdrant.pid"
    # Wait for Qdrant to be ready
    for i in $(seq 1 10); do
      if python3 -c "import socket; s=socket.create_connection(('localhost', 6333), timeout=1); s.close()" 2>/dev/null; then
        log "Qdrant started on :6333"
        break
      fi
      sleep 1
    done
  fi
else
  log "Qdrant already running on :6333"
fi

# Start Firebase emulators if not already running
if ! python3 -c "import socket; s=socket.create_connection(('localhost', 8081), timeout=1); s.close()" 2>/dev/null; then
  log "Starting Firebase emulators..."
  npx firebase emulators:start --project chat-vote-dev --only firestore,auth \
    > "$PROJECT_DIR/.logs/firebase.log" 2>&1 &
  echo $! > "$PROJECT_DIR/.logs/firebase.pid"
  # Wait for emulators to be ready
  for i in $(seq 1 30); do
    if python3 -c "import socket; s=socket.create_connection(('localhost', 8081), timeout=1); s.close()" 2>/dev/null; then
      log "Firebase emulators started (Firestore :8081, Auth :9099)"
      break
    fi
    sleep 2
  done
else
  log "Firebase emulators already running on :8081"
fi

# ── 8. Seed data ────────────────────────────────────────────────────────────
if python3 -c "import socket; s=socket.create_connection(('localhost', 8081), timeout=1); s.close()" 2>/dev/null && \
   python3 -c "import socket; s=socket.create_connection(('localhost', 6333), timeout=1); s.close()" 2>/dev/null; then
  log "Seeding Firestore and Qdrant..."
  cd CHATVOTE-BackEnd && poetry run python scripts/seed_local.py 2>&1 | tail -5
  cd "$PROJECT_DIR"
fi

# ── 9. Persist environment variables for subsequent Bash commands ────────────
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "FIRESTORE_EMULATOR_HOST=localhost:8081"
    echo "QDRANT_URL=http://localhost:6333"
    echo "ENV=local"
  } >> "$CLAUDE_ENV_FILE"
  log "Persisted environment variables to CLAUDE_ENV_FILE"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
log "Cloud session setup complete!"
log "  Qdrant:    http://localhost:6333"
log "  Firestore: http://localhost:8081"
log "  Auth:      http://localhost:9099"
log ""
log "Run 'make dev-backend' and 'make dev-frontend' to start app services."

exit 0
