<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-03-04 | Updated: 2026-03-04 -->

# public

## Purpose
Static assets served directly by Next.js at the root URL path. Contains images (logos, party logos, icons, favicons), PWA assets (manifest, service worker), and the PDF.js web worker binary used by `react-pdf` for client-side PDF rendering.

## Key Files
| File | Description |
|------|-------------|
| `service-worker.js` | Firebase Auth service worker — handles session cookie management for SSR auth |
| `pdf.worker.min.mjs` | PDF.js web worker binary used by `react-pdf` / `pdfjs-dist` for off-thread PDF parsing |
| `web-app-manifest-192x192.png` | PWA manifest icon at 192×192px |
| `web-app-manifest-512x512.png` | PWA manifest icon at 512×512px |
| `images/` | All image assets: `logos/` (chatvote SVG/WebP), `icons/` (favicons in multiple sizes and formats), party logos |

## For AI Agents

### Working In This Directory
- Files in `public/` are served at `/` — `public/images/logo.webp` is accessible at `/images/logo.webp`.
- `service-worker.js` is registered by `AuthServiceWorkerProvider` in `src/components/providers/`. Do not rename or move it — the registration URL is hardcoded.
- `pdf.worker.min.mjs` is required by `pdfjs-dist`. Its path is configured in `src/components/pdf-view.tsx` via `GlobalWorkerOptions.workerSrc`. Do not rename.
- Favicon files follow the naming convention set in `src/app/layout.tsx` `generateMetadata()` — update both if adding new sizes.
- SVG files for party logos must be optimized (no embedded scripts) as they are displayed with `next/image`.

### Common Patterns
- Reference public assets in components with a leading `/`: `src="/images/logos/chatvote.svg"`.
- Use `next/image` for all image rendering to get automatic optimization, lazy loading, and WebP conversion.
- PWA manifest is defined in `src/app/manifest.json` (a Next.js route handler) — `public/web-app-manifest-*.png` are the icon files it references.

<!-- MANUAL: -->
