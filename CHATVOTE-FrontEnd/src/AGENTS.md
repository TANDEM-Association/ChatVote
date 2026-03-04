<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src

## Purpose
Root source directory for the ChatVote frontend. Contains the Next.js App Router pages (`app/`), all React components (`components/`), shared library code (`lib/`), and internationalization resources (`i18n/`). Also holds `config/` for environment-based runtime configuration.

## Key Files
| File | Description |
|------|-------------|
| `config/` | Runtime config object built from env vars (API URLs, feature flags, GA ID) |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `app/` | Next.js App Router: layouts, pages, API routes (see `app/AGENTS.md`) |
| `components/` | All React components organized by feature area (see `components/AGENTS.md`) |
| `lib/` | Shared utilities, stores, hooks, Firebase client, Stripe, theme, types (see `lib/AGENTS.md`) |
| `i18n/` | next-intl configuration and FR/EN message catalogs (see `i18n/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Path aliases are configured in `tsconfig.json`: `@lib/` → `src/lib/`, `@components/` → `src/components/`, `@i18n/` → `src/i18n/`, `@config` → `src/config/`, `@actions/` → `src/app/_actions/`.
- Never import from `src/lib/generated/` directly in new code — use the re-exports in `src/lib/socket.types.ts`.
- Server-only code (Firebase Admin, Stripe server) must not be imported in client components.

### Common Patterns
- Server Components: async functions that fetch data server-side, no `"use client"` directive.
- Client Components: must declare `"use client"` at top; use Zustand store via `useChatStore()` hook.
- Shared domain types live in `lib/stores/chat-store.types.ts` and `lib/socket.types.ts`.

<!-- MANUAL: -->
