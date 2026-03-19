<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-19 -->

# src/components/ui

## Purpose

Base UI primitive components — a combination of shadcn/ui generated components and custom primitives. These are the lowest-level building blocks used throughout the application. All components are unstyled by default and styled via Tailwind CSS v4 utility classes.

## Key Files

| File                | Description                                                                     |
| ------------------- | ------------------------------------------------------------------------------- |
| `accordion.tsx`     | Radix UI Accordion wrapper                                                      |
| `badge.tsx`         | Status badge with CVA variants                                                  |
| `border-trail.tsx`  | Animated glowing border trail effect (custom, used on hover states)             |
| `button.tsx`        | Button with CVA variants (default, outline, ghost, link, destructive) and sizes |
| `card.tsx`          | Card container with header/content/footer slots                                 |
| `carousel.tsx`      | Embla Carousel wrapper with navigation controls                                 |
| `chart.tsx`         | Recharts wrapper with theme-aware color tokens                                  |
| `collapsible.tsx`   | Radix UI Collapsible wrapper                                                    |
| `drawer.tsx`        | Vaul drawer for mobile bottom sheets                                            |
| `dropdown-menu.tsx` | Radix UI DropdownMenu wrapper                                                   |
| `input.tsx`         | Text input with consistent focus/error styles                                   |
| `label.tsx`         | Radix UI Label wrapper                                                          |
| `modal.tsx`         | Modal dialog overlay (custom)                                                   |
| `select.tsx`        | Radix UI Select wrapper                                                         |
| `separator.tsx`     | Radix UI Separator wrapper                                                      |
| `sheet.tsx`         | Radix UI Sheet (side panel) wrapper                                             |
| `sidebar.tsx`       | App sidebar with `SidebarProvider`, `useSidebar` hook                           |
| `skeleton.tsx`      | Loading skeleton placeholder                                                    |
| `slider.tsx`        | Radix UI Slider wrapper                                                         |
| `sonner.tsx`        | Sonner toast notification wrapper                                               |
| `text-loop.tsx`     | Animated cycling text (custom)                                                  |
| `textarea.tsx`      | Textarea with consistent styles                                                 |
| `tooltip.tsx`       | Radix UI Tooltip wrapper with `TooltipProvider`                                 |

## For AI Agents

### Working In This Directory

- These components are generated/maintained in the shadcn/ui style. Do not restructure them — follow the existing pattern when adding new primitives.
- To add a new shadcn/ui component: run `npx shadcn@latest add <component>` from `CHATVOTE-FrontEnd/`. This updates `components.json` and creates the file here.
- Use `cn()` from `@lib/utils` for class merging inside these components — it combines `clsx` and `tailwind-merge`.
- CVA (`class-variance-authority`) is used for variant-based styling. Follow the `button.tsx` pattern for new variant-based components.
- `border-trail.tsx` and `text-loop.tsx` are custom animations — they use `motion` (Motion One for React).

### Common Patterns

```typescript
// Standard shadcn/ui component pattern
import { cn } from "@lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "outline" | "ghost";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", ...props }, ref) => {
    return <button ref={ref} className={cn(variants({ variant }), className)} {...props} />;
  }
);
```

## Dependencies

### External

- `@radix-ui/*` — accessible headless primitives
- `class-variance-authority` — CVA for variant-based styling
- `clsx` + `tailwind-merge` — class merging via `cn()`
- `embla-carousel-react` — for `carousel.tsx`
- `vaul` — for `drawer.tsx`
- `sonner` — for `sonner.tsx`
- `recharts` — for `chart.tsx`
- `motion` — for `border-trail.tsx`, `text-loop.tsx`

<!-- MANUAL: -->
