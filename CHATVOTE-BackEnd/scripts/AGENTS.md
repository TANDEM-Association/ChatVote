<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# scripts

## Purpose
Developer utility scripts for local development, data auditing, Firestore operations, Qdrant management, candidate pipeline operations, and frontend type synchronisation. Not part of the production application; run manually or via `make` targets.

## Key Files
| File | Description |
|------|-------------|
| `seed_local.py` | Seeds Firestore emulator + Qdrant collections from `firebase/firestore_data/dev/`; `--with-vectors` generates sample embeddings via Ollama |
| `import-firestore.js` | Node.js: imports JSON seed file into Firestore emulator; `--clean` flag resets collection |
| `export-firestore.js` | Node.js: exports Firestore emulator data to JSON files |
| `generate_ts_types.py` | Exports Pydantic JSON Schemas + Socket.IO event maps for frontend TS type generation |
| `candidate_id_audit.py` | Audits candidate ID consistency across Firestore and Qdrant |
| `candidate_id_audit_figures.py` | Generates visual charts from candidate ID audit results |
| `municipality_audit.py` | Audits municipality data integrity in Firestore |
| `qdrant_snapshot.py` | Creates and manages Qdrant collection snapshots for backup |
| `chunk_health_audit.py` | Audits Qdrant chunk metadata completeness and quality |
| `pipeline_audit.py` | End-to-end data pipeline health audit |
| `pipeline_audit_figures.py` | Generates visual reports from pipeline audit results |
| `crawl_all_candidates.py` | Batch-crawls all candidate websites |
| `reindex_all_damaged_prod.py` | Re-indexes damaged/incomplete Qdrant points in production |
| `reindex_candidate_prod.py` | Re-indexes a single candidate in production |
| `reindex_paris_prod.py` | Re-indexes Paris-specific candidates in production |
| `migrate_dev_to_prod_qdrant.py` | Migrates Qdrant data from dev to prod collections |
| `fetch_second_turn_candidates.py` | Fetches second-round election candidate data |
| `ingest_second_tour_candidatures.py` | Ingests second-round candidature data into Firestore |
| `seed_all_profession_communes.py` | Seeds profession de foi PDFs for all communes |
| `seed_commune_vectors.py` | Seeds Qdrant vectors for commune-level data |
| `upload_all_professions_to_storage.py` | Uploads all profession de foi PDFs to Firebase Storage |
| `upload_poster_pdfs_to_storage.py` | Uploads election poster PDFs to Firebase Storage |
| `index_election_posters.py` | Indexes election poster content into Qdrant |
| `index_posters_prod.py` | Production variant of poster indexing |
| `backfill_md_urls.py` | Backfills markdown URLs in Qdrant metadata |
| `backfill_profession_urls.py` | Backfills profession de foi URLs in metadata |
| `backfill_urls.py` | General URL backfill utility |
| `validate_qdrant_metadata.py` | Validates Qdrant point metadata against expected schema |
| `validate_chat_e2e.py` | End-to-end chat validation script |
| `check_prod_status.py` | Health check for production services |
| `diagnose_coverage.py` | Diagnoses RAG coverage gaps by theme/party |
| `sync_crawl_status.py` | Syncs crawl status from scraper to Firestore |
| `optimize_prompts.py` | Prompt optimization utilities |
| `eval_report.py` | Generates evaluation reports from test results |
| `generate_goldens.py` | Generates golden test datasets for evaluation |
| `migrate_municipalities_to_prod.js` | Migrates municipality data to production Firestore |
| `migrate_firebase_urls_to_s3.py` | Migrates Firebase Storage URLs to S3 |
| `snapshot.Dockerfile` | Dockerfile for Qdrant snapshot operations |

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
