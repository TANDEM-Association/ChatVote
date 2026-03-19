<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# data/scripts

## Purpose
Jupyter notebooks and Python scripts for offline data ingestion, Qdrant vector store management, and parliamentary voting data processing. Used by data engineers to build or update the vector collections that power the RAG pipeline, independent of the live application's automatic indexing services.

## Key Files
| File | Description |
|------|-------------|
| `generate_db.ipynb` | Notebook for generating the initial Qdrant vector store content from party manifestos |
| `add_additional_data.ipynb` | Notebook for adding supplementary content to existing Qdrant collections |
| `scrape_voting_behavior.ipynb` | Notebook for scraping parliamentary voting records and preparing them for indexing |
| `vector_store_voting_behavior.ipynb` | Notebook for indexing scraped voting records into the `justified_voting_behavior_{env}` Qdrant collection |
| `vector_store_requests.ipynb` | Notebook for testing and inspecting Qdrant search queries |
| `index_candidate_websites.py` | Standalone script to trigger candidate website scraping and indexing (similar to the admin endpoint in `aiohttp_app.py`) |
| `delete_vector_store_data.py` | Script to delete points from Qdrant collections by filter |
| `script_utils.py` | Shared utility functions used across notebooks and scripts in this directory |

## For AI Agents

### Working In This Directory
- Run notebooks with `jupyter notebook` or `jupyter lab` from the repo root; ensure Poetry environment is activated
- Scripts require `ENV`, `API_NAME`, `QDRANT_URL`, and at least one embedding API key in the environment
- These scripts operate directly on Qdrant — verify the target `ENV` before running to avoid modifying production data
- `delete_vector_store_data.py` is destructive; always test with `--dry-run` if supported, or against the dev collection first

### Testing Requirements
No automated tests. Validate by running against the local Qdrant instance and inspecting results:
```bash
# Inspect a collection after indexing
curl -X GET http://localhost:6333/collections/all_parties_dev
```

### Common Patterns
- Collection names follow the env-suffix convention from `src/vector_store_helper.py`: `all_parties_{env}`, `justified_voting_behavior_{env}`, `parliamentary_questions_{env}`, `candidates_websites_{env}`
- Embedding dimension must match `EMBEDDING_DIM` in `src/vector_store_helper.py` (3072 for Google/OpenAI, 768 for Ollama `nomic-embed-text`)
- Notebooks are paired with `.license` files for REUSE compliance

## Dependencies

### Internal
- `src/vector_store_helper.py` — collection names and Qdrant client setup
- `src/services/candidate_website_scraper.py` — used by `index_candidate_websites.py`
- `src/services/candidate_indexer.py` — used by `index_candidate_websites.py`

### External
| Package | Purpose |
|---------|---------|
| `qdrant-client` | Direct Qdrant collection and point operations |
| `langchain-*` | Embeddings and text splitting |
| `jupyter` | Notebook runtime |

<!-- MANUAL: -->
