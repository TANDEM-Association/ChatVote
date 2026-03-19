<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# tests

## Purpose
Comprehensive test suite covering Socket.IO integration tests, unit tests for individual services, and evaluation/red-team harnesses. Tests range from full end-to-end WebSocket flows to isolated unit tests for indexing, chunking, classification, and vector search.

## Key Files
| File | Description |
|------|-------------|
| `test_websocket_app.py` | Socket.IO integration tests; uses `pytest-asyncio`; `TestHelpers` class provides reusable event send-and-wait utilities |
| `conftest.py` | Shared pytest fixtures (Qdrant client, Firestore emulator, test data) |
| `test_chunk_classifier.py` | Tests for chunk source-type classification logic |
| `test_chunk_metadata.py` | Tests for `ChunkMetadata` model validation and serialisation |
| `test_chunking.py` | Tests for text splitting/chunking utilities |
| `test_content_processing.py` | Tests for HTML/PDF content extraction and cleaning |
| `test_candidate_indexer.py` | Tests for candidate website indexing pipeline |
| `test_manifesto_indexer.py` | Tests for manifesto PDF indexing pipeline |
| `test_pdf_extract.py` | Tests for PDF text extraction edge cases |
| `test_qdrant_ops.py` | Tests for low-level Qdrant operations |
| `test_vector_store_helper.py` | Tests for collection management, alias resolution |
| `test_vector_search.py` | Tests for RAG vector similarity search |
| `test_theme_classifier.py` | Tests for LLM-based theme classification |
| `test_source_builder.py` | Tests for source attribution formatting |
| `test_topic_stats.py` | Tests for topic/theme statistics aggregation |
| `test_seed_functions.py` | Tests for Firestore seeding utilities |
| `test_crawl_scraper_cleanup.py` | Tests for scraper output cleanup |
| `test_crawl_scraper_flow.py` | Tests for end-to-end crawl flow |
| `test_indexer_node.py` | Tests for indexer pipeline nodes |
| `test_pipeline_base.py` | Tests for data pipeline base classes |
| `test_pipeline_context.py` | Tests for pipeline execution context |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `unit/` | Isolated unit tests (no external services required) |
| `eval/` | LLM evaluation harnesses (response quality, retrieval accuracy) |
| `red_team/` | Adversarial/red-team test scenarios for prompt injection, jailbreak |
| `fixtures/` | Shared test data (sample PDFs, HTML, JSON) |

## For AI Agents

### Working In This Directory
- Tests are **integration tests** — they require a fully running backend on `http://localhost:8080` with Firestore, Qdrant, and at least one LLM API key configured
- `BASE_URL = "http://localhost:8080"` is hardcoded at the top of the test file; override by editing that constant when targeting a remote environment
- Tests use real Socket.IO clients and real LLM calls; they are slow (seconds per test) and require network access
- `load_env()` is called at module import time; ensure `.env` is present with valid credentials before running

### Testing Requirements
```bash
# 1. Start the local server in a separate terminal
ENV=local poetry run python -m src.aiohttp_app --debug

# 2. Run tests
poetry run pytest tests/test_websocket_app.py -s -v

# 3. Run a single test
poetry run pytest tests/test_websocket_app.py::TestClassName::test_name -s
```

### Common Patterns
- Each test function creates a new `socketio.Client()`, connects, emits `chat_session_init`, then emits the action under test
- `TestHelpers.send_and_verify_chat_session_init()` abstracts the session initialisation handshake shared by all chat tests
- `asyncio.wait_for(future, timeout=N)` is used to assert events arrive within a timeout; increase timeouts if running against slow LLMs
- DTOs from `src/models/dtos.py` are used to construct event payloads via `model_dump()`; this ensures test payloads stay in sync with the wire format

## Dependencies

### Internal
- `src/models/dtos.py` — all DTO classes used to build and validate test payloads
- `src/models/party.py`, `src/models/chat.py` — types used in test assertions
- `src/utils.py` — `load_env()` called at test module load

### External
| Package | Purpose |
|---------|---------|
| `pytest` ~8.3 | Test framework |
| `pytest-asyncio` ~0.24 | Async test support |
| `python-socketio` | Socket.IO client for connecting to the server under test |
| `websocket-client` | WebSocket transport used by python-socketio client |

<!-- MANUAL: -->
