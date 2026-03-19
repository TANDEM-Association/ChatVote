<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# docs

## Purpose
Technical reference documentation for the ChatVote backend. Contains code-derived architecture snapshots that describe the confirmed technical stack, runtime boundaries, LLM provider configuration, RAG pipeline design, Firebase/Qdrant infrastructure, and operational constraints.

## Key Files
| File | Description |
|------|-------------|
| `technical-stack.md` | Comprehensive code-derived snapshot of the technical stack: languages, frameworks, LLM providers, RAG configuration, Firebase/Qdrant setup, environment variables, quality gates, and operational notes |

## For AI Agents

### Working In This Directory
- `technical-stack.md` is a **read reference** for agents that need to understand the overall system without reading all source files
- Keep `technical-stack.md` up to date when making changes to: LLM providers in `src/llms.py`, collection names in `src/vector_store_helper.py`, environment variables in `.env.example`, or Firebase configuration in `firebase/firebase.json`
- Do not add runnable code or scripts to this directory; it is documentation only

### Testing Requirements
No automated tests for documentation. Validate accuracy by cross-referencing against the actual source files listed in `technical-stack.md`.

### Common Patterns
- Document only what is confirmed by code or config — do not speculate about deployment targets or infrastructure not evidenced in the repository
- Use code-derived language: "Confirmed by `src/llms.py`" rather than "The system uses Gemini"

<!-- MANUAL: -->
