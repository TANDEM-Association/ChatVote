# Technical Stack — chatvote Backend (CHATVOTE-BackEnd)

> This document is a **code-derived** snapshot of the technical stack and architecture of this repository.
> It is intentionally explicit about what is **confirmed by the code/config**, and what is **inferred**.

## 1) Executive summary

This repository implements the **chatvote backend**, a political information chatbot for the French municipal election context.
It exposes:

- A **REST/HTTP API** (aiohttp)
- A **real-time WebSocket API** (Socket.IO on top of aiohttp)
- A **Firebase Functions** codebase that ingests PDFs from Firebase Storage, embeds/splits them, and syncs them into a **Qdrant** vector database

The backend integrates multiple LLM providers (OpenAI, Azure OpenAI, Google Gemini, Perplexity) through **LangChain**.

---

## 2) Languages, runtimes, and packaging

### 2.1 Language

- **Python**
  - Poetry constraint: `>=3.11 <=3.12` (`pyproject.toml`)
  - Docker base image: `python:3.11.3-slim` (`Dockerfile`)

### 2.2 Dependency management / packaging

- **Poetry** (Python packaging + dependency lock)
  - `pyproject.toml`, `poetry.lock`

### 2.3 Runtime execution

- Local:
  - `poetry run python -m src.aiohttp_app --debug` (`README.md`)
- Docker:
  - Image built via `Dockerfile`
  - Entrypoint: `poetry run python -m src.aiohttp_app --host 0.0.0.0 --port 8080`

---

## 3) Architecture overview (runtime boundaries)

### 3.1 High-level component map

**Client(s)** (web / embed / localhost)
→ **aiohttp app** (`src/aiohttp_app.py`)

- REST endpoints under `/api/v1/...`
- Socket.IO server attached (WebSocket transport)

**aiohttp app**
→ **Firebase / Firestore** (primary application data + caching)
→ **Qdrant** (vector similarity search for RAG)
→ **LLM providers** (generation + query improvement + reranking + summaries)

**Firebase Storage events**
→ **Firebase Functions (Python)** (`firebase/functions/main.py`)

- PDF ingestion & chunking
- embeddings
- Qdrant upsert/delete
- Firestore source metadata updates

### 3.2 HTTP API (aiohttp)

- Framework: **aiohttp**
- Key file: `src/aiohttp_app.py`
- CORS: `aiohttp-cors`
- Validation: `aiohttp-pydantic` + Pydantic DTOs
- Health check endpoint:
  - `GET /healthz` — documented as a “Kubernetes health check endpoint” in code.

### 3.3 Real-time API (Socket.IO WebSocket)

- Library: **python-socketio**
- Mode: `AsyncServer(async_mode="aiohttp", transports=["websocket"])`
- Key file: `src/websocket_app.py`

Events include (non-exhaustive, code-derived):

- Session:
  - `chat_session_init`, `chat_session_initialized`
- Chat:
  - `chat_answer_request`, streaming via `party_response_chunk_ready`, complete via `party_response_complete`
- Sources:
  - `sources_ready`
- Summaries / meta:
  - `chat_summary_request`, `chat_summary_complete`
  - `quick_replies_and_title_ready`
- Voting behavior:
  - `voting_behavior_request`, `voting_behavior_result`, `voting_behavior_summary_chunk`, `voting_behavior_complete`

### 3.4 Data access layer

- Firestore access through **Firebase Admin SDK**:
  - `firebase_admin`, `firebase_admin.firestore`, `firebase_admin.firestore_async`
  - Code: `src/firebase_service.py`
- Credentials strategy:
  - Uses service account JSON files if present in repo root:
    - `chatvote-dev-firebase-adminsdk.json` (dev)
    - `chatvote-firebase-adminsdk.json` (prod)
  - Otherwise falls back to **Google Application Default Credentials (ADC)**.

---

## 4) LLM / AI stack

### 4.1 Orchestration

- **LangChain**
  - `langchain`, `langchain-core`, `langchain-community`

### 4.2 Providers integrated (code-confirmed)

#### OpenAI

- Chat models via `langchain-openai` (`ChatOpenAI`)
- Embeddings via `OpenAIEmbeddings`
  - Embedding model used: `text-embedding-3-large` (also used by Firebase Functions)

#### Azure OpenAI

- `AzureChatOpenAI` via `langchain-openai`
- Deployments configured in code (`src/llms.py`):
  - `gpt-4o-2024-08-06`
  - `gpt-4o-mini-2024-07-18`
- Endpoint/version configured via env:
  - `AZURE_OPENAI_ENDPOINT`
  - `OPENAI_API_VERSION`
  - `AZURE_OPENAI_API_KEY`

#### Google Gemini

- `ChatGoogleGenerativeAI` via `langchain-google-genai`
- Model configured in code: `gemini-2.0-flash`
- API key env: `GOOGLE_API_KEY`

#### Perplexity (OpenAI-compatible)

- Uses `openai.AsyncOpenAI` with `base_url="https://api.perplexity.ai"` (`src/chatbot_async.py`)
- Models configured in code:
  - `sonar` (small)
  - `sonar-pro` (large)
- API key env: `PERPLEXITY_API_KEY`

### 4.3 LLM selection strategy

- The system defines deterministic and non-deterministic model pools:
  - `DETERMINISTIC_LLMS` vs `NON_DETERMINISTIC_LLMS` (`src/llms.py`)
- It ranks models by `priority` and routes based on:
  - `LLMSize` (small/large)
  - `premium_only` flag
  - error handling / rate limit fallback

### 4.4 Observability / tracing

- **LangSmith** tracing is supported via env vars (`.env.example`):
  - `LANGCHAIN_TRACING_V2`
  - `LANGCHAIN_ENDPOINT` (defaults to `https://api.smith.langchain.com`)
  - `LANGCHAIN_API_KEY`
  - `LANGCHAIN_PROJECT`

---

## 5) Retrieval-Augmented Generation (RAG)

### 5.1 Vector database

- **Qdrant**
  - Client: `qdrant-client`
  - LangChain integration: `langchain-qdrant`
  - Config via env:
    - `QDRANT_URL`
    - `QDRANT_API_KEY`

### 5.2 Vector store usage patterns

- Key file: `src/vector_store_helper.py`

Collections are environment-suffixed (`ENV` in `dev`/`prod`):

- `all_parties_{env}`
- `justified_voting_behavior_{env}`
- `parliamentary_questions_{env}`

Namespaces:

- Party documents: `namespace = party.party_id`
- Voting behavior: `namespace = "vote_summary"`
- Parliamentary questions: `namespace = "{party_id}-parliamentary-questions"`

### 5.3 Embeddings

- Embedding model: `text-embedding-3-large`
- Embedding dimensionality noted in code: `3072`

### 5.4 Reranking

- LLM-based reranking implemented in `src/chatbot_async.py`:
  - Takes ~top N docs from vector search
  - Uses deterministic LLM output (`RerankingOutput`) to select the best docs

---

## 6) Databases, storage, and cloud services

### 6.1 Firestore (primary DB)

- Confirmed by:
  - `firebase-admin` usage (`src/firebase_service.py`)
  - Firebase config files under `firebase/`

Observed collections/paths (code-derived):

- `parties`
- `proposed_questions/{party_id}/questions`
- `cached_answers/{party_id}/{cache_key}`
- `system_status/llm_status`
- `sources/{party_id}/source_documents`

### 6.2 Firebase Storage

- Used for public PDFs organized as:
  - `public/<party-subdir>/<document_name>_<YYYY-MM-DD>.pdf`
- Firebase Functions triggers ingest PDFs on upload/delete.

### 6.3 Firebase Functions

- Runtime: `python311` (`firebase/firebase.json`)
- Trigger types:
  - `storage_fn.on_object_finalized` (upload)
  - `storage_fn.on_object_deleted` (delete)
- Resource settings used:
  - Timeout up to 540s
  - Memory up to 1GB for upload pipeline

### 6.4 Firebase rules/indexes

- Firestore rules: `firebase/firestore.rules`
- Firestore indexes: `firebase/firestore.indexes.json`
- Storage rules: `firebase/storage.rules`

### 6.5 Inferred / mentioned hosting hints (not strictly confirmed)

- `GET /healthz` is labeled as “Kubernetes health check endpoint” (`src/aiohttp_app.py`).
  - This suggests the service may be deployed in a Kubernetes-like environment, _but the repo does not include Kubernetes manifests_.
- `tests/test_websocket_app.py` contains a commented example URL that looks like **Azure Container Apps**:
  - `...azurecontainerapps.io`
  - This suggests at least one deployment target may be Azure Container Apps, _but it’s not enforced by IaC in this repo_.

---

## 7) Configuration & secrets

### 7.1 Environment variables inventory

From `.env.example`:

| Variable                | Purpose                                                                                                                   |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `API_NAME`              | Guard/indicator used by `load_env()` to ensure correct env is loaded (`chatvote-api`).                                   |
| `ENV`                   | Environment switch (`dev`/`prod`), affects CORS and Firebase credentials file selection, and Qdrant collection suffixing. |
| `LANGCHAIN_TRACING_V2`  | Enable/disable LangSmith tracing.                                                                                         |
| `LANGCHAIN_ENDPOINT`    | LangSmith endpoint.                                                                                                       |
| `LANGCHAIN_API_KEY`     | LangSmith API key.                                                                                                        |
| `LANGCHAIN_PROJECT`     | LangSmith project name.                                                                                                   |
| `OPENAI_API_KEY`        | OpenAI API key (Chat models + embeddings).                                                                                |
| `PERPLEXITY_API_KEY`    | Perplexity API key (OpenAI-compatible endpoint).                                                                          |
| `OPENAI_API_VERSION`    | Azure OpenAI API version (used by `AzureChatOpenAI`).                                                                     |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL.                                                                                                |
| `AZURE_OPENAI_API_KEY`  | Azure OpenAI API key.                                                                                                     |
| `GOOGLE_API_KEY`        | Google Gemini API key.                                                                                                    |
| `QDRANT_API_KEY`        | Qdrant API key (optional if Qdrant is public/no auth).                                                                    |
| `QDRANT_URL`            | Qdrant URL (`http://localhost:6333` default in code).                                                                     |

### 7.2 Firebase credentials

- Local development can use:
  - gcloud ADC (`gcloud auth application-default login`) **or**
  - Service account JSON at repo root

---

## 8) DevEx, quality gates, and testing

### 8.1 Linting / formatting

- **Ruff**
  - Pre-commit hooks: `ruff` + `ruff-format` (`.pre-commit-config.yaml`)

### 8.2 Type checking

- **mypy** (pre-commit)
  - config in `pyproject.toml`
  - pydantic plugin enabled

### 8.3 Testing

- **pytest** + **pytest-asyncio**
- Socket.IO end-to-end style tests:
  - `tests/test_websocket_app.py`

### 8.4 Docker

- Dockerfile installs Poetry and dependencies via `poetry install --no-root`

---

## 9) Operational notes / constraints

- **CORS policy**:

  - `dev` allows `*`
  - non-dev allows explicit origins including `https://chatvote.fr`, `https://embed.chatvote.fr`, and localhost (`src/utils.py`).

- **Caching**:

  - Party responses can be cached in Firestore (`cached_answers/...`) and randomly reused.

- **Rate limit signaling**:
  - `awrite_llm_status(is_at_rate_limit: bool)` writes to Firestore `system_status/llm_status`.

---

## 10) Appendix: primary stack dependencies (from `pyproject.toml`)

Core:

- `aiohttp`, `aiohttp-cors`, `aiohttp-pydantic`
- `python-socketio`
- `pydantic`
- `python-dotenv`

AI / RAG:

- `langchain`, `langchain-community`, `langchain-core`
- `langchain-openai`, `openai`
- `langchain-google-genai`
- `langchain-text-splitters`
- `langchain-qdrant`, `qdrant-client`
- `pypdf`

Firebase:

- `firebase-admin`

Utilities:

- `pyyaml`, `xxhash`

Dev:

- `pytest`, `pytest-asyncio`
- `ruff`, `mypy`, `pre-commit`
