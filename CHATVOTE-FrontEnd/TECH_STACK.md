# Technical Stack

## Core Application

- **Framework**: Next.js 15 (App Router) with server components and route handlers under `app/`.
- **Language**: TypeScript (tsconfig and `*.ts/tsx` across the codebase).
- **Runtime**: React 19.0 with Next.js build/runtime pipeline.
- **Package manager**: Bun lockfile (`bun.lockb`) present; scripts also support npm/yarn/pnpm.

## UI & Styling

- **Styling system**: Tailwind CSS 3.4 with `@tailwindcss/typography` and `tailwindcss-animate`; global styles in `app/globals.css`.
- **Component primitives**: Radix UI packages (accordion, dialog, select, tooltip, etc.) plus Lucide icons.
- **Motion**: `motion` (Framer Motion v12 API) for animations and `LazyMotion` setup in `app/layout.tsx`.
- **Media & rendering**: Embla carousel; Recharts for data viz; `react-markdown` with `remark-gfm` for rich text; `react-pdf` for PDF rendering.
- **Theming**: `next-themes` based light/dark toggle with CSS variables defined in Tailwind theme.

## State & Data Flow

- **State management**: Zustand stores for chat/session state, wired through React context providers.
- **Forms & hooks**: `usehooks-ts` utilities; Radix form controls; Sonner toasts for UX feedback.

## Data, Auth & Realtime

- **Backend data layer**: Firebase Firestore accessed via both client SDK (`lib/firebase/firebase.ts`) and Admin SDK for server-side operations (`lib/firebase/firebase-admin.ts`).
- **Authentication**: Firebase Auth (email/password, password reset, anonymous auth) with a service worker helper (`components/providers/auth-service-worker-provider.tsx`).
- **Realtime messaging**: `socket.io-client` used by `SocketProvider` to stream chat events from the backend (`NEXT_PUBLIC_API_URL` endpoint).

## Payments

- **Stripe**: Client libraries (`@stripe/stripe-js`, `@stripe/react-stripe-js`) plus server-side Stripe SDK for checkout/payment intents (`lib/server-actions/stripe-create-session.ts`, `lib/stripe/stripe.ts`).

## Hosting, Delivery & Cloud Services

- **Hosting**: Firebase Hosting configured for Next.js framework SSR (`firebase.json`) with backend region `europe-west1`.
- **CDN/Images**: Next Image remote loader allows assets from `chatvote.org` and `dev.chatvote.org` (`next.config.ts`).
- **Analytics**: Vercel Analytics (`@vercel/analytics`) initialized in the root layout.
- **Sitemap/SEO**: `next-sitemap` config plus `app/sitemap.ts` and `app/robots.ts`.

## Tooling & Quality

- **Lint/format**: ESLint (Next.js preset, Tailwind, no-relative-import-paths) and Biome for linting/formatting (`package.json` scripts).
- **Build scripts**: `next dev/build/start`, `next lint`, `biome format/lint`.
- **Type safety**: TypeScript 5.7 with project references; ambient types in `env.d.ts`.
