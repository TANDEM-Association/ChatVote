<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# scripts

## Purpose
Developer utility scripts for local development setup, Firestore data import, and frontend type synchronisation. Not part of the production application; these are run manually or via `make` targets to set up a local development environment or perform one-off data operations.

## Key Files
| File | Description |
|------|-------------|
| `seed_local.py` | Seeds the Firestore emulator with dev data from `firebase/firestore_data/dev/` and creates required Qdrant collections; `--with-vectors` flag also generates sample embeddings via Ollama for basic RAG testing |
| `import-firestore.js` | Node.js script that imports a JSON seed file into Firestore emulator; accepts collection name, file path, and `--clean` flag to delete existing documents first |
| `generate_ts_types.py` | Exports Pydantic model JSON Schemas and Socket.IO event maps as JSON to stdout; consumed by the frontend's TypeScript type generation toolchain |
| `package.json` / `package-lock.json` | Node.js dependencies for `import-firestore.js` (Firebase Admin SDK for Node) |

## For AI Agents

### Working In This Directory
- Run `seed_local.py` only when the Firestore emulator is running on `localhost:8081` and Qdrant is running on `localhost:6333`
- `seed_local.py` forces `ENV=local` and `API_NAME=chatvote-api` before importing any `src` modules; do not import `src` modules before setting these env vars in other scripts
- `import-firestore.js` requires `node` and `npm install` in this directory before first use
- `generate_ts_types.py` writes to stdout; redirect to a file or pipe to the frontend tool: `poetry run python scripts/generate_ts_types.py > types.json`

### Testing Requirements
Scripts are validated by running them against local services. Verify `seed_local.py` with:
```bash
# Prereqs: Firebase emulator running, Qdrant running
poetry run python scripts/seed_local.py
# With sample vectors (requires Ollama):
poetry run python scripts/seed_local.py --with-vectors
```

### Common Patterns
- All Python scripts add the repo root to `sys.path` to enable `from src.models import ...` imports without installing the package
- Seed data lives in `firebase/firestore_data/dev/`; update JSON files there, not in this directory
- The `--clean` flag on `import-firestore.js` is destructive; use it to reset a collection to a known state during development

## Dependencies

### Internal
- `firebase/firestore_data/dev/` — seed data consumed by both scripts
- `src/models/` — imported by `generate_ts_types.py` to extract JSON schemas
- `src/vector_store_helper.py` — imported by `seed_local.py` for Qdrant collection setup

### External
| Package | Purpose |
|---------|---------|
| `firebase-admin` (Node.js) | Used by `import-firestore.js` to write to Firestore emulator |
| `firebase-admin` (Python) | Used by `seed_local.py` for Firestore emulator access |

<!-- MANUAL: -->
