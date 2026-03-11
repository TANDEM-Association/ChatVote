# Data Sources Pipeline — Implementation Plan

## Phase 1: Backend pipeline framework + first 3 nodes

### Step 1: Base framework (`src/services/data_pipeline/`)

Create `src/services/data_pipeline/__init__.py` and `base.py`:
- `DataSourceNode` ABC with: `node_id`, `label`, `run(force: bool)`, `get_status()`
- Firestore helpers: `load_config()`, `save_config()`, `update_status()`, `save_checkpoint()`
- Node registry: `PIPELINE_NODES: dict[str, DataSourceNode]`
- Status enum: idle, running, success, error
- Incremental check: `should_skip(current_hash) -> bool`

### Step 2: Candidatures node (`candidatures.py`)

- Downloads CSV from data.gouv.fr static URL (138MB)
- Checks `Last-Modified` header first → skip if unchanged
- Parses with csv.DictReader (delimiter `;`)
- Filters to top N communes (setting: `top_communes`, default 287)
- Needs population data → depends on population node having run
- Stores parsed data in a temp cache (dict in memory or temp file)
- Checkpoint: `source_hash` (SHA-256 of first 10KB + file size)
- Counts: `total_rows`, `matched_communes`, `total_lists`, `total_candidates`

### Step 3: Population node (`population.py`)

- Downloads INSEE communes population CSV
- Source URL configurable (env var or setting)
- Parses, sorts by population, picks top N
- Checkpoint: `source_hash`
- Counts: `total_communes`, `largest`, `smallest`
- Note: this CSV rarely changes, so caching is important

### Step 4: Websites node (`websites.py`)

- Uses `google.oauth2.service_account` with `GOOGLE_SHEETS_CREDENTIALS_JSON`
- Calls Drive API `files.get` for `modifiedTime` → skip if unchanged
- Downloads xlsx via `alt=media`, parses with openpyxl
- Matches candidates by normalized commune name + lastname
- Checkpoint: `source_modified` (Drive modifiedTime)
- Counts: `total_rows`, `with_url`, `matched_to_seed`
- Requires: `GOOGLE_SHEETS_CREDENTIALS_JSON`, `GOOGLE_SHEET_ID`

### Step 5: Admin API endpoints

In `src/aiohttp_app.py`, add routes under `/api/v1/admin/data-sources/`:
- `GET /status` — returns all node configs from Firestore
- `POST /run/{node_id}` — body `{force: bool}`, runs node in background task
- `PUT /config/{node_id}` — updates settings + enabled flag
- `POST /bust-cache` — resets all checkpoints
- All guarded by `X-Admin-Secret` == `ADMIN_UPLOAD_SECRET`

### Step 6: Env vars

Add to `.env.local.template` and `.env.example`:
- `GOOGLE_SHEETS_CREDENTIALS_JSON=` (raw JSON string)
- `GOOGLE_SHEET_ID=1JZJSQSOwlMWK5ZdXuEHetVxpesuuK_LI`
- `DATA_GOUV_CANDIDATURES_URL=` (optional override)

---

## Phase 2: Seed + professions de foi nodes

### Step 7: Seed node (`seed.py`)

- Merges outputs from candidatures + population + websites + professions nodes
- Builds: municipalities, electoral_lists, candidates collections
- Incremental Firestore writes: hash each doc, skip if unchanged
- Also writes JSON fixtures to `firebase/firestore_data/dev/` for local dev
- Checkpoint: per-collection doc count + content hash
- Counts: `municipalities`, `electoral_lists`, `candidates`, `with_website`, `with_manifesto`

### Step 8: Professions de foi node (`professions.py`)

- Port scraping logic from `chatvote-cowork/scraper/scrape_elections.py`
- Uses aiohttp (not Playwright) where possible; Playwright for JS-rendered pages
- Per-commune incremental: track `{commune_code: last_scraped_at}` in checkpoints
- Setting: `top_communes` (inherited from pipeline), `max_pdfs_per_commune`
- Counts: `communes_scraped`, `pdfs_found`, `pdfs_downloaded`
- TODO marker: "Extract to separate service for production (Playwright is heavy)"

---

## Phase 3: Qdrant indexer node

### Step 9: Indexer node (`indexer.py`)

- Wraps existing `manifesto_indexer.py` + `candidate_indexer.py`
- Disabled by default (costly LLM calls)
- Per-candidate/party content hash → skip if source unchanged
- Settings: `enabled` (default false), `batch_size`, `embedding_provider`
- Counts: `chunks_indexed`, `candidates_indexed`, `parties_indexed`

---

## Phase 4: Frontend admin page

### Step 10: Data sources page (`/admin/data-sources/[secret]`)

- Same auth pattern as upload page: URL secret + X-Admin-Secret header
- Layout: DAG of 6 cards (3 sources → seed ← professions → indexer)
- Each card component:
  - Status badge (colored dot + label)
  - Last run timestamp + duration
  - Key counts (contextual per node)
  - Toggle enabled/disabled
  - "Run" button (normal) + "Force" button (ignores checkpoints)
  - Expandable settings panel (top N communes, sheet ID, etc.)
- Global toolbar: "Run all enabled", "Force re-run all", "Bust cache"
- Auto-poll: `setInterval` every 5s while any node status is "running"
- Error display: last error message in red, expandable stack trace

### Step 11: Pipeline visualization

- Visual DAG with arrows showing dependencies
- Nodes dim when disabled
- Animated pulse on running nodes
- Green/yellow/red border based on status

---

## File summary

### New files (backend)
- `src/services/data_pipeline/__init__.py`
- `src/services/data_pipeline/base.py`
- `src/services/data_pipeline/candidatures.py`
- `src/services/data_pipeline/population.py`
- `src/services/data_pipeline/websites.py`
- `src/services/data_pipeline/professions.py`
- `src/services/data_pipeline/seed.py`
- `src/services/data_pipeline/indexer.py`

### New files (frontend)
- `src/app/admin/data-sources/[secret]/page.tsx`

### Modified files
- `src/aiohttp_app.py` — add admin/data-sources routes
- `.env.local.template` — add Google Sheets env vars
- `pyproject.toml` — add `openpyxl` as regular dependency (not just dev)

### Unchanged
- `scripts/seed_local.py` — stays as dev shortcut
- `firebase/firestore_data/dev/*.json` — still generated, used for local dev
