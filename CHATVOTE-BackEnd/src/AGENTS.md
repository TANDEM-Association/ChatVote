<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src

## Purpose
Core application source package. Contains the HTTP server, Socket.IO event handlers, RAG pipeline, LLM provider management, Firestore data access, Qdrant vector store helpers, prompt templates, i18n utilities, Pydantic models, and background services. Every runtime feature of the ChatVote API lives here.

## Key Files
| File | Description |
|------|-------------|
| `aiohttp_app.py` | aiohttp app factory; REST routes under `/api/v1`; mounts Socket.IO; starts Firestore listeners and APScheduler on startup |
| `websocket_app.py` | Socket.IO `AsyncServer`; all real-time event handlers (`chat_session_init`, `chat_answer_request`, `voting_behavior_request`, etc.) |
| `chatbot_async.py` | Core RAG pipeline — query improvement, document retrieval, LLM-based reranking, streaming response generation, pro/con perspectives, voting behaviour summaries (~53 KB, largest file) |
| `llms.py` | LLM provider registry; `NON_DETERMINISTIC_LLMS` and `DETERMINISTIC_LLMS` pools; `stream_answer_from_llms` with mid-stream fallback and `StreamResetMarker`; rate-limit signalling to Firestore |
| `firebase_service.py` | Async Firestore CRUD — parties, candidates, cached answers, proposed questions, municipalities, LLM status |
| `vector_store_helper.py` | Qdrant client; lazy-initialised vector stores for all four collections; `identify_relevant_docs*` search functions; combined manifesto + candidate search |
| `prompts.py` | French prompt templates for all LLM calls |
| `prompts_en.py` | English prompt templates |
| `utils.py` | `load_env()` guard, `safe_load_api_key()`, `get_cors_allowed_origins()`, chat history string builder, document string builder, reference sanitiser, xxhash cache key |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `models/` | Pydantic data models (see `models/AGENTS.md`) |
| `services/` | Background services: scraping, indexing, Firestore listener, scheduler, municipalities sync (see `services/AGENTS.md`) |
| `i18n/` | Translation loader and locale JSON files (see `i18n/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Import path root is the repo root (`src` is a package); run with `python -m src.aiohttp_app`
- `load_env()` must be called before any env-dependent import; it raises `ValueError` if `API_NAME` is missing or wrong
- Socket.IO events are defined in `websocket_app.py`; the `sio` instance is imported into `aiohttp_app.py` and attached to the aiohttp app with `sio.attach(app)`
- LLM calls must go through helpers in `llms.py` — do not instantiate provider clients directly in feature code
- All Firestore access must use the async client (`async_db`) from `firebase_service.py`; the sync `db` client is only used by Firestore listeners (which run in threads)
- Qdrant collections are lazily created by `vector_store_helper._ensure_collection_exists()`; dimension mismatch triggers automatic recreation

### Testing Requirements
```bash
# Integration tests require a local server running on :8080
poetry run python -m src.aiohttp_app --debug &
poetry run pytest tests/test_websocket_app.py -s
```

### Common Patterns
- Streaming responses yield `BaseMessageChunk | StreamResetMarker`; handlers must check for `StreamResetMarker` and clear accumulated state before re-emitting to the client
- Cache keys are xxhash-64 hex digests of serialised conversation history strings
- Prompt templates are selected based on the session `locale` field (`"fr"` | `"en"`)
- Qdrant namespace field: `metadata.namespace` = `party_id` for manifestos, `"{party_id}-parliamentary-questions"` for parliamentary questions, `"vote_summary"` for voting behaviour
- CORS origins are resolved by `get_cors_allowed_origins(ENV)`; wildcard in dev/local, explicit list in prod

## Dependencies

### Internal
- `src/models/` — all Pydantic types
- `src/services/` — background indexing and scraping
- `src/i18n/` — translation strings

### External
| Package | Purpose |
|---------|---------|
| `aiohttp` | HTTP server and async HTTP client |
| `python-socketio` | Socket.IO async server |
| `langchain-core` / `langchain` | LLM chain primitives |
| `langchain-google-genai` | Gemini chat + embedding models |
| `langchain-openai` | OpenAI and Azure OpenAI chat + embedding models |
| `langchain-anthropic` | Anthropic Claude models |
| `langchain-ollama` | Local Ollama models |
| `langchain-qdrant` | Qdrant vector store integration |
| `qdrant-client` | Direct Qdrant search and collection management |
| `firebase-admin` | Firestore async client |
| `pydantic` | Model validation and serialisation |
| `xxhash` | Cache key hashing |
| `python-dotenv` | `.env` file loading |

<!-- MANUAL: -->
