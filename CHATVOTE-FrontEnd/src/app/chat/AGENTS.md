<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src/app/chat

## Purpose
The primary feature area of the app. Contains the chat session layout and page, which initialize the Zustand `ChatStore`, connect to Socket.IO, and render the chat UI. The layout wraps all chat pages with `ChatStoreProvider`, `SocketProvider`, and `SidebarProvider`. The dynamic route `[chatId]/` handles existing chat sessions; the base `/chat` page starts a new session.

## Key Files
| File | Description |
|------|-------------|
| `layout.tsx` | Chat layout: wraps children with `ChatStoreProvider`, `AnonymousUserChatStoreUpdater`, `SocketProvider`, and `SidebarProvider` |
| `page.tsx` | `/chat` landing — new chat entry point |
| `[chatId]/` | Dynamic route for existing chat sessions identified by `chatId` |
| `i18n/` | Chat-specific i18n route segment (locale routing) |

## For AI Agents

### Working In This Directory
- `layout.tsx` is the critical initialization point for chat state and Socket.IO. Changes here affect every chat session.
- `ChatStoreProvider` creates a per-session Zustand store instance (not a global singleton) — this is intentional to support multiple tabs.
- `SocketProvider` registers all Socket.IO event listeners and wires them to store actions. Adding a new backend event requires updating both `socket.types.ts` and `socket-provider.tsx`.
- `AnonymousUserChatStoreUpdater` is a render-only component that syncs Firebase anonymous auth state into the chat store.
- The `[chatId]` segment receives the session ID as a route param; `page.tsx` reads query params (`?municipality_code=`, `?parties=`, `?q=`) for initial state.

### Testing Requirements
- Chat flow E2E tests are in `e2e/integration/` — `streamed-responses.spec.ts`, `chat-input.spec.ts`, `persisted-sessions.spec.ts`.
- The mock Socket.IO server (`e2e/mock/mock-socket-server.ts`) must be running for integration tests.

### Common Patterns
- Session ID is a UUID generated client-side when starting a new chat, then confirmed server-side via the `chat_session_initialized` Socket.IO event.
- Party selection is done before or during the chat; selected party IDs are stored in `ChatStore.partyIds`.
- Municipality code is an optional query parameter enabling local-scope chat with candidate data.

## Dependencies

### Internal
- `@components/providers/chat-store-provider` — Zustand store provider
- `@components/providers/socket-provider` — Socket.IO event bridge
- `@components/auth/anonymous-user-chat-store-updater` — Auth state sync
- `@components/ui/sidebar` — Sidebar state management
- `@components/chat/chat-view` — Main chat UI component

### External
- `socket.io-client` — via `SocketProvider`
- `zustand` — via `ChatStoreProvider`

<!-- MANUAL: -->
