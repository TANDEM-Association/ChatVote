<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# scripts

## Purpose

Build-time tooling scripts. The primary script generates TypeScript types from the Python backend's Pydantic models, ensuring the frontend's Socket.IO payload types and DTO interfaces stay in sync with the backend automatically. A watcher script re-runs generation when backend model files change during development.

## Key Files

| File                      | Description                                                                                                                                                                                                                                                                                                                                    |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `generate-types.mjs`      | Main type generation script. Calls `poetry run python scripts/generate_ts_types.py` in the backend directory, receives JSON Schema output, converts it to TypeScript interfaces/type aliases, and writes to `src/lib/generated/backend-types.generated.ts`. Also generates `ServerToClientEvents` and `ClientToServerEvents` socket event maps |
| `watch-backend-types.mjs` | File watcher that runs `generate-types.mjs` automatically when Python model files in `CHATVOTE-BackEnd/src/models/` change. Started by `npm run dev` alongside Turbopack                                                                                                                                                                       |

## For AI Agents

### Working In This Directory

- These are Node.js ESM scripts (`*.mjs`) run directly with `node`.
- `generate-types.mjs` requires the backend Python environment (Poetry + dependencies) to be installed. If Python is unavailable, it falls back to the existing generated file with a warning.
- The generated output is at `src/lib/generated/backend-types.generated.ts`. This file is committed to the repository so the frontend can build without Python available.
- **Never edit `src/lib/generated/backend-types.generated.ts` manually.** It is overwritten on every generation run.
- The conversion pipeline: Pydantic model → `model_json_schema()` → JSON Schema → custom converter in `generate-types.mjs` → TypeScript.
- A `name_map` object in the Python exporter maps Python class names to TypeScript names (e.g., `ChatUserMessageDto` → `ChatUserMessageDto`).

### Running Type Generation

```bash
# From CHATVOTE-FrontEnd/
pnpm run generate:types

# Runs automatically before dev and build via predev/prebuild hooks
pnpm run dev    # starts watcher + Turbopack
pnpm run build  # generates types then builds
```

### Common Patterns

- When a new Pydantic model is added to the backend, run `pnpm run generate:types` and commit the updated `backend-types.generated.ts`.
- When the frontend needs a type from the backend, import from `@lib/generated` via the re-exports in `@lib/socket.types.ts` — never import from `generated/` directly in component code.

## Dependencies

### External

- `node:child_process` — `execSync` to call Python
- `node:fs`, `node:path` — file I/O
- Python + Poetry — backend type exporter (`generate_ts_types.py` in `CHATVOTE-BackEnd/scripts/`)

<!-- MANUAL: -->
