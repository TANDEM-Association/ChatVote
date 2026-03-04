<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# firebase/functions

## Purpose
Firebase Cloud Functions (Python runtime) that automate party manifesto PDF ingestion. Triggered by Firebase Storage events when PDFs are uploaded or deleted under the `public/` path. On upload: downloads the PDF, chunks it with LangChain's text splitter, generates embeddings via OpenAI `text-embedding-3-large`, and upserts into the Qdrant `all_parties_{env}` collection. On delete: removes all Qdrant points associated with the deleted document and updates Firestore source metadata.

## Key Files
| File | Description |
|------|-------------|
| `main.py` | Two Cloud Function handlers: `on_object_finalized` (PDF upload → chunk → embed → Qdrant upsert) and `on_object_deleted` (delete Qdrant points + Firestore metadata); deployed to EUROPE_WEST1 (dev) or US_EAST1 (prod) |
| `models.py` | `PartySource` Pydantic model for Firestore source document metadata |
| `requirements.txt` | Python dependencies for the functions runtime (independent of the main `pyproject.toml`) |
| `.python-version` | Python version pin for the functions runtime |

## For AI Agents

### Working In This Directory
- This is an **independent Python environment** — it has its own `requirements.txt` and does not share Poetry dependencies with the main backend
- Deploy with: `firebase deploy --only functions` (from repo root or `firebase/` directory)
- Environment variables are Firebase `StringParam` values (`ENV`, `OPENAI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`) — set them via `firebase functions:config:set` or the Firebase console, not `.env` files
- PDF path convention: `public/<party-subdir>/<document_name>_<YYYY-MM-DD>.pdf`; the function parses party ID from the storage path segments
- Embedding model: `text-embedding-3-large` (3072 dimensions) — must match the `EMBEDDING_DIM` in the main backend's `vector_store_helper.py`
- Chunk size: 1000 chars / 200 overlap (same as `manifesto_indexer.py` in the main backend)
- Function resource limits: 540s timeout, up to 1 GB memory for the upload handler

### Testing Requirements
```bash
# Start Firebase emulators with functions support
firebase emulators:start --only functions,storage,firestore

# Upload a test PDF to the Storage emulator to trigger the function
# (requires gsutil or Firebase Storage emulator UI)
```
End-to-end function testing requires live or emulated Qdrant since the functions write directly to the vector database.

### Common Patterns
- Qdrant collection name follows the same env-suffix convention: `all_parties_{env}` where `env` is read from `ENV` StringParam
- Points are identified by a UUID derived from the document name to enable idempotent upsert and clean delete
- On delete, the function uses `qdrant_client.delete(collection_name, points_selector=FilterSelector(...))` filtered by document name metadata

## Dependencies

### Internal
- `models.py` — `PartySource` model for Firestore source metadata

### External
| Package | Purpose |
|---------|---------|
| `firebase-functions` (Python) | Cloud Function decorators and trigger types |
| `firebase-admin` | Firestore + Storage access within functions |
| `langchain-openai` | `OpenAIEmbeddings` for `text-embedding-3-large` |
| `langchain-community` | `PyPDFLoader` for PDF loading |
| `langchain-text-splitters` | `RecursiveCharacterTextSplitter` |
| `qdrant-client` | Qdrant upsert and delete |

<!-- MANUAL: -->
