<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/components/auth

## Purpose

Authentication UI components for Firebase Auth flows (email/password, Google, Microsoft, anonymous). Handles login, password reset, user account dialog, and anonymous-to-authenticated upgrade. The `AnonymousUserChatStoreUpdater` component bridges Firebase Auth state into the Zustand chat store.

## Key Files

| File                                    | Description                                                                                                                 |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `anonymous-user-chat-store-updater.tsx` | Render-only component: syncs anonymous Firebase Auth state (`userId`, `isAnonymous`) into `ChatStore` on auth state changes |
| `login-button.tsx`                      | Trigger button to open the login dialog                                                                                     |
| `login-form.tsx`                        | Email/password login form with Google and Microsoft OAuth buttons                                                           |
| `password-reset-form.tsx`               | Password reset request form                                                                                                 |
| `success-auth-form.tsx`                 | Post-authentication success confirmation screen                                                                             |
| `user-avatar.tsx`                       | User avatar display (photo URL or initials fallback)                                                                        |
| `user-dialog.tsx`                       | Full user account dialog: shows profile, logout, and account management                                                     |

## For AI Agents

### Working In This Directory

- All components are Client Components (`"use client"`).
- Firebase Auth is accessed via `auth` from `@lib/firebase/firebase.ts` (client SDK). Never use `firebase-admin` in these components.
- `AnonymousUserChatStoreUpdater` must remain in `chat/layout.tsx` — it relies on `useChatStore()` being available inside `ChatStoreProvider`.
- Auth state is also available via `useAppContext()` from `AppProvider` and the `AuthProvider` from `anonymous-auth.tsx`.
- Anonymous auth is automatically created for unauthenticated users; `isAnonymous: true` in the store reflects this.

### Testing Requirements

- `e2e/integration/authentication.spec.ts` covers login, logout, and anonymous flows.
- Use the Firebase Auth emulator (`localhost:9099`) for E2E tests — set `NEXT_PUBLIC_USE_FIREBASE_EMULATORS=true`.

### Common Patterns

- Auth dialogs use `@components/ui/modal` or `@components/ui/drawer` for the overlay.
- Post-login actions (like saving a pending message) are triggered by listening to auth state changes in `AnonymousUserChatStoreUpdater`.

## Dependencies

### Internal

- `@lib/firebase/firebase.ts` — Firebase Auth client instance
- `@lib/stores/` — `useChatStore()` for auth state sync

### External

- `firebase/auth` — `onAuthStateChanged`, `signInWithPopup`, `signOut`

<!-- MANUAL: -->
