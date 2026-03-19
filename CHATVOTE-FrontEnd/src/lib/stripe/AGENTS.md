<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/lib/stripe

## Purpose

Server-side Stripe integration for the donation flow. Provides a singleton Stripe client, configuration constants, and helper functions for creating Stripe Checkout sessions. All code here is server-only — never imported in Client Components.

## Key Files

| File                | Description                                                                                                                               |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `stripe.ts`         | Singleton Stripe client factory: `getStripe()` — lazily initializes `Stripe` with `STRIPE_SECRET_KEY` and app info. Imports `server-only` |
| `stripe-config.ts`  | Stripe configuration constants (price IDs, donation amounts, product config)                                                              |
| `stripe-helpers.ts` | Helper functions for creating Checkout sessions and handling webhook events                                                               |

## For AI Agents

### Working In This Directory

- All files import `server-only` — these must never be used in Client Components or `"use client"` files.
- The `getStripe()` function is a lazy singleton — it creates the Stripe instance once and reuses it. Never call `new Stripe()` directly elsewhere.
- Stripe secret key comes from `STRIPE_SECRET_KEY` env var (server-only). The publishable key comes from `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` (client-safe).
- Donation flow: Client Component (`donation-form.tsx`) → Server Action or API route → `getStripe()` → Stripe Checkout Session → redirect to Stripe hosted page → return to `/donate?result=...`.

### Testing Requirements

- Stripe integration is tested manually or with Stripe test mode keys. Use `STRIPE_SECRET_KEY=sk_test_...` in development.
- Webhook testing requires the Stripe CLI: `stripe listen --forward-to localhost:3000/api/stripe/webhook`.

## Dependencies

### External

- `stripe` 17.x — Stripe Node.js SDK
- `server-only` — build-time server guard
- `@lib/url` — `getAppUrlSync()` for success/cancel URLs

<!-- MANUAL: -->
