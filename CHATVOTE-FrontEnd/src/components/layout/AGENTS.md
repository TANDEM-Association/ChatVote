<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/components/layout

## Purpose

Shared page-level layout components: the site header, footer, and a `PageLayout` wrapper. Used by non-chat pages (home, guide, donate, legal). The chat feature has its own layout managed by `src/app/chat/layout.tsx`.

## Key Files

| File              | Description                                                                                     |
| ----------------- | ----------------------------------------------------------------------------------------------- |
| `footer.tsx`      | Site footer: chatvote logo, navigation links (guide, donate, feedback, legal), and theme toggle |
| `header/`         | Site header directory (nav bar with logo and auth controls)                                     |
| `page-layout.tsx` | Wrapper component that composes header + main content area + footer with consistent spacing     |

## For AI Agents

### Working In This Directory

- `footer.tsx` is a Client Component (`"use client"`) because `ThemeModeToggle` and `FeedbackDialog` require client interaction.
- Navigation links in `footer.tsx` must be kept in sync with the actual routes in `src/app/`.
- i18n keys for navigation labels are in the `"navigation"` namespace.
- `PageLayout` is used by non-chat pages. The chat layout is separate and does not include header/footer — the chat UI fills the full viewport.

### Common Patterns

- Add new footer links as `<Link href="...">` elements inside the existing `<section>` in `footer.tsx`.
- Header auth controls rely on `AuthProvider` from `@components/anonymous-auth` being in the provider tree.

## Dependencies

### Internal

- `@components/chat/theme-mode-toggle` — dark/light toggle
- `@components/feedback-dialog` — feedback collection
- `@components/anonymous-auth` — auth state

### External

- `next/image`, `next/link` — Next.js navigation
- `next-intl` — `useTranslations()`
- `lucide-react` — icons

<!-- MANUAL: -->
