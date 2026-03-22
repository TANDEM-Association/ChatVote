<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# ChatVote

## Purpose

AI-powered political information chatbot for French elections. Citizens ask questions to multiple political parties simultaneously and receive source-backed answers via RAG (Retrieval-Augmented Generation). Monorepo with two independent codebases: a Python async backend and a Next.js frontend.

## Key Files

| File | Description |
|------|-------------|
| `Makefile` | One-command local dev orchestration (`make setup`, `make dev`, `make check`, `make seed`, `make stop`, `make clean`); 35+ targets for dev, build, test, deploy, observability |
| `docker-compose.dev.yml` | Docker services: Qdrant vector DB, optional Ollama LLM (CPU fallback), Firebase emulators, Langfuse (self-hosted v3 with Postgres/ClickHouse/MinIO) |
| `CLAUDE.md` | AI agent instructions, architecture docs, command reference, environment setup |
| `ARCHITECTURE.md` | Detailed architecture documentation — RAG pipeline, LLM failover chain, Socket.IO real-time flow |
| `.gitmodules` | Git submodule definitions (if using submodules; current: single monorepo) |
| `playwright.config.ts` | Playwright E2E test config (root-level integration tests) |
| `seed.spec.ts` | Seeding test specification |
| `.gitignore` | Excludes tooling state (`.osgrep`, `.omc`, `.quint`, `.playwright-mcp`, `.logs`) |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `CHATVOTE-BackEnd/` | Python async API — aiohttp + Socket.IO + LangChain + Qdrant RAG. See `CHATVOTE-BackEnd/AGENTS.md` |
| `CHATVOTE-FrontEnd/` | Next.js 16 React app — TypeScript, Zustand, Tailwind CSS, Socket.IO client. See `CHATVOTE-FrontEnd/AGENTS.md` |
| `specs/` | Project specifications and requirements. See `specs/AGENTS.md` |
| `.github/` | GitHub Actions CI/CD — linting, testing, Docker image builds, production deploy to Scaleway (backend) + Vercel (frontend) |
| `k8s/` | Kubernetes manifests — Qdrant StatefulSet, Langfuse Deployment (v2 Postgres-only for prod), Redis, service definitions |
| `terraform/` | OpenTofu infrastructure-as-code — Scaleway networking, Serverless Containers, Cockpit, S3 buckets |
| `chatvote-rescue/` | Data pipeline utilities — chunk management, Qdrant indexing, theme classification, backfill operations. See `chatvote-rescue/AGENTS.md` |
| `.logs/` | Runtime logs for backend, frontend, Firebase emulators, Langfuse (gitignored) |

## For AI Agents

### Working In This Directory

- Run `make setup` after cloning to init any submodules, create `.env` files, and install all deps
- Run `make dev` to start everything (Docker, Firebase emulators, Langfuse, backend, frontend)
- Run `make check` to health-check all services (Qdrant, Ollama, Firestore, Backend, Frontend)
- Run `make stop` to tear down all services; `make clean` to also remove Docker volumes
- Backend and frontend are independent codebases — changes to one don't require rebuilding the other
- Makefile auto-detects local Ollama (native vs Docker) and cloud LLM providers; no manual config needed

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
| Qdrant | 6333 | Vector database for RAG retrieval |
| Ollama | 11434 | Local LLM engine (optional, GPU-accelerated if native) |
| Firestore emulator | 8081 | Local Firestore for dev |
| Firebase Auth emulator | 9099 | Local Auth emulator |
| Langfuse dashboard | 8652 | Observability UI (self-hosted v3) |

### Testing Requirements

- Root-level `playwright.config.ts` for integration tests spanning both frontend and backend
- Backend tests: `cd CHATVOTE-BackEnd && poetry run pytest`
- Frontend tests: `cd CHATVOTE-FrontEnd && npm run lint && npm run type:check`
- E2E tests: `cd CHATVOTE-FrontEnd && npx playwright test`
- Evaluation tests: `make eval-prod` (DeepEval RAG testing against production data)

### Common Patterns

- Zero cloud keys needed for local dev (Ollama + Firebase emulators + Qdrant in Docker)
- Langfuse enabled by default in `make dev` — login: `admin@chatvote.local` / `chatvote123`
- Data seeding: `make seed` (Firestore + Qdrant embeddings), `make seed-local` (Ollama), `make seed-qwen` (Scaleway)
- Provider detection: Makefile checks for Ollama native, falls back to Docker, detects cloud LLM API keys in `.env`

### Key Make Targets

**Development:**
- `make setup` — Init submodules, create `.env` files, install dependencies
- `make dev` — Start all services (Docker + Firebase + Langfuse + backend + frontend)
- `make dev-backend` — Start backend only (foreground, for debugging)
- `make dev-frontend` — Start frontend only (foreground, for debugging)

**Data & Seeding:**
- `make seed` — Re-seed Firestore + Qdrant with embeddings (auto-detect provider)
- `make seed-local` — Force Ollama embeddings (768d)
- `make seed-qwen` — Force Scaleway qwen embeddings (4096d)
- `make seed-firestore` — Firestore only (no vectors)

**Testing & Checks:**
- `make check` — Health-check all 5 services
- `make test-e2e` — Run Playwright E2E tests
- `make eval-prod` — Evaluate RAG performance (DeepEval)
- `make lint-backend` / `make lint-frontend` — Run linters
- `make type-check` — TypeScript strict check

**Infrastructure:**
- `make logs` — Tail all service logs
- `make stop` — Stop all services
- `make clean` — Stop + remove Docker volumes
- `make docker-build-backend` — Build backend image locally
- `make docker-push-backend` — Push to Scaleway registry (CI only)

## Dependencies

### External

- Docker & Docker Compose — container orchestration for Qdrant + Ollama + Firebase emulators + Langfuse
- Poetry — Python dependency management (backend)
- pnpm — Node.js package manager (frontend)
- Firebase CLI — emulator tooling
- Ollama — local LLM inference (optional, recommended for Apple Silicon)
- OpenTofu — infrastructure-as-code provisioning

### Cloud (Dev/Prod)

- Google Gemini API — primary LLM provider
- OpenAI, Azure OpenAI, Anthropic Claude — LLM failover chain
- Firebase (Firestore, Auth, Storage, Hosting emulators)
- Langfuse — observability platform (self-hosted v3 locally, v2 in K8s prod)
- Scaleway — serverless backend, Qdrant managed, Cockpit logs
- Vercel — frontend hosting

<!-- MANUAL: -->
