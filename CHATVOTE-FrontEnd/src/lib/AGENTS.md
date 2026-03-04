<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src/lib

## Purpose
Shared library code for the frontend: the Zustand chat store, Socket.IO type definitions, Firebase client/admin wrappers, Stripe server client, custom React hooks, theme utilities, election data helpers, generated backend types, and general utilities. This is the primary layer between the React component tree and external services.

## Key Files
| File | Description |
|------|-------------|
| `chat-socket.ts` | `ChatSocket` class — typed wrapper around socket.io-client. Exposes `on()`, `off()`, and named emit methods (`initializeChatSession`, `addUserMessage`, `generateProConPerspective`, `generateVotingBehaviorSummary`, etc.) |
| `socket.types.ts` | All Socket.IO payload types. Re-exports generated DTO types from `generated/` and defines frontend-adapted types with explanatory comments linking to backend DTOs |
| `constants.ts` | Shared constants (e.g., `TENANT_ID_HEADER`, other app-wide constants) |
| `utils.ts` | Utility functions: `cn()` (class merging), `generateUuid()`, `firestoreTimestampToDate()`, etc. |
| `url.ts` | `getAppUrl()` / `getAppUrlSync()` — resolves `NEXT_PUBLIC_APP_URL` |
| `device.ts` | `detectDevice()` — parses User-Agent header to determine `"mobile"` or `"desktop"` |
| `party-details.ts` | `PartyDetails` type and helpers for party data shape |
| `scroll-utils.ts` | Scroll position utilities for the chat messages view |
| `scroll-constants.ts` | Constants for scroll behavior thresholds |
| `cache-tags.ts` | Next.js cache tag constants for `revalidateTag()` |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `stores/` | Zustand chat store: state types, store factory, and 32 action handlers (see `stores/AGENTS.md`) |
| `hooks/` | Custom React hooks: `useIsMounted`, `useCarouselCurrentIndex`, `useLockScroll`, `useChatParam` (see `hooks/AGENTS.md`) |
| `firebase/` | Firebase client SDK, Admin SDK, server helpers, and Firestore CRUD operations (see `firebase/AGENTS.md`) |
| `stripe/` | Stripe server client and helpers for donation flow (see `stripe/AGENTS.md`) |
| `theme/` | Theme detection and setting utilities (see `theme/AGENTS.md`) |
| `election/` | Election-specific data: municipality search, candidate queries, election types |
| `generated/` | Auto-generated TypeScript types from backend Pydantic models — DO NOT EDIT MANUALLY |
| `server-actions/` | Shared server action utilities |
| `shared/` | Shared domain helpers used across lib |
| `types/` | Shared TypeScript type definitions (e.g., `auth.ts` for `User` type) |

## For AI Agents

### Working In This Directory
- `socket.types.ts` is the single source of truth for Socket.IO payload shapes on the frontend. When the backend changes a DTO, run `pnpm run generate:types` to regenerate `generated/backend-types.generated.ts`, then update `socket.types.ts` if the frontend-adapted types need changes.
- Never edit files in `generated/` — they are overwritten by `scripts/generate-types.mjs`.
- `chat-socket.ts` only exposes typed public methods. The raw `socket.io-client` instance is managed by `SocketProvider`. `chat-socket.ts` imports `socket` from `socket-provider.tsx`.
- Server-only modules (`firebase-admin.ts`, `firebase-server.ts`, `stripe.ts`) must not be imported in client components. They import `server-only` as a guard.
- Use `cn()` from `utils.ts` everywhere class names are merged.

### Common Patterns
```typescript
// Type-safe socket emit (via ChatSocket)
chatSocket.addUserMessage({ session_id, user_message, party_ids, user_is_logged_in });

// Class merging
import { cn } from "@lib/utils";
className={cn("base-class", condition && "conditional-class", props.className)}
```

## Dependencies

### External
- `socket.io-client` — real-time transport
- `firebase` — client SDK
- `firebase-admin` — server SDK
- `stripe` — payment processing
- `zustand` — state management
- `immer` — immutable state updates

<!-- MANUAL: -->
