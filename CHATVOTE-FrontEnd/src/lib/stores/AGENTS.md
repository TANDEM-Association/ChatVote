<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/lib/stores

## Purpose

The Zustand chat store — the central state container for the entire chat feature. Manages chat session identity, message history, active party selection, Socket.IO connection state, real-time streaming messages, pro/con perspective state, voting behavior state, and loading/error state. The store is created via `createChatStore()` and scoped per chat layout mount (not a global singleton).

## Key Files

| File                  | Description                                                                                                                                                                                                                       |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `chat-store.ts`       | Store factory: `createChatStore()` assembles all 32+ action handlers using Zustand + Immer + devtools middleware. Defines `defaultState`                                                                                          |
| `chat-store.types.ts` | All TypeScript types for the store: `ChatStoreState`, `ChatStoreActions`, `ChatStore`, `GroupedMessage`, `MessageItem`, `Source`, `VotingBehavior`, `MessageFeedback`, `CurrentStreamingMessages`, `ChatStoreActionHandlerFor<T>` |
| `ai-sdk-features-store.ts` | Zustand store for AI SDK experimental features (feature flags and state) |
| `chat-mode-store.ts` | Store for chat mode state (national vs local scope toggle) |

## Subdirectories

| Directory  | Purpose                                                                      |
| ---------- | ---------------------------------------------------------------------------- |
| `actions/` | 32 individual action handler files, one per action (see `actions/AGENTS.md`) |

## For AI Agents

### Working In This Directory

- `chat-store.ts` only wires up actions — business logic lives in `actions/`. Keep `chat-store.ts` as a thin assembler.
- `ChatStoreState` in `chat-store.types.ts` is the authoritative shape of all store state. Add new state fields here with their TypeScript types before implementing actions.
- The store uses Immer (`immer` middleware): action handlers receive a mutable `draft` — mutate it directly. Do not return new state objects.
- `ChatStoreActionHandlerFor<T>` is the generic type for all action handlers: `(get, set) => (...args) => ReturnType`. Use this type when creating new action files.
- Devtools middleware is included — the store is inspectable in Redux DevTools browser extension.
- `SURVEY_BANNER_MIN_MESSAGE_COUNT = 8` is a store-level constant controlling when the survey banner appears.

### Key State Fields

| Field                      | Type                                    | Purpose                                                    |
| -------------------------- | --------------------------------------- | ---------------------------------------------------------- |
| `messages`                 | `GroupedMessage[]`                      | Persisted chat history (user + assistant turns)            |
| `currentStreamingMessages` | `CurrentStreamingMessages \| undefined` | In-flight streaming state keyed by session ID and party ID |
| `partyIds`                 | `Set<string>`                           | Currently selected party IDs for the session               |
| `socket.io`                | `ChatSocket \| undefined`               | The typed Socket.IO wrapper                                |
| `loading.*`                | various                                 | Granular loading flags for different async operations      |
| `scope`                    | `ChatScope`                             | `"national"` or `"local"`                                  |
| `tenant`                   | `Tenant \| undefined`                   | Active tenant config (multi-tenant support)                |

### Testing Requirements

- Store actions are unit-testable by calling `createChatStore()` directly and dispatching actions.
- Integration behavior is tested via E2E tests in `e2e/integration/`.

### Common Patterns

```typescript
// Reading from store in a component
const messages = useChatStore((state) => state.messages);

// Writing to store (inside an action handler)
set((draft) => {
  draft.messages.push(newMessage); // Immer mutation
});
```

## Dependencies

### Internal

- `actions/` — all action implementations
- `@lib/firebase/firebase.types` — `ChatSession`, `Tenant`
- `@lib/chat-socket` — `ChatSocket` type
- `@lib/socket.types` — `ChatScope`, `LLMSize`, payload types

### External

- `zustand` + `zustand/middleware` — `createStore`, `devtools`
- `zustand/middleware/immer` — `immer`
- `immer` — `WritableDraft`

<!-- MANUAL: -->
