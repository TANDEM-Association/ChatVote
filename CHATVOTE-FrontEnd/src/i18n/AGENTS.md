<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src/i18n

## Purpose
Internationalization configuration and message catalogs for next-intl. The app supports French (`fr`, default) and English (`en`). Locale detection runs server-side. All user-visible strings must be externalized here — never hardcode French or English text in components.

## Key Files
| File | Description |
|------|-------------|
| `config.ts` | Defines `locales = ["en", "fr"] as const`, `Locale` type, and `defaultLocale = "fr"` |
| `request.ts` | next-intl request configuration: locale detection and message loading per request |
| `messages/` | JSON message catalogs, one file per locale (`fr.json`, `en.json`) |

## For AI Agents

### Working In This Directory
- `config.ts` is the single source of truth for supported locales. Adding a new locale requires: (1) adding it to `locales` array, (2) creating a new `messages/<locale>.json`, (3) updating `request.ts` if needed.
- Message files are plain JSON with nested namespace keys. Namespaces include: `"navigation"`, `"common"`, `"electionFlow"`, `"chat"`, `"auth"`, etc.
- In Client Components: `const t = useTranslations("namespace")` then `t("key")`.
- In Server Components: `const t = await getTranslations("namespace")` then `t("key")`.
- Message keys must exist in both `fr.json` and `en.json` — missing keys cause runtime warnings.
- Locale is determined server-side by `src/app/_actions/i18n/getLocale.ts` and injected via `NextIntlClientProvider` in `layout.tsx`.

### Common Patterns
```typescript
// Client Component
import { useTranslations } from "next-intl";
const t = useTranslations("electionFlow");
return <h2>{t("dialogueWith")}</h2>;

// Server Component
import { getTranslations } from "next-intl/server";
const t = await getTranslations("chat");
return <title>{t("pageTitle")}</title>;
```

### Testing Requirements
- i18n is exercised via E2E tests: `e2e/integration/theme-and-language.spec.ts`.
- Both locales should be tested for any user-visible string changes.

## Dependencies

### External
- `next-intl` 4.8.1 — `useTranslations`, `getTranslations`, `NextIntlClientProvider`, `getMessages`

<!-- MANUAL: -->
