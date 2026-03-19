<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/components/providers

## Purpose

React context providers that establish the application's global and feature-scoped runtime environment. Providers are layered in the layout hierarchy: `AppProvider` at the root, `ChatStoreProvider` and `SocketProvider` at the chat layout level. Each provider has a single, well-defined responsibility.

## Key Files

| File                               | Description                                                                                                                                                                                        |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app-provider.tsx`                 | Root provider: composes `AuthProvider`, `TenantProvider`, `PartiesProvider`, `LazyMotion`, `TooltipProvider`, `Toaster`, and Vercel Analytics. Exposes `useAppContext()` for `device` and `locale` |
| `socket-provider.tsx`              | Manages the Socket.IO connection lifecycle. Creates a locale-aware socket, registers all server→client event handlers, and wires them to `ChatStore` actions. Exports the `socket` instance        |
| `chat-store-provider.tsx`          | Creates a scoped Zustand `ChatStore` instance per chat layout mount. Exposes `useChatStore()` hook                                                                                                 |
| `auth-service-worker-provider.tsx` | Registers the Firebase Auth service worker for session cookie management                                                                                                                           |
| `chat-voting-details-provider.tsx` | Provides context for the voting details panel (selected vote, slide index)                                                                                                                         |
| `parties-provider.tsx`             | Makes the list of `PartyDetails` available via context without prop drilling                                                                                                                       |
| `tenant-provider.tsx`              | Makes the active `Tenant` configuration (LLM size, branding) available via context                                                                                                                 |

## For AI Agents

### Working In This Directory

- All providers are Client Components (`"use client"`).
- Provider order in `app-provider.tsx` matters: `AuthProvider` must wrap `TenantProvider` which must wrap `PartiesProvider`.
- `socket-provider.tsx` is the single place where Socket.IO events are subscribed. Adding a new server→client event requires: (1) adding the type to `socket.types.ts`, (2) adding the handler function in `socket-provider.tsx`, (3) adding the corresponding store action.
- `chat-store-provider.tsx` uses `createChatStore()` from `@lib/stores/chat-store` — one store instance per `ChatStoreProvider` mount, not a global singleton.
- The `socket` export from `socket-provider.tsx` is a module-level variable. It is reassigned when the locale changes (to reconnect with the correct `Accept-Language` header).

### Common Patterns

```typescript
// Consuming a provider context
import { useAppContext } from "@components/providers/app-provider";
const { device, locale } = useAppContext();

// Consuming the chat store
import { useChatStore } from "@components/providers/chat-store-provider";
const messages = useChatStore((state) => state.messages);
```

### Testing Requirements

- `SocketProvider` behavior is tested indirectly via `e2e/integration/streamed-responses.spec.ts`.
- Provider context errors (missing provider) surface as thrown errors — always render components inside the correct provider tree in tests.

## Dependencies

### Internal

- `@lib/stores/chat-store` — `createChatStore()`
- `@lib/chat-socket` — `ChatSocket` class
- `@lib/firebase/firebase.ts` — Firebase Auth client
- `@lib/socket.types` — all Socket.IO payload types

### External

- `socket.io-client` — `io()`, `Socket`
- `zustand` — store creation
- `motion/react` — `LazyMotion`

<!-- MANUAL: -->
