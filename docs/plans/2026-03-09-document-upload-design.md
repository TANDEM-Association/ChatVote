# Document Upload Feature Design

## Access
- Secret URL: `/admin/upload/<SECRET_TOKEN>` — token stored as env var `ADMIN_UPLOAD_SECRET`
- Backend validates token on every request, returns 404 (not 403) if wrong

## Frontend Page (`/admin/upload/[secret]`)
- Drag & drop zone + file picker (PDF, DOCX, TXT)
- Batch upload: drop multiple files at once
- Per-file progress bar: uploading → chunking → embedding → indexing → done
- Live status table for all uploads (current + past in session)
- Auto-assignment display: shows detected party/candidate/collection per file

## Auto-Assignment Logic (backend)
1. Extract text from first few pages
2. LLM classifies: match against known parties and candidates from Firestore
3. Falls back to filename heuristics (e.g. `renaissance-programme.pdf` → Renaissance)
4. If ambiguous, returns suggestions — user picks from dropdown
5. Determines target collection: `all_parties_prod` or `candidates_websites_prod`

## Processing Flow
- **< 5MB**: Immediate — stream progress via SSE (Server-Sent Events)
- **≥ 5MB or batch**: Background task, poll status endpoint
- Pipeline: Upload → Extract text → Auto-assign → Chunk (1000/200) → Embed → Upsert to Qdrant
- Reuses existing `manifesto_indexer` and `candidate_indexer` pipelines

## Backend Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/admin/upload` | POST | Upload file(s), returns job ID(s) |
| `/api/v1/admin/upload-status` | GET | List all jobs with progress |
| `/api/v1/admin/upload-status/{job_id}` | GET | Single job progress (SSE) |

All require `X-Upload-Secret` header matching `ADMIN_UPLOAD_SECRET` env var.

## Tech Stack
- Backend: aiohttp multipart upload + asyncio.create_task for background
- Frontend: Next.js page with EventSource for SSE progress
- Text extraction: pypdf (PDF), python-docx (DOCX), plain read (TXT)
- Embedding/indexing: reuses existing pipeline (no new deps)
