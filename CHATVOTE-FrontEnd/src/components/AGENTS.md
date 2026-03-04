<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src/components

## Purpose
All React components for the ChatVote frontend, organized by feature area. The largest area is `chat/` with 63 components covering the full real-time chat UI. Other areas handle authentication, UI primitives, context providers, the election entry flow, and page layout.

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `chat/` | All chat UI components: messages, input, streaming, sidebar, voting behavior, pro/con (see `chat/AGENTS.md`) |
| `auth/` | Authentication components: login, password reset, user dialog, anonymous auth sync (see `auth/AGENTS.md`) |
| `ui/` | shadcn/ui primitives and custom base components (see `ui/AGENTS.md`) |
| `providers/` | React context providers: app, auth, chat store, socket, parties, tenant (see `providers/AGENTS.md`) |
| `election-flow/` | Home page election entry flow: scope selection, municipality search, candidate list (see `election-flow/AGENTS.md`) |
| `layout/` | Shared layout components: header, footer, page layout wrapper (see `layout/AGENTS.md`) |
| `guide/` | User guide components |
| `icons/` | SVG icon components |
| `legal/` | Legal disclaimer components (AI disclaimer) |
| `i18n/` | i18n-related UI components |

## Key Files
| File | Description |
|------|-------------|
| `anonymous-auth.tsx` | Anonymous Firebase Auth provider and hook |
| `donation-dialog.tsx` | Stripe donation dialog |
| `donation-form.tsx` | Stripe donation form |
| `donate-result-content.tsx` | Post-donation confirmation UI |
| `feedback-dialog.tsx` | User feedback collection dialog |
| `guide-dialog.tsx` | In-app guide dialog |
| `guide.tsx` | Guide content component |
| `loading-spinner.tsx` | Shared loading spinner |
| `markdown.tsx` | Shared markdown renderer (react-markdown + remark-gfm) |
| `party-card.tsx` | Single party card with logo and name |
| `party-cards.tsx` | Grid of party cards |
| `pdf-view.tsx` | PDF viewer using pdfjs-dist |
| `embed-open-website-button.tsx` | Button for embed widget to open full site |
| `visually-hidden.tsx` | Accessibility hidden text wrapper |

## For AI Agents

### Working In This Directory
- Add new components to the most specific subdirectory. Cross-feature components go in the root of `components/`.
- All components using hooks, event handlers, or browser APIs must be Client Components (`"use client"`).
- Use `cn()` from `@lib/utils` for conditional class merging — never string concatenation.
- Use `useTranslations()` from `next-intl` for all user-visible text. Add keys to both `src/i18n/messages/fr.json` and `src/i18n/messages/en.json`.
- Import shadcn/ui primitives from `@components/ui/`, not from `@radix-ui` directly.

### Common Patterns
- Props interfaces are co-located with their component (`type Props = { ... }`).
- Default exports for page-level components; named exports for utility/primitive components.
- Lucide React for icons — import specific icons, not the entire library.

## Dependencies

### Internal
- `@lib/stores/` — Zustand chat store
- `@lib/firebase/` — Firebase auth and Firestore
- `@lib/hooks/` — Shared custom hooks

### External
- `@radix-ui/*` — Accessible primitives
- `lucide-react` — Icons
- `motion` — Animations
- `next-intl` — Translations

<!-- MANUAL: -->
