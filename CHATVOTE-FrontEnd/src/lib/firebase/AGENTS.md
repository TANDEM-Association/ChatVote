<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/lib/firebase

## Purpose

Firebase integration layer split into client-side, server-side, and admin-side modules. Handles Firestore CRUD for chat sessions and messages, Firebase Auth for user management, and provides typed domain types. The split prevents server-only code (Admin SDK) from being bundled into client JavaScript.

## Key Files

| File                 | Description                                                                                                                                                                            |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `firebase.ts`        | Client SDK: initializes Firebase app, exports `auth` and `db`. Connects to emulators when `NEXT_PUBLIC_USE_FIREBASE_EMULATORS=true`. All Firestore CRUD for chat sessions and messages |
| `firebase-config.ts` | Firebase project config object built from `NEXT_PUBLIC_FIREBASE_*` env vars                                                                                                            |
| `firebase-server.ts` | Server-side helpers using the client SDK from a server context: `getParties()`, `getAuth()`, `getSystemStatus()`. Imports `server-only`                                                |
| `firebase-admin.ts`  | Firebase Admin SDK: `getTenant()`, privileged server operations. Imports `server-only`                                                                                                 |
| `firebase.types.ts`  | Domain types: `ChatSession`, `Tenant`, `ProposedQuestion`, `SourceDocument`, `LlmSystemStatus`, `DEFAULT_LLM_SIZE`                                                                     |
| `analytics.ts`       | Firebase Analytics: event tracking for chat interactions, errors, newsletter signups, response timing                                                                                    |
| `user-profile.ts`    | User profile helpers for Firebase Auth user data                                                                                                                                         |

## For AI Agents

### Working In This Directory

- `firebase.ts` is the only file safe to import in Client Components. It uses the Firebase client SDK.
- `firebase-server.ts` and `firebase-admin.ts` import `server-only` — importing them in a Client Component causes a build error. This is intentional.
- The Firebase emulator runs on `localhost:8081` (Firestore) and `localhost:9099` (Auth) when `NEXT_PUBLIC_USE_FIREBASE_EMULATORS=true`. All E2E tests use the emulator.
- Firestore collections: `chat_sessions` (root), `chat_sessions/{id}/messages` (subcollection), `users`, `system_status`, `parties`, `tenants`.
- `firebase.ts` exports these Firestore functions: `createChatSession`, `getChatSession`, `getChatSessionMessages`, `getUsersChatHistory`, `listenToHistory`, `listenToSystemStatus`, `addMessageToGroupedMessageOfChatSession`, `addProConPerspectiveToMessage`, `addVotingBehaviorToMessage`, `updateMessageFeedback`, `getUser`, `updateUserData`.

### Key Firestore Schema

| Collection                    | Document Fields                                                                               |
| ----------------------------- | --------------------------------------------------------------------------------------------- |
| `chat_sessions`               | `user_id`, `party_ids`, `title`, `is_public`, `created_at`, `updated_at`, `tenant_id?`        |
| `chat_sessions/{id}/messages` | `id`, `messages: MessageItem[]`, `role`, `quick_replies`, `created_at`                        |
| `users`                       | `survey_status`, `newsletter_allowed`, `clicked_away_login_reminder`, `keep_up_to_date_email` |
| `system_status/llm_status`    | `is_at_rate_limit`                                                                            |

### Testing Requirements

- All tests involving Firestore use the emulator. Set `NEXT_PUBLIC_USE_FIREBASE_EMULATORS=true`.
- `e2e/global-setup.ts` and `e2e/global-teardown.ts` handle emulator lifecycle.
- `e2e/integration/reset-emulator.setup.ts` resets Firestore data between test suites.

## Dependencies

### External

- `firebase` 11.x — client SDK (`firebase/app`, `firebase/auth`, `firebase/firestore`)
- `firebase-admin` 13.x — server-only Admin SDK
- `server-only` — build-time guard for server modules

<!-- MANUAL: -->
