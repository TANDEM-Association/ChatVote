<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/components/election-flow

## Purpose

The home page entry flow that guides users to start a chat session. Users choose between national (all parties) or local (municipality-specific candidates) scope. The flow is a 3-step progressive disclosure: scope selection → municipality search → candidate list → start chat. Navigates to `/chat` or `/chat?municipality_code=<code>` on completion.

## Key Files

| File                      | Description                                                                                                                                  |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `home-election-flow.tsx`  | Main 3-step flow component: scope select (Radix UI), municipality search, candidate list, and "Start Chat" button with animated border trail |
| `municipality-search.tsx` | Autocomplete search for French municipalities by name, calls `@lib/election/election-firebase-server`                                        |
| `candidate-list.tsx`      | Renders list of candidates for a selected municipality with photo, name, party, and website                                                  |
| `candidate-card.tsx`      | Individual candidate card component                                                                                                          |
| `index.ts`                | Barrel export for the directory                                                                                                              |

## For AI Agents

### Working In This Directory

- All components are Client Components (`"use client"`).
- `home-election-flow.tsx` uses `useIsMounted()` to return a skeleton during SSR — this avoids Radix UI Select hydration mismatches.
- The flow tracks analytics via `@vercel/analytics/react` `track()` on chat start.
- Municipality data comes from `@lib/election/election-firebase-server` (a server action or direct Firestore call from the client).
- The `ChatButton` internal component uses `BorderTrail` from `@components/ui/border-trail` for the animated hover effect.
- Scope types: `"national"` (parties only) | `"local"` (municipality + candidates). Local scope sets `?municipality_code=` query param when navigating to chat.

### Common Patterns

- Step state is managed with `useState<FlowStep>` — `"scope"` | `"municipality"` | `"parties"`.
- Async data loading (parties, candidates) uses `try/catch` with `sonner` toast on error.
- i18n keys are under the `"electionFlow"` namespace.

## Dependencies

### Internal

- `@lib/election/election-firebase-server` — municipality and candidate data
- `@lib/election/election.types` — `Municipality`, `Candidate` types
- `@lib/firebase/firebase-server` — `getParties()`
- `@lib/hooks/use-is-mounted` — SSR hydration guard
- `@components/ui/border-trail`, `button`, `select`, `skeleton`

### External

- `next/navigation` — `useRouter()`
- `next-intl` — `useTranslations()`
- `@vercel/analytics/react` — `track()`
- `lucide-react` — icons
- `sonner` — error toasts

<!-- MANUAL: -->
