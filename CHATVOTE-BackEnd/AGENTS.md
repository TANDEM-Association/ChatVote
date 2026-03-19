<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# CHATVOTE-BackEnd

## Purpose
Python async backend for ChatVote, an AI-powered political information chatbot for French elections. Exposes an HTTP REST API and a real-time Socket.IO WebSocket API on top of aiohttp. Implements a RAG pipeline backed by Qdrant vector search, with multi-provider LLM failover (Gemini → OpenAI → Azure → Anthropic → Ollama). Firestore is the primary application database; Firebase Storage holds party manifesto PDFs ingested by Firebase Cloud Functions.

## Key Files
| File | Description |
|------|-------------|
| `pyproject.toml` | Poetry dependency manifest; Python ≥3.11,<3.13 |
| `Dockerfile` / `Dockerfile.dev` | Production and development container images |
| `docker-compose.yml` / `docker-compose.dev.yml` | Local service orchestration (Qdrant, Firebase emulator) |
| `.env.example` | Reference for all required environment variables |
| `.env.local.template` | Template for local development env file |
| `.pre-commit-config.yaml` | Ruff lint/format + mypy hooks |
| `README.md` | Project overview and quickstart |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/` | All application source code (see `src/AGENTS.md`) |
| `tests/` | pytest end-to-end Socket.IO tests (see `tests/AGENTS.md`) |
| `firebase/` | Firebase config, rules, seed data, Cloud Functions (see `firebase/AGENTS.md`) |
| `scripts/` | Developer utility scripts — seed, Firestore import, TS type generation (see `scripts/AGENTS.md`) |
| `data/` | Jupyter notebooks and scripts for offline data pipeline work (see `data/AGENTS.md`) |
| `docs/` | Technical stack documentation (see `docs/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Entry point: `python -m src.aiohttp_app --debug` (port 8080)
- All source code lives under `src/`; do not place application logic at the repo root
- Environment is controlled by `ENV` (`local` | `dev` | `prod`); `local` activates Firebase/Qdrant emulators
- `API_NAME=chatvote-api` must be set; `utils.load_env()` enforces this at import time and will raise if mismatched
- Firebase credentials: service account JSON at repo root for dev/prod; ADC or emulator for local

### Testing Requirements
```bash
# Install deps
poetry install --with dev

# Run tests (requires a running local server on :8080)
poetry run pytest tests/test_websocket_app.py -s

# Lint
poetry run ruff check .

# Format
poetry run ruff format .

# Type check
poetry run mypy src/
```

### Common Patterns
- All async functions use `asyncio` and aiohttp's event loop; avoid blocking calls in async paths
- Pydantic v2 models used throughout; use `model_dump()` not `.dict()`
- Qdrant collections are environment-suffixed: `all_parties_dev`, `all_parties_prod`, etc.
- LLM calls go through `src/llms.py` helpers (`get_answer_from_llms`, `stream_answer_from_llms`) — never call provider SDKs directly
- CORS: open (`*`) in `dev`/`local`, restricted to explicit origins in `prod`

## Dependencies

### Internal
- `src/` — all application logic
- `firebase/firestore_data/dev/` — seed data for local development

### External
| Package | Purpose |
|---------|---------|
| `aiohttp` ~3.9 | Async HTTP server |
| `python-socketio` ~5.12 | Socket.IO WebSocket server |
| `aiohttp-pydantic` | Pydantic-validated route handlers |
| `langchain` ~0.3 + providers | LLM orchestration and RAG chains |
| `qdrant-client` + `langchain-qdrant` | Vector similarity search |
| `firebase-admin` ~6.6 | Firestore and Firebase Storage access |
| `pypdf` | PDF text extraction |
| `playwright` | Headless browser for candidate website scraping |
| `apscheduler` | Cron job scheduling |
| `xxhash` | Fast hashing for cache keys |
| `pydantic` ~2.10 | Data validation and serialisation |

<!-- MANUAL: -->
