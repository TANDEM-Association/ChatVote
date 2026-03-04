<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# CHATVOTE-FrontEnd

## Purpose
Next.js 16 frontend for ChatVote, an AI-powered political information chatbot for French elections. Citizens ask questions to multiple parties simultaneously and receive source-backed streaming answers via Socket.IO. The app is built with React 19, TypeScript, Zustand, Tailwind CSS v4, and shadcn/ui components. It supports FR/EN internationalization, Firebase Auth, Stripe donations, and Playwright E2E tests.

## Key Files
| File | Description |
|------|-------------|
| `next.config.ts` | Next.js configuration (Turbopack, bundle analyzer) |
| `package.json` | Dependencies: Next 16, React 19, Zustand 5, socket.io-client, Firebase, Stripe |
| `tsconfig.json` | TypeScript config with path aliases (`@lib/*`, `@components/*`, `@i18n/*`, etc.) |
| `playwright.config.ts` | Playwright E2E config for integration tests |
| `playwright.integration.config.ts` | Playwright config for integration suite with mock Socket.IO server |
| `eslint.config.mjs` | ESLint with TypeScript, import-sort, tailwind, prettier plugins |
| `postcss.config.mjs` | PostCSS with Tailwind CSS v4 |
| `components.json` | shadcn/ui configuration |
| `proxy.ts` | Development proxy configuration |
| `TECH_STACK.md` | Technology stack overview |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/` | All application source code (see `src/AGENTS.md`) |
| `e2e/` | Playwright E2E tests and mock Socket.IO server (see `e2e/AGENTS.md`) |
| `scripts/` | Build-time tooling: type generation from backend Pydantic models (see `scripts/AGENTS.md`) |
| `public/` | Static assets: images, icons, PWA manifest, service worker, PDF worker (see `public/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- All source edits go under `src/`. Never edit generated files in `src/lib/generated/`.
- Type aliases are defined in `tsconfig.json`: use `@lib/`, `@components/`, `@i18n/`, `@config`, `@actions/` in imports.
- Run `pnpm run generate:types` before type-checking to regenerate backend DTO types. This requires the backend Python environment.
- The app uses Next.js App Router. All pages are under `src/app/`.
- Fonts: Merriweather and Merriweather Sans (Google Fonts). Theme: dark by default, set via `x-theme` request header.

### Testing Requirements
```bash
pnpm run lint          # ESLint check
pnpm run format:check  # Prettier check
pnpm run type:check    # TypeScript strict + generate types
npx playwright test --config playwright.integration.config.ts  # E2E tests
```

### Common Patterns
- `"use client"` directive required for any component using hooks or browser APIs.
- Server Components fetch data from Firebase Admin SDK directly; Client Components use the client SDK or Socket.IO.
- Tailwind CSS v4: class-based, no `tailwind.config.js`. Use `cn()` from `@lib/utils` to merge classes.
- All user-visible strings must use `useTranslations()` from next-intl for i18n.

## Dependencies

### Internal
- Depends on `CHATVOTE-BackEnd` for type generation (`scripts/generate-types.mjs` calls Python)
- Socket.IO backend at `NEXT_PUBLIC_API_URL`

### External
- `next` 16.1.4, `react` 19.2.3
- `zustand` 5.0.2 with `immer` middleware
- `socket.io-client` 4.8.1
- `firebase` 11.0.2 + `firebase-admin` 13.0.2
- `stripe` 17.5.0
- `next-intl` 4.8.1
- `tailwindcss` 4.x, `@radix-ui/*`, `lucide-react`
- `embla-carousel-react`, `react-window`, `recharts`, `motion`
- `@playwright/test` for E2E

<!-- MANUAL: -->
