<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# ChatVote

## Purpose
AI-powered political information chatbot for French elections. Citizens ask questions to multiple political parties simultaneously and receive source-backed answers via RAG (Retrieval-Augmented Generation). Monorepo with two independent git submodules: a Python async backend and a Next.js frontend.

## Key Files

| File | Description |
|------|-------------|
| `Makefile` | One-command local dev orchestration (`make dev`, `make seed`, `make check`, `make stop`) |
| `docker-compose.dev.yml` | Docker services: Qdrant vector DB + optional Ollama LLM (CPU fallback) |
| `CLAUDE.md` | AI agent instructions, architecture docs, and command reference |
| `.gitmodules` | Submodule definitions for BackEnd and FrontEnd repos |
| `playwright.config.ts` | Playwright E2E test config (root-level integration tests) |
| `seed.spec.ts` | Seeding test specification |
| `.gitignore` | Excludes tooling state (`.osgrep`, `.omc`, `.quint`, `.playwright-mcp`, `.logs`) |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `CHATVOTE-BackEnd/` | Python async API — aiohttp + Socket.IO + LangChain + Qdrant RAG (see `CHATVOTE-BackEnd/AGENTS.md`) |
| `CHATVOTE-FrontEnd/` | Next.js 16 React app — TypeScript, Zustand, Tailwind, Socket.IO client (see `CHATVOTE-FrontEnd/AGENTS.md`) |
| `specs/` | Project specifications and requirements (see `specs/AGENTS.md`) |
| `.logs/` | Runtime logs for backend, frontend, and Firebase emulators (gitignored) |

## For AI Agents

### Working In This Directory
- Run `make setup` after cloning to init submodules, create `.env` files, and install all deps
- Run `make dev` to start everything (Docker, Firebase emulators, backend, frontend)
- Run `make check` to health-check all 5 services (Qdrant, Ollama, Firestore, Backend, Frontend)
- Run `make stop` to tear down all services; `make clean` to also remove Docker volumes
- Backend and frontend are independent codebases — changes to one don't require rebuilding the other

### Architecture Overview
```
Browser (Next.js :3000) ── Socket.IO ──→ Backend (:8080) ──→ Qdrant (RAG) + LLM providers
                                                                    │
                                              Gemini (primary) → OpenAI → Azure → Claude (failover)
```

### Local Services
| Service | Port | Purpose |
|---------|------|---------|
| Frontend | 3000 | Next.js dev server (Turbopack) |
| Backend | 8080 | aiohttp + Socket.IO API |
| Qdrant | 6333 | Vector database for RAG |
| Ollama | 11434 | Local LLM engine (optional, GPU-accelerated if native) |
| Firestore emulator | 8081 | Local Firestore for dev |

### Testing Requirements
- Root-level `playwright.config.ts` for integration tests spanning both frontend and backend
- Backend tests: `cd CHATVOTE-BackEnd && poetry run pytest`
- Frontend tests: `cd CHATVOTE-FrontEnd && npm run lint && npm run type:check`
- E2E tests: `cd CHATVOTE-FrontEnd && npx playwright test`

### Common Patterns
- Zero cloud keys needed for local dev (Ollama + Firebase emulators + Qdrant in Docker)
- Submodules track `main` branch on TANDEM origin
- Data seeding: `make seed` (Firestore only) or `make seed-vectors` (+ Qdrant embeddings via Ollama)

## Dependencies

### External
- Docker & Docker Compose — container orchestration for Qdrant + Ollama
- Poetry — Python dependency management (backend)
- pnpm — Node.js package manager (frontend)
- Firebase CLI — emulator tooling
- Ollama — local LLM inference (optional, recommended for Apple Silicon)

<!-- MANUAL: -->
