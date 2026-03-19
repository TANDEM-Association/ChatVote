<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/services

## Purpose
Background services that run alongside the HTTP/Socket.IO server. Handles automated data ingestion (manifesto PDF indexing, candidate website scraping and indexing), change detection via Firestore real-time listeners, periodic scheduling via APScheduler cron jobs, and French municipality data synchronisation from the government API.

## Key Files
| File | Description |
|------|-------------|
| `manifesto_indexer.py` | Fetches party manifesto PDFs from Firebase Storage URLs into memory, extracts text with `pypdf`, chunks with `RecursiveCharacterTextSplitter` (1000 chars / 200 overlap), embeds, and upserts into Qdrant `all_parties_` collection |
| `candidate_website_scraper.py` | Playwright-based async BFS crawler: sitemap.xml → homepage → internal links (max depth 2, max 15 pages + 5 PDFs per site); content extraction via BeautifulSoup; returns `ScrapedWebsite` with page content |
| `candidate_indexer.py` | Orchestrates scrape → chunk → embed → upsert pipeline for candidate websites into `candidates_websites_` collection; supports single candidate or all candidates with a website URL |
| `firestore_listener.py` | Firestore real-time listeners on `parties` and `candidates` collections; triggers manifesto or website indexing when documents are added or modified; runs in a separate thread and dispatches to the main asyncio event loop |
| `scheduler.py` | APScheduler `AsyncIOScheduler` with two cron jobs: municipalities sync every Sunday at midnight, candidate website re-indexing daily at 3 AM |
| `municipalities_sync.py` | Fetches all French communes from `geo.api.gouv.fr` with full metadata (code, name, region, department, EPCI, population, etc.) and writes to `firebase/firestore_data/dev/municipalities.json` |
| `profession_indexer.py` | Indexes profession de foi PDFs from Firebase Storage into `candidates_websites_` Qdrant collection with namespace per candidate |
| `theme_classifier.py` | LLM-based theme classification for Qdrant chunks using 14-theme taxonomy; classifies chunks into theme + sub-theme |
| `chunk_classifier.py` | Classifies chunk source types (manifesto, website, profession de foi) and enriches metadata |
| `backfill_themes.py` | CLI tool to backfill theme/sub-theme on existing Qdrant chunks via `theme_classifier`; supports batch + concurrent LLM calls |
| `backfill_metadata.py` | Backfills missing metadata fields (URLs, titles, source types) on existing Qdrant points |
| `chunking.py` | Shared text chunking utilities using `RecursiveCharacterTextSplitter` with configurable size/overlap |
| `content_processing.py` | Content extraction and cleaning from HTML/PDF sources; normalises text for embedding |
| `pdf_extract.py` | PDF text extraction with `pypdf`; handles corrupted/encrypted PDFs gracefully |
| `qdrant_ops.py` | Low-level Qdrant operations: batch upsert, scroll, delete by filter, collection management |
| `document_upload.py` | Uploads documents (PDFs, scraped content) to Firebase Storage |
| `firecrawl_scraper.py` | Alternative scraper using Firecrawl API for JavaScript-heavy sites |
| `playwright_fast_scraper.py` | Optimised Playwright scraper with connection pooling and parallel page processing |
| `k8s_job_launcher.py` | Launches Kubernetes Jobs for batch indexing/scraping operations on the cluster |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `data_pipeline/` | Orchestration layer for the full scrape → chunk → embed → index pipeline |

## For AI Agents

### Working In This Directory
- All indexing functions are async; call with `await` from an async context or schedule via the APScheduler
- `firestore_listener.py` listener callbacks run in a Firestore SDK background thread; use `asyncio.run_coroutine_threadsafe(coro, event_loop)` to dispatch back to the main loop
- Scraper configuration constants are at the top of `candidate_website_scraper.py`: `MAX_PAGES_PER_SITE=15`, `MAX_PDFS_PER_SITE=5`, `MAX_CRAWL_DEPTH=2`
- Text splitter settings: chunk size 1000 chars, overlap 200 chars — same for both manifesto and candidate indexers
- Qdrant upsert is idempotent: existing vectors for a candidate/party are deleted before re-indexing

### Testing Requirements
Services require live infrastructure (Firestore emulator, Qdrant, Ollama for local embeddings). Use admin endpoints to trigger indexing manually during development:
```bash
# Index all manifestos
curl -X POST http://localhost:8080/api/v1/admin/index-all-manifestos

# Index single candidate
curl -X POST http://localhost:8080/api/v1/admin/index-candidate-website/{candidate_id}

# Check listener status
curl http://localhost:8080/api/v1/admin/listener-status
```

### Common Patterns
- All indexing functions return `dict[str, int]` mapping entity ID to chunk count, or a single `int` for single-entity variants
- Playwright is required for `candidate_website_scraper.py`; install browsers with `playwright install chromium`
- The `_indexed_manifesto_urls` and `_indexed_candidate_urls` module-level dicts in `firestore_listener.py` deduplicate indexing when Firestore emits initial snapshots on listener start

## Dependencies

### Internal
- `src/firebase_service.py` — Firestore reads for party and candidate records
- `src/vector_store_helper.py` — Qdrant client and collection names
- `src/models/party.py`, `src/models/candidate.py` — entity types

### External
| Package | Purpose |
|---------|---------|
| `playwright` | Headless Chromium for JavaScript-rendered candidate websites |
| `beautifulsoup4` | HTML content extraction |
| `pypdf` | PDF text extraction |
| `aiohttp` | Async HTTP client for PDF downloads and geo API |
| `langchain-text-splitters` | `RecursiveCharacterTextSplitter` |
| `apscheduler` | Cron job scheduling |
| `defusedxml` | Safe XML parsing for sitemap.xml |
| `google-cloud-firestore` | Real-time listener SDK (via `firebase-admin`) |

<!-- MANUAL: -->
