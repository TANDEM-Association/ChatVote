<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/app

## Purpose

Next.js App Router root. Contains the global layout (fonts, metadata, providers), all page routes, Next.js API route handlers, and server actions. The root layout wraps all pages with `NextIntlClientProvider` and `AppProvider` (auth, tenant, parties, theme). The primary user-facing route is `/chat`.

## Key Files

| File            | Description                                                                                                                                             |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `layout.tsx`    | Root layout: loads fonts (Merriweather/Merriweather Sans), metadata, detects device/theme/locale, wraps with `AppProvider` and `NextIntlClientProvider` |
| `globals.css`   | Global Tailwind CSS v4 styles                                                                                                                           |
| `manifest.json` | PWA web app manifest                                                                                                                                    |
| `robots.ts`     | Next.js robots.txt generation                                                                                                                           |

## Subdirectories

| Directory           | Purpose                                                                       |
| ------------------- | ----------------------------------------------------------------------------- |
| `_actions/`         | Next.js Server Actions (e.g., `i18n/getLocale.ts`)                           |
| `admin/`            | Admin dashboard for data sources and election management                     |
| `api/`              | Next.js API route handlers (see `api/AGENTS.md`)                             |
| `chat/`             | Chat session pages — the main feature (see `chat/AGENTS.md`)                 |
| `commune/`          | Commune (municipality) information and search pages                          |
| `(home)/`           | Landing page                                                                 |
| `dev/`              | Development-only pages (debug, health checks, internal tools)                |
| `donate/`           | Stripe donation flow                                                         |
| `experiment/`       | Experimental features and A/B test pages                                    |
| `guide/`            | User guide page                                                              |
| `legal-notice/`     | Legal notice page                                                            |
| `maintenance/`      | Maintenance mode and status pages                                           |
| `pdf/`              | PDF viewer page (uses pdfjs-dist)                                            |
| `privacy-policy/`   | Privacy policy page                                                          |
| `topics/`           | Topic-based filtering and election topic pages                              |

## For AI Agents

### Working In This Directory

- All layouts and pages are React Server Components by default — add `"use client"` only when needed.
- The root layout fetches `parties`, `tenant`, and `auth` from Firebase Admin on every request. These are passed into `AppProvider` and available via context in client components.
- Locale is determined server-side via `getLocale()` server action and injected via `NextIntlClientProvider`.
- Theme is read from the `x-theme` request header by `getTheme()`.
- `generateMetadata()` in `layout.tsx` produces French-language SEO metadata; update both FR and EN strings when adding pages.

### Testing Requirements

- Page-level tests are in `e2e/integration/`.
- Server actions should be tested via integration tests with the Firebase emulator.

### Common Patterns

- Dynamic segments use bracket notation: `[chatId]` for chat sessions.
- API routes follow the Next.js Route Handler convention: `export async function GET(request: Request)`.
- Server Actions are in `_actions/` and use `"use server"` directive.

## Dependencies

### Internal

- `@lib/firebase/firebase-admin` — server-side Firestore/Auth
- `@lib/firebase/firebase-server` — shared server-side Firebase helpers
- `@lib/theme/getTheme` — theme detection
- `@lib/device` — device detection (mobile/desktop)
- `@components/providers/app-provider` — client-side context root

### External

- `next-intl` — i18n
- `@next/third-parties/google` — Google Analytics

<!-- MANUAL: -->
