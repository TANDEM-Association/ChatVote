<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# data

## Purpose
Offline data pipeline work for building and maintaining ChatVote's vector store content. Contains Jupyter notebooks and Python scripts used to scrape, process, and index parliamentary voting data, vector store requests, and other supplementary content into Qdrant. These are one-off or periodic data engineering tools, not part of the live application runtime.

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `scripts/` | Jupyter notebooks and Python scripts for data ingestion and Qdrant management (see `scripts/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- This directory contains data engineering artefacts only; do not import from here in application code
- Notebooks are exploratory and may contain credentials or API calls in cells; review before running in a shared environment
- Changes to vector store schema (collection names, embedding dimensions, metadata fields) must be reflected in both these scripts and `src/vector_store_helper.py`

### Testing Requirements
Data scripts are validated by running them against live or local Qdrant and Firestore instances. No automated test suite exists for this directory.

### Common Patterns
- All scripts use the same env-suffix collection naming convention as the main application (`all_parties_dev`, `all_parties_prod`, etc.)
- Notebooks are paired with `.license` files (REUSE compliance)

<!-- MANUAL: -->
