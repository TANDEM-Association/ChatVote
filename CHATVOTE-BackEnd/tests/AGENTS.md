<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# tests

## Purpose
End-to-end integration test suite for the Socket.IO WebSocket API. Tests connect to a running local server via the python-socketio client, emit events, and assert on received event payloads. Covers chat session lifecycle, streaming response handling, pro/con perspective generation, candidate pro/con, voting behaviour, and chat summary flows.

## Key Files
| File | Description |
|------|-------------|
| `test_websocket_app.py` | All Socket.IO integration tests; uses `pytest-asyncio` for async test functions; `TestHelpers` class provides reusable event send-and-wait utilities |
| `__init__.py` | Package marker |

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
