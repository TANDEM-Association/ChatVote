#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Interactive setup for ChatVote local development
# Asks the user to choose between Local (Ollama), Cloud (Gemini), or
# Scaleway mode, then generates the appropriate .env files.
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

# ---- Backend .env (interactive) ----
if [ -f "$BACKEND_ENV" ]; then
    echo -e "  ${GREEN}✓${NC} CHATVOTE-BackEnd/.env already exists — skipped"
    echo ""
    echo -e "  ${YELLOW}Tip:${NC} Delete CHATVOTE-BackEnd/.env and re-run to reconfigure."
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
echo -e "  ${CYAN}3)${NC} Scaleway        — Scaleway AI APIs, requires a Scaleway API key"
echo -e "                       Chat: llama-3.3-70b-instruct | Embeddings: qwen3-embedding-8b (4096d)"
echo ""

while true; do
    printf "  Enter choice [1/2/3]: "
    read -r choice
    case "$choice" in
        1) MODE="local"; break ;;
        2) MODE="gemini"; break ;;
        3) MODE="scaleway"; break ;;
        *) echo -e "  ${RED}Invalid choice.${NC} Please enter 1, 2, or 3." ;;
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

if [ "$MODE" = "scaleway" ]; then
    echo -e "  ${BOLD}Scaleway API Key${NC}"
    echo -e "  Get one at: ${CYAN}https://console.scaleway.com/iam/api-keys${NC}"
    echo ""
    printf "  Enter your SCALEWAY_EMBED_API_KEY: "
    read -r scaleway_key

    if [ -z "$scaleway_key" ]; then
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

# === Firebase Storage (needed for manifesto PDF indexer) ===
FIREBASE_STORAGE_BUCKET=chat-vote-dev.appspot.com
ENVEOF

    echo -e "  ${GREEN}✓${NC} Created CHATVOTE-BackEnd/.env (Local / Ollama)"
    echo ""
    echo -e "  Embeddings: ${CYAN}nomic-embed-text (768d)${NC} via Ollama"
    echo -e "  Chat model: ${CYAN}llama3.2${NC} via Ollama"

elif [ "$MODE" = "gemini" ]; then
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

# === Firebase Storage (needed for manifesto PDF indexer) ===
FIREBASE_STORAGE_BUCKET=chat-vote-dev.appspot.com
ENVEOF

    echo -e "  ${GREEN}✓${NC} Created CHATVOTE-BackEnd/.env (Cloud / Gemini)"
    echo ""
    echo -e "  Embeddings: ${CYAN}gemini-embedding-001 (3072d)${NC} via Google AI"
    echo -e "  Chat model: ${CYAN}gemini-2.0-flash${NC} via Google AI"

else
    cat > "$BACKEND_ENV" << ENVEOF
API_NAME=chatvote-api
ENV=local
LANGCHAIN_TRACING_V2=false

# === SCALEWAY DEVELOPMENT ===
QDRANT_URL=http://localhost:6333
SCALEWAY_EMBED_API_KEY=${scaleway_key}
EMBEDDING_PROVIDER=scaleway

# === Ollama fallback (kept for optional local use) ===
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_DIM=768

# === Cloud API keys (optional — uncomment for Gemini/OpenAI chat) ===
# GOOGLE_API_KEY=
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=

# === Firebase Storage (needed for manifesto PDF indexer) ===
FIREBASE_STORAGE_BUCKET=chat-vote-dev.appspot.com
ENVEOF

    echo -e "  ${GREEN}✓${NC} Created CHATVOTE-BackEnd/.env (Scaleway)"
    echo ""
    echo -e "  Embeddings: ${CYAN}qwen3-embedding-8b (4096d)${NC} via Scaleway AI"
    echo -e "  Chat model: ${CYAN}llama-3.3-70b-instruct${NC} via Scaleway AI"
fi

echo ""
echo -e "  ${BOLD}Mode: $MODE${NC}"
echo -e "  Run ${CYAN}make dev${NC} to start all services."
echo ""
