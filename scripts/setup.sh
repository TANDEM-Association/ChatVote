#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Interactive setup for ChatVote local development
# Asks the user to choose between Local (Ollama) and Cloud (Gemini) mode,
# then generates the appropriate .env files.
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$ROOT_DIR/CHATVOTE-BackEnd"
FRONTEND_DIR="$ROOT_DIR/CHATVOTE-FrontEnd"

BACKEND_ENV="$BACKEND_DIR/.env"
FRONTEND_ENV="$FRONTEND_DIR/.env.local"

# Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo -e "${BOLD}=== ChatVote Setup ===${NC}"
echo ""

# ---- Frontend .env.local (always the same) ----
if [ -f "$FRONTEND_ENV" ]; then
    echo -e "  ${GREEN}✓${NC} CHATVOTE-FrontEnd/.env.local already exists — skipped"
else
    cp "$FRONTEND_DIR/.env.local.template" "$FRONTEND_ENV"
    echo -e "  ${GREEN}✓${NC} Created CHATVOTE-FrontEnd/.env.local"
fi

# ---- Frontend port selection (first free port between 3000 and 3333) ----
FRONTEND_PORT_FILE="$FRONTEND_DIR/.frontend-port"
if [ ! -f "$FRONTEND_PORT_FILE" ]; then
    FRONTEND_PORT=3000
    for port in $(seq 3000 3333); do
        if ! lsof -ti :"$port" > /dev/null 2>&1; then
            FRONTEND_PORT=$port
            break
        fi
    done
    echo "$FRONTEND_PORT" > "$FRONTEND_PORT_FILE"
    sed -i '' "s|NEXT_PUBLIC_APP_URL=http://localhost:[0-9]*|NEXT_PUBLIC_APP_URL=http://localhost:$FRONTEND_PORT|" "$FRONTEND_ENV"
    echo -e "  ${GREEN}✓${NC} Frontend port: ${CYAN}$FRONTEND_PORT${NC} (saved to .frontend-port)"
else
    FRONTEND_PORT=$(cat "$FRONTEND_PORT_FILE")
    echo -e "  ${GREEN}✓${NC} Frontend port: ${CYAN}$FRONTEND_PORT${NC} (from .frontend-port)"
fi

# ---- Backend .env (interactive) ----
if [ -f "$BACKEND_ENV" ]; then
    echo -e "  ${GREEN}✓${NC} CHATVOTE-BackEnd/.env already exists — skipped"
    echo ""
    echo -e "  ${YELLOW}Tip:${NC} Delete CHATVOTE-BackEnd/.env and re-run to reconfigure."
    SKIP_ENV=true
else
    SKIP_ENV=false
fi

# ---- Firebase service account (always ensure it exists) ----
FIREBASE_KEY="$BACKEND_DIR/chat-vote-dev-firebase-adminsdk.json"
if [ ! -f "$FIREBASE_KEY" ]; then
    echo -e "  ${CYAN}→${NC} Generating dummy Firebase service account for local emulator..."
    PRIVATE_KEY=$(openssl genrsa 2048 2>/dev/null | awk '{printf "%s\\n", $0}' | sed 's/\\n$//')
    cat > "$FIREBASE_KEY" << KEYEOF
{
  "type": "service_account",
  "project_id": "chat-vote-dev",
  "private_key_id": "local-dev-dummy-key",
  "private_key": "$PRIVATE_KEY",
  "client_email": "firebase-adminsdk@chat-vote-dev.iam.gserviceaccount.com",
  "client_id": "000000000000000000000",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk%40chat-vote-dev.iam.gserviceaccount.com"
}
KEYEOF
    echo -e "  ${GREEN}✓${NC} Created dummy Firebase service account (local emulator only)"
fi

if [ "$SKIP_ENV" = true ]; then
    if ! grep -q "^GOOGLE_APPLICATION_CREDENTIALS=" "$BACKEND_ENV" 2>/dev/null; then
        echo "GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_KEY" >> "$BACKEND_ENV"
        echo -e "  ${GREEN}✓${NC} Added GOOGLE_APPLICATION_CREDENTIALS to CHATVOTE-BackEnd/.env"
    fi
    echo ""
    exit 0
fi

echo ""
echo -e "${BOLD}Choose your LLM & embedding provider:${NC}"
echo ""
echo -e "  ${CYAN}1)${NC} Local (Ollama)  — Free, runs on your machine, no API key needed"
echo -e "                       Chat: llama3.2 | Embeddings: nomic-embed-text (768d)"
echo ""
echo -e "  ${CYAN}2)${NC} Cloud (Gemini)  — Better quality, requires a Google API key"
echo -e "                       Chat: gemini-2.0-flash | Embeddings: gemini-embedding-001 (3072d)"
echo ""

while true; do
    printf "  Enter choice [1/2]: "
    read -r choice
    case "$choice" in
        1) MODE="local"; break ;;
        2) MODE="gemini"; break ;;
        *) echo -e "  ${RED}Invalid choice.${NC} Please enter 1 or 2." ;;
    esac
done

echo ""

if [ "$MODE" = "gemini" ]; then
    echo -e "  ${BOLD}Google API Key${NC}"
    echo -e "  Get one at: ${CYAN}https://aistudio.google.com/apikey${NC}"
    echo ""
    printf "  Enter your GOOGLE_API_KEY: "
    read -r google_key

    if [ -z "$google_key" ]; then
        echo -e "  ${RED}No key provided.${NC} Falling back to Local (Ollama) mode."
        MODE="local"
    fi
fi

echo ""

# ---- Write backend .env ----
if [ "$MODE" = "local" ]; then
    cat > "$BACKEND_ENV" << 'ENVEOF'
API_NAME=chatvote-api
ENV=local
LANGCHAIN_TRACING_V2=false

# === LOCAL DEVELOPMENT (Ollama — no API keys needed) ===
QDRANT_URL=http://localhost:6333
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_DIM=768
EMBEDDING_PROVIDER=ollama

# === Cloud API keys (optional — uncomment to use cloud LLMs) ===
# GOOGLE_API_KEY=
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
ENVEOF

    echo "GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_KEY" >> "$BACKEND_ENV"
    echo -e "  ${GREEN}✓${NC} Created CHATVOTE-BackEnd/.env (Local / Ollama)"
    echo ""
    echo -e "  Embeddings: ${CYAN}nomic-embed-text (768d)${NC} via Ollama"
    echo -e "  Chat model: ${CYAN}llama3.2${NC} via Ollama"

else
    cat > "$BACKEND_ENV" << ENVEOF
API_NAME=chatvote-api
ENV=local
LANGCHAIN_TRACING_V2=false

# === CLOUD DEVELOPMENT (Gemini) ===
QDRANT_URL=http://localhost:6333
GOOGLE_API_KEY=${google_key}
EMBEDDING_PROVIDER=google

# === Ollama fallback (kept for optional local use) ===
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_DIM=768
ENVEOF

    echo "GOOGLE_APPLICATION_CREDENTIALS=$FIREBASE_KEY" >> "$BACKEND_ENV"
    echo -e "  ${GREEN}✓${NC} Created CHATVOTE-BackEnd/.env (Cloud / Gemini)"
    echo ""
    echo -e "  Embeddings: ${CYAN}gemini-embedding-001 (3072d)${NC} via Google AI"
    echo -e "  Chat model: ${CYAN}gemini-2.0-flash${NC} via Google AI"
fi

echo ""
echo -e "  ${BOLD}Mode: $MODE${NC}"
echo -e "  Run ${CYAN}make dev${NC} to start all services."
echo ""
