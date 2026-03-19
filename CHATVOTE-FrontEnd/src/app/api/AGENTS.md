<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/app/api

## Purpose

Next.js API Route Handlers for server-side data fetching, OG image generation, PDF proxying, and Stripe webhook processing. All routes run as Edge or Node.js server functions. Client-side code never calls these directly for real-time features — that goes through Socket.IO — but these routes handle REST-style requests and media serving.

## Key Files

| File               | Description                                                      |
| ------------------ | ---------------------------------------------------------------- |
| `parties/route.ts` | `GET /api/parties` — returns list of party details from Firebase |
| `ai-chat/`         | AI chat completion and streaming routes                          |
| `candidate-lists/` | Candidate list generation and search routes                      |
| `candidates/`      | Candidate data and profile routes                                |
| `commune/`         | Commune (municipality) lookup and search routes                  |
| `coverage/`        | Coverage analysis and reporting routes                           |
| `electoral-lists/` | Electoral list data routes                                       |
| `embed/`           | Embed widget API routes                                          |
| `experiment/`      | A/B testing and experimental feature routes                      |
| `municipalities/`  | Municipality search/lookup routes                                |
| `og/`              | Open Graph image generation routes                               |
| `parties/`         | Party data routes                                                |
| `pdf-proxy/`       | Proxies PDF files from Firebase Storage to avoid CORS            |
| `quick/`           | Quick reply suggestion routes                                    |
| `revalidate/`      | On-demand ISR cache revalidation                                 |
| `[chatId]/`        | Per-chat-session API routes                                      |

## For AI Agents

### Working In This Directory

- All files must export named HTTP method functions (`GET`, `POST`, `PUT`, `DELETE`).
- Use `NextResponse.json()` to return JSON responses.
- Server-only imports (`firebase-admin`, `stripe`) are safe here — these never run on the client.
- Never import Socket.IO here; real-time communication is handled by the Python backend directly.
- For OG image routes, use `@vercel/og` or Next.js `ImageResponse`.

### Testing Requirements

- Test API routes by hitting them with `fetch()` in Playwright E2E tests or integration tests.
- PDF proxy and party routes should be tested against the Firebase emulator.

### Common Patterns

```typescript
// Standard API route pattern
import { NextResponse } from "next/server";
import { getParties } from "@lib/firebase/firebase-server";

export async function GET() {
  const data = await getParties();
  return NextResponse.json(data);
}
```

## Dependencies

### Internal

- `@lib/firebase/firebase-server` — Firestore data access
- `@lib/firebase/firebase-admin` — Admin SDK for privileged operations
- `@lib/stripe/stripe` — Stripe server client (for payment routes)

### External

- `next` Route Handlers
- `firebase-admin`
- `stripe`

<!-- MANUAL: -->
