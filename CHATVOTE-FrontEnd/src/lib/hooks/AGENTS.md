<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/lib/hooks

## Purpose

Custom React hooks shared across the frontend. Each hook encapsulates a specific piece of reusable behavior: hydration state, carousel index tracking, scroll locking, chat URL parameter parsing, and theme management.

## Key Files

| File                            | Description                                                                                                      |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `use-is-mounted.ts`             | Returns `false` during SSR/initial hydration, `true` after mount. Used to suppress Radix UI hydration mismatches |
| `use-carousel-current-index.ts` | Tracks the current slide index of an Embla Carousel instance                                                     |
| `use-lock-scroll.ts`            | Locks body scroll when a modal or sheet is open (uses `react-remove-scroll`)                                     |
| `useLockScroll.ts`              | Legacy variant of scroll lock (kept for compatibility)                                                           |
| `use-chat-param.ts`             | Reads chat-specific URL query parameters (`q`, `parties`, `municipality_code`)                                   |
| `useTheme.ts`                   | Reads and toggles the active theme (`dark` / `light`) using `next-themes`                                        |

## For AI Agents

### Working In This Directory

- All hooks follow the `use` prefix convention.
- New hooks go here if they are used by more than one component. Single-use hooks can be co-located with their component.
- `useIsMounted` pattern: initialize state as `false`, set to `true` in a `useEffect`. This is the standard SSR guard for Radix primitives.
- `use-carousel-current-index.ts` works with Embla's `EmblaCarouselType` API — always pass the `embla` instance returned by `useEmblaCarousel()`.

### Common Patterns

```typescript
// Hydration guard
const isMounted = useIsMounted();
if (!isMounted) return <Skeleton />;

// URL params
const { initialQuestion, partyIds, municipalityCode } = useChatParam();
```

## Dependencies

### External

- `embla-carousel-react` — for `use-carousel-current-index.ts`
- `react-remove-scroll` — for scroll lock hooks
- `next-themes` — for `useTheme.ts`
- `next/navigation` — `useSearchParams()` for URL param hooks

<!-- MANUAL: -->
