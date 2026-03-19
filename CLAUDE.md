# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChatVote is an AI-powered political information chatbot for French elections. Citizens can ask questions to multiple political parties simultaneously and receive source-backed answers via RAG (Retrieval-Augmented Generation). The project is a monorepo with two independent codebases:

- **`CHATVOTE-BackEnd/`** — Python async API (aiohttp + Socket.IO + LangChain + Qdrant)
- **`CHATVOTE-FrontEnd/`** — Next.js 16 React app (TypeScript, Zustand, Tailwind, Socket.IO client)

## Common Commands

### Local Development (zero cloud keys)

```bash
make setup                         # One-time: init submodules, create .env, install deps
make dev                           # Start everything (Docker, Firebase, backend, frontend)
make dev                           # Includes Langfuse observability (dashboard: localhost:8652)
make check                         # Health-check all services
make logs                          # Tail all service logs
make stop                          # Stop everything
make clean                         # Stop + remove Docker volumes
make seed                          # Re-seed Firestore + Qdrant collections + embeddings (uses .env provider)
make seed-qwen                     # Same but force Scaleway qwen embeddings (4096d)
make seed-local                    # Same but force Ollama embeddings (768d)
make dev-backend                   # Start backend in foreground (debugging)
make dev-frontend                  # Start frontend in foreground (debugging)
```

### Backend (`CHATVOTE-BackEnd/`)

```bash
poetry install --with dev          # Install dependencies
poetry run python -m src.aiohttp_app --debug  # Dev server on :8080
poetry run pytest tests/test_websocket_app.py -s  # Run tests
poetry run ruff check .            # Lint
poetry run ruff format .           # Format
poetry run mypy src/               # Type check
docker-compose up                  # Start Qdrant + API
```

### Frontend (`CHATVOTE-FrontEnd/`)

```bash
pnpm install --frozen-lockfile     # Install dependencies
npm run dev                        # Dev server on :3000 (Turbopack)
npm run build                      # Production build
npm run lint                       # ESLint
npm run lint:fix                   # ESLint autofix
npm run format                     # Prettier format
npm run format:check               # Check formatting
npm run type:check                 # TypeScript strict check
ANALYZE=true npm run build         # Bundle analysis
```

## Architecture

### Real-Time Communication Flow

```
Browser (Next.js) ─── Socket.IO ───→ websocket_app.py ───→ chatbot_async.py
                                                                  │
                                              ┌───────────────────┤
                                              ▼                   ▼
                                     Qdrant (RAG search)    LLM providers
                                              │            (Gemini/OpenAI/
                                              ▼             Azure/Claude)
                                     Reranked sources           │
                                              └────────┬────────┘
                                                       ▼
                                              Streamed response
                                              chunks back via
                                              Socket.IO events
```

### Backend Key Files

| File | Purpose |
|------|---------|
| `src/aiohttp_app.py` | HTTP server, REST API routes, app lifecycle |
| `src/websocket_app.py` | Socket.IO event handlers for real-time streaming |
| `src/chatbot_async.py` | Core LLM response generation, RAG pipeline (largest file ~53KB) |
| `src/llms.py` | LLM provider initialization with automatic failover chain |
| `src/prompts.py` / `src/prompts_en.py` | All prompt templates (FR/EN) |
| `src/firebase_service.py` | Firestore async CRUD operations |
| `src/vector_store_helper.py` | Qdrant vector store setup and operations |
| `src/models/` | Pydantic models (`chat.py`, `party.py`, `candidate.py`, `vote.py`, `dtos.py`) |
| `src/services/` | Background services (scraping, indexing, scheduling) |

### LLM Provider Failover

Configured in `src/llms.py`. Primary: Google Gemini 2.0-flash. Falls back through OpenAI, Azure, Anthropic. Embeddings: Google `gemini-embedding-001` (3072 dims), fallback to OpenAI `text-embedding-3-large`.

### Qdrant Collections (Vector DB)

Collections are environment-suffixed (`_dev` / `_prod`):

- `all_parties_{env}` — Party manifesto PDFs (namespace: `{party_id}`)
- `candidates_websites_{env}` — Scraped candidate websites (namespace: `{candidate_id}`)
- `justified_voting_behavior_{env}` — Parliamentary voting records
- `parliamentary_questions_{env}` — Parliamentary questions

### RAG Pipeline (`chatbot_async.py`)

1. User question → LLM improves/expands query
2. Vector similarity search in Qdrant (manifestos/candidates/voting data)
3. LLM-based reranking of retrieved documents
4. Generate streamed response with source attribution

### Frontend Key Patterns

- **State**: Zustand store in `src/lib/stores/chat-store.ts` with modular action handlers in `src/lib/stores/actions/`
- **Socket.IO wrapper**: `src/lib/chat-socket.ts` (type-safe events defined in `src/lib/socket.types.ts`)
- **Providers**: `src/components/providers/` — SocketProvider, AuthProvider, AppProvider
- **i18n**: next-intl with FR/EN messages in `src/i18n/messages/`
- **UI**: shadcn/ui components in `src/components/ui/`, Radix primitives, Tailwind CSS v4
- **Routing**: Next.js App Router — `src/app/chat/[chatId]/` for chat sessions, `src/app/api/` for server routes

### Socket.IO Events

**Client → Server**: `chat_session_init`, `chat_answer_request`, `pro_con_perspective_request`, `voting_behavior_request`

**Server → Client** (streamed): `responding_parties_selected`, `sources_ready`, `party_response_chunk_ready`, `quick_replies_and_title_ready`, `chat_response_complete`

### Data Storage

- **Firestore**: Chat sessions, parties, candidates, municipalities, cached answers, feedback
- **Qdrant**: Vector embeddings for RAG retrieval
- **Firebase Storage**: Party manifesto PDFs
- **Firebase Auth**: Email, Google, Microsoft, Anonymous

## Environment Variables

Backend needs at minimum: `ENV` (dev/prod), one LLM API key (`GOOGLE_API_KEY` recommended), `QDRANT_URL`, Firebase credentials. See `CHATVOTE-BackEnd/.env.example`.

Frontend needs: Firebase config (`NEXT_PUBLIC_FIREBASE_*`), `NEXT_PUBLIC_SOCKET_URL`, Stripe keys, `NEXT_PUBLIC_APP_URL`. See `CHATVOTE-FrontEnd/.env.local`.

### Observability (Langfuse)

Langfuse self-hosted provides AI tracing (LLM calls, Qdrant retrieval spans, tool invocations). Enabled by default in `make dev`. Dashboard at `http://localhost:8652` (login: `admin@chatvote.local` / `admin123`). Frontend env vars in `.env.local`:

- `LANGFUSE_SECRET_KEY` — enables Langfuse tracing when set (local: `sk-lf-local`)
- `LANGFUSE_PUBLIC_KEY` — Langfuse public key (local: `pk-lf-local`)
- `LANGFUSE_BASEURL` — Langfuse server URL (local: `http://localhost:8652`)

Fallback: set `LANGCHAIN_TRACING=true` + `LANGCHAIN_API_KEY` for LangSmith cloud tracing instead. With neither set, tracing is disabled (no-op).

Production Langfuse runs as v3 (Postgres + ClickHouse + Redis) on the K8s cluster. K8s manifests in `k8s/prod/langfuse/`. Frontend tracing uses OTEL via `@langfuse/otel` LangfuseSpanProcessor + Langfuse SDK client for trace-level I/O. Python backend instrumentation is deferred (separate PR).

## Scraping & Indexing Pipeline

`candidate_website_scraper.py` uses Playwright (headless Chromium) for BFS crawling of candidate websites (sitemap.xml → homepage → internal links, max depth 2, max 15 pages + 5 PDFs per site). Content extraction uses BeautifulSoup — no AI involved in scraping itself.

`candidate_indexer.py` takes scraped content, chunks it with LangChain's `RecursiveCharacterTextSplitter` (1000 chars, 200 overlap), generates embeddings, and indexes into Qdrant. The AI part is only in the embedding step.

`manifesto_indexer.py` handles party PDF manifestos with the same chunk → embed → index pattern.
