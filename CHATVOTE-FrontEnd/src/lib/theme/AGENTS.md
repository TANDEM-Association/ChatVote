<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src/lib/theme

## Purpose
Theme detection and persistence utilities. The app supports `"dark"` and `"light"` themes. Theme is detected server-side from the `x-theme` request header (set by middleware or a service worker) and applied as a `data-theme` attribute on the `<html>` element. Client-side toggling uses `next-themes`.

## Key Files
| File | Description |
|------|-------------|
| `getTheme.ts` | Server-side: reads the `x-theme` header from the request and returns a `Theme` value. Falls back to `"dark"` |
| `setTheme.ts` | Client-side: sets the theme preference (likely via cookie or `next-themes`) |
| `types.ts` | `Theme` type definition: `"dark" \| "light"` |

## For AI Agents

### Working In This Directory
- `getTheme.ts` is used in `src/app/layout.tsx` to set the initial `data-theme` attribute server-side — this prevents flash of unstyled content.
- Tailwind CSS v4 uses CSS custom properties for theming. Theme variants are applied via the `data-theme` attribute on `<html>`.
- Client-side theme toggling is handled by `useTheme` from `@lib/hooks/useTheme.ts` (wraps `next-themes`).
- `DEFAULT_THEME` is `"dark"`.

## Dependencies

### External
- `next-themes` — client-side theme management

<!-- MANUAL: -->
