<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# src/i18n

## Purpose
Backend internationalisation subsystem. Provides translated strings for LLM prompt text, error messages, and any user-facing content generated server-side. Supports French (`fr`, default) and English (`en`). Translations are loaded from JSON locale files with in-memory caching and dot-notation key lookup.

## Key Files
| File | Description |
|------|-------------|
| `translator.py` | Core translation utilities: `get_text(key, locale, **kwargs)` with dot-notation nesting, format interpolation, fallback chain to French, and in-memory cache; `normalize_locale()` handles `"en-US"` / `"en_US"` variants |
| `locales/fr.json` | French translation strings (default locale) |
| `locales/en.json` | English translation strings |

## For AI Agents

### Working In This Directory
- Add new string keys to both `fr.json` and `en.json` simultaneously; `get_text()` falls back to French if a key is missing in English, but logs a warning
- Use dot notation for nested keys: `get_text("errors.rate_limit", locale)` maps to `{"errors": {"rate_limit": "..."}}` in the JSON
- Locale strings from Socket.IO sessions come in as `"fr"` or `"en"` (validated by `InitChatSessionDto.locale`); use `normalize_locale()` when receiving locale from external input
- Call `clear_cache()` in tests that modify locale files at runtime to avoid stale cached values
- The `locale` field flows through `GroupChatSession` → prompt selection (`prompts.py` vs `prompts_en.py`) and i18n string lookup; keep these two mechanisms consistent

### Testing Requirements
```bash
# Translation utilities can be tested in isolation
poetry run python -c "from src.i18n.translator import get_text; print(get_text('welcome', 'en'))"
```

### Common Patterns
- Default locale is `"fr"` (`DEFAULT_LOCALE` constant); always provide a French string before adding English
- Format arguments are passed as `**kwargs` and applied with `str.format(**kwargs)` — use named placeholders in JSON strings: `"Bonjour {name}"`
- `SUPPORTED_LOCALES = ("fr", "en")` — adding a new locale requires updating this tuple and creating a new JSON file

## Dependencies

### Internal
- `src/websocket_app.py` — passes `locale` from `GroupChatSession` to prompt and i18n calls
- `src/prompts.py` / `src/prompts_en.py` — parallel locale-based prompt selection

### External
| Package | Purpose |
|---------|---------|
| `json` (stdlib) | JSON locale file parsing |
| `pathlib` (stdlib) | Locale file path resolution |

<!-- MANUAL: -->
