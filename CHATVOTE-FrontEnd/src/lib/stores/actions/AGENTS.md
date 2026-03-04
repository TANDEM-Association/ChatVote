<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src/lib/stores/actions

## Purpose
32 individual Zustand action handler files, one per action. Each file exports a single factory function matching the `ChatStoreActionHandlerFor<T>` signature: it receives `(get, set)` and returns the action function. This modular structure keeps each action isolated, testable, and easy to locate.

## Key Files
| File | Description |
|------|-------------|
| `initialize-chat-session.ts` | Emits `chat_session_init` via Socket.IO to start a backend session |
| `initialized-chat-session.ts` | Handles `chat_session_initialized` confirmation from server |
| `chat-add-user-message.ts` | Adds a user message to store state and emits `chat_answer_request` |
| `hydrate-chat-session.ts` | Populates store from server-fetched session data (used on session restore) |
| `load-chat-session.ts` | Async: fetches session + messages from Firestore and hydrates store |
| `new-chat.ts` | Resets store to default state for a new chat session |
| `set-chat-id.ts` | Sets the active chat session ID |
| `set-input.ts` | Updates the text input field value |
| `set-party-ids.ts` | Updates the selected party IDs set |
| `set-pre-selected-parties.ts` | Sets pre-selected parties (from URL params or election flow) |
| `select-responding-parties.ts` | Handles `responding_parties_selected` event — records which parties will respond |
| `streaming-message-sources-ready.ts` | Handles `sources_ready` event — attaches sources to a streaming message |
| `merge-streaming-chunk-payload-for-message.ts` | Handles `party_response_chunk_ready` — appends text chunk to streaming message |
| `complete-streaming-message.ts` | Handles `party_response_complete` — finalizes a streaming message |
| `update-quick-replies-and-title-for-current-streaming-message.ts` | Handles `quick_replies_and_title_ready` |
| `cancel-streaming-messages.ts` | Cancels in-flight streaming and clears pending timeout handlers |
| `start-timeout-for-streaming-messages.ts` | Sets a timeout to cancel streaming if no chunks arrive |
| `reset-streaming-message.ts` | Handles `stream_reset` — clears a party's streaming state on backend error |
| `generate-pro-con-perspective.ts` | Emits pro/con request and sets loading state |
| `complete-pro-con-perspective.ts` | Handles `pro_con_perspective_complete` — attaches result to message |
| `generate-candidate-pro-con-perspective.ts` | Emits candidate pro/con request |
| `complete-candidate-pro-con-perspective.ts` | Handles `candidate_pro_con_perspective_complete` |
| `generate-voting-behavior-summary.ts` | Emits voting behavior request and sets loading state |
| `add-voting-behavior-result.ts` | Handles `voting_behavior_result` — accumulates individual vote records |
| `add-voting-behavior-summary-chunk.ts` | Handles `voting_behavior_summary_chunk` — streams summary text |
| `complete-voting-behavior.ts` | Handles `voting_behavior_complete` — finalizes voting behavior state |
| `set-socket.ts` | Stores the `ChatSocket` instance reference in state |
| `set-socket-connected.ts` | Updates `socket.connected` flag |
| `set-socket-connecting.ts` | Updates `socket.isConnecting` flag |
| `set-socket-error.ts` | Stores socket error message |
| `set-chat-session-is-public.ts` | Toggles session public/private visibility in Firestore |
| `set-message-feedback.ts` | Persists like/dislike feedback to Firestore and updates local state |

## For AI Agents

### Working In This Directory
- Every action file exports exactly one function using this signature:
```typescript
import { type ChatStoreActionHandlerFor } from "../chat-store.types";

export const myAction: ChatStoreActionHandlerFor<"myAction"> = (get, set) => async (arg1, arg2) => {
  set((draft) => {
    // mutate draft directly (Immer)
  });
};
```
- After creating a new action file: (1) add the action type to `ChatStoreActions` in `chat-store.types.ts`, (2) import and wire it in `chat-store.ts`.
- Use `get()` to read current state inside an action. Use `set((draft) => { ... })` for Immer mutations.
- Actions that emit Socket.IO events call `get().socket.io?.methodName(payload)` — always guard with `?.` since the socket may not be connected yet.
- Async actions that call Firestore use `await` — they return `Promise<void>`.

### Common Patterns
```typescript
// Reading state in an action
const { chatId, partyIds } = get();

// Mutating state (Immer)
set((draft) => {
  draft.loading.newMessage = true;
});

// Emitting a socket event
get().socket.io?.addUserMessage({ session_id: chatId, ... });
```

### Testing Requirements
- Each action can be unit-tested by creating a store with `createChatStore()`, dispatching the action, and asserting on `store.getState()`.

## Dependencies

### Internal
- `../chat-store.types` — `ChatStoreActionHandlerFor<T>`, all state types
- `@lib/firebase/firebase.ts` — Firestore writes (feedback, session updates)
- `@lib/socket.types` — payload types for socket emissions

<!-- MANUAL: -->
