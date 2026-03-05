# ChatVote

AI-powered political information chatbot for French elections. Citizens ask questions to multiple political parties simultaneously and receive source-backed answers via RAG.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker & Docker Compose | latest | [docker.com](https://docs.docker.com/get-docker/) |
| Python | 3.11+ | [python.org](https://www.python.org/) |
| Poetry | latest | `pip install poetry` |
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| pnpm | latest | `npm install -g pnpm` |
| Java | 11+ | Required for Firebase emulators |
| Ollama | latest | `brew install ollama` (recommended on macOS) |

## Quick Start

```bash
git clone --recurse-submodules git@github.com:TANDEM-Association/ChatVote.git
cd ChatVote
make setup    # One-time: install deps, create .env files
make dev      # Start everything (Docker, Firebase, backend, frontend)
```

Open http://localhost:3000. That's it.

Use `make logs` to tail all service logs, `make check` to health-check, `make stop` to shut down.

## Architecture

```
Browser ◄──► Next.js (:3000) ◄──Socket.IO──► Backend (:8080)
                                                  │
                                    ┌─────────────┼─────────────┐
                                    ▼             ▼             ▼
                              Qdrant (:6333)  Ollama (:11434)  Firebase
                              Vector search   Local LLM       Emulators
                                                              (:8081 Firestore)
                                                              (:9099 Auth)
```

## Local Services

| Service | Port | URL |
|---------|------|-----|
| Frontend (Next.js) | 3000 | http://localhost:3000 |
| Backend (aiohttp) | 8080 | http://localhost:8080 |
| Qdrant dashboard | 6333 | http://localhost:6333/dashboard |
| Ollama | 11434 | http://localhost:11434 |
| Firestore emulator | 8081 | http://localhost:8081 |
| Auth emulator | 9099 | http://localhost:9099 |

## Make Targets

### Development

| Target | Description |
|--------|-------------|
| `make setup` | One-time setup: create `.env` files, install deps, pull Ollama models |
| `make dev` | Start **everything**: Docker infra, seed data, backend, frontend |
| `make dev-infra` | Start only Docker containers (Qdrant, and Ollama/Firebase if not native) |
| `make dev-backend` | Start backend in foreground (for debugging) |
| `make dev-frontend` | Start frontend in foreground (for debugging) |
| `make seed` | Seed Firestore emulator + create Qdrant collections |
| `make seed-vectors` | Same as seed + generate sample embeddings via Ollama |
| `make check` | Health-check all services |
| `make logs` | Tail all service logs |
| `make stop` | Stop Docker containers + background processes |
| `make clean` | Stop everything + remove Docker volumes |

### Testing

| Target | Description |
|--------|-------------|
| `make test-e2e` | Run full E2E suite (starts infra, seeds, runs Playwright, stops) |

**Frontend E2E tests** (`CHATVOTE-FrontEnd/`):

```bash
npx playwright test                    # Run all E2E tests
npx playwright test --project=mock     # Run mock tests only (no real backend)
npx playwright test --ui               # Interactive UI mode
```

Tests use a **mock Socket.IO server** on a dynamic port — no real backend needed. The test framework auto-detects browser console errors (hydration mismatches, uncaught exceptions) and fails tests when unexpected errors appear.

### RAG Evaluation

| Target | Description |
|--------|-------------|
| `make eval` | Run all RAG evaluations (DeepEval) |
| `make eval-static` | Static evaluations only (no live services needed) |
| `make eval-e2e` | End-to-end RAG evaluations (needs Qdrant + Ollama) |
| `make red-team` | Red-team adversarial tests |
| `make generate-goldens` | Generate golden QA pairs for evaluation |
| `make eval-report` | Generate HTML evaluation dashboard |

### Embedding Providers

The backend supports multiple embedding providers, configured via `EMBEDDING_PROVIDER` in `.env`:

| Provider | Model | Dimensions | Config |
|----------|-------|-----------|--------|
| `ollama` (default) | nomic-embed-text | 768 | Local, no API key |
| `scaleway` | qwen3-embedding-8b | 4096 | `SCALEWAY_EMBED_API_KEY` |
| `google` | gemini-embedding-001 | 3072 | `GOOGLE_API_KEY` |
| `openai` | text-embedding-3-large | 3072 | `OPENAI_API_KEY` |

Auto-detection picks the first available provider if `EMBEDDING_PROVIDER` is unset. Ollama model names are configurable via `OLLAMA_MODEL` and `OLLAMA_EMBED_MODEL` in `.env`.

## Project Structure

```
ChatVote/
├── CHATVOTE-BackEnd/          # Python async API (submodule)
│   ├── src/                   #   Application source
│   │   ├── aiohttp_app.py     #   HTTP server + REST routes
│   │   ├── websocket_app.py   #   Socket.IO event handlers
│   │   ├── chatbot_async.py   #   RAG pipeline + LLM generation
│   │   ├── llms.py            #   LLM provider failover chain
│   │   ├── models/            #   Pydantic data models
│   │   └── services/          #   Background services
│   ├── scripts/               #   Seed & utility scripts
│   ├── firebase/              #   Firebase emulator config
│   └── pyproject.toml
├── CHATVOTE-FrontEnd/         # Next.js React app (submodule)
│   ├── src/
│   │   ├── app/               #   App Router pages
│   │   ├── components/        #   React components (shadcn/ui)
│   │   ├── lib/               #   Stores, socket client, utils
│   │   └── i18n/              #   FR/EN translations
│   ├── e2e/                   #   Playwright E2E tests
│   │   ├── mock/              #   Test specs (mock Socket.IO)
│   │   └── support/           #   Fixtures, helpers, base-test
│   └── package.json
├── docker-compose.dev.yml     # Qdrant + Ollama for local dev
├── Makefile                   # Developer workflow commands
└── CLAUDE.md                  # AI assistant context
```

## Troubleshooting

**Ollama is very slow (macOS)**
The Docker Ollama container runs on CPU only (no Apple Silicon GPU access). Install Ollama natively for GPU acceleration: `brew install ollama && ollama serve`. The Makefile auto-detects a native Ollama and skips the Docker container.

**Ollama model pull is slow**
First run triggers model downloads (~2 GB for llama3.2 + nomic-embed-text). This only happens once — subsequent starts are fast.

**Port already in use**
Check what's using the port: `lsof -i :<port>`. Kill the process or change the port in the relevant `.env` file.

**Java not found (Firebase emulators)**
Firebase emulators require Java 11+. Install via your package manager (`brew install openjdk@11` on macOS).

**"No parties loaded" in the UI**
Run `make seed` to populate Firestore with sample party data.

**Firebase emulator won't start**
Check logs: `cat .logs/firebase-emulators.log`. Common fix: kill stale processes on ports 8081/9099.

## License

See [CHATVOTE-BackEnd/LICENSE](CHATVOTE-BackEnd/LICENSE).
