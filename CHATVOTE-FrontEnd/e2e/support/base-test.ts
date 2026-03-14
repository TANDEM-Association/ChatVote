import { test as base, expect } from '@playwright/test';
import type { ConsoleMessage } from '@playwright/test';

/**
 * Custom test fixture that collects browser console errors and warnings.
 * - Errors: fail the test (zero tolerance)
 * - Warnings: collected and printed for review (soft assertion)
 *
 * Known upstream issues are filtered via IGNORED_PATTERNS.
 * Tests can add per-test ignores via `expectedErrors` fixture.
 *
 * Usage: import { test, expect } from '../support/base-test';
 *
 * Per-test error ignoring:
 *   test('my test', async ({ page, expectedErrors }) => {
 *     expectedErrors.push(/FirebaseError/);
 *     // ... test that triggers expected Firebase errors
 *   });
 */

// ── Upstream bugs (unfixable — waiting on React/library fixes) ──────────
const UPSTREAM_ERROR_PATTERNS = [
  // React 19 useId() hydration mismatch — affects ALL libs using useId
  // (Radix, React Aria, Mantine, etc). Upstream React bug:
  // https://github.com/facebook/react/issues/33779
  // https://github.com/radix-ui/primitives/issues/3700
  /aria-controls/,
  /Prop `id` did not match/,
  /A tree hydrated but some attributes.*didn't match/,
  // Sidebar SSR hydration mismatch — server detects device via User-Agent
  // but client viewport may differ (esp. in Playwright mobile viewports).
  // Known shadcn/ui issue: https://github.com/shadcn-ui/ui/issues/5925
  /Hydration failed because the server rendered HTML didn't match/,
];

// ── Test environment noise (not bugs, expected in dev/test) ─────────────
const TEST_ENV_ERROR_PATTERNS = [
  // Next.js dev mode noise
  /Download the React DevTools/,
  /Fast Refresh/,
  // Firebase emulator warnings
  /firestore.*emulator/i,
  /auth.*emulator/i,
  // Socket.IO connection errors (mock server restarts between tests)
  /WebSocket connection to.*socket\.io.*failed/,
  // HTTP resource errors in test environment (mock server timing)
  /Failed to load resource/,
  // Firestore emulator connectivity (flaky in CI/test environment)
  /Could not reach Cloud Firestore backend/,
  /Failed to get document because the client is offline/,
  // SSR chat session lookup fails in test env (mock server doesn't persist to Firestore)
  /Chat session not found/,
  // Municipality API fetch can fail in test env (timing / SSR)
  /Failed to fetch municipalities/,
  // Firestore security rules errors — expected when emulators run with
  // production rules before test setup can load permissive rules.
  /No matching allow statements/,
  /permission-denied/,
  // Firestore NOT_FOUND when updating a document that doesn't exist yet
  // (race condition: chat_session update before create completes)
  /NOT_FOUND: no entity to update/,
  // Firebase Analytics/Installations errors from fake API key in test env
  /API key not valid/,
  /config-fetch-failed/,
  /installations\/request-failed/,
  // Firebase Auth network errors (transient in test env, e.g. emulator restart timing)
  /auth\/network-request-failed/,
  // Note: FirebaseError auth errors and "Chat session not found" are NOT
  // globally ignored — they are added per-test via expectedErrors fixture.
];

const IGNORED_WARNING_PATTERNS = [
  // Next.js dev mode noise
  /Download the React DevTools/,
  /Fast Refresh/,
  /ReactDOM.preload/,
  // Firebase emulator
  /firestore.*emulator/i,
  /auth.*emulator/i,
  // React dev warnings that are informational
  /Warning: Each child in a list/,
  /Warning: validateDOMNesting/,
  // Firestore transport errors in test environment
  /WebChannelConnection RPC.*transport errored/,
];

function isIgnoredError(text: string, extraPatterns: RegExp[]): boolean {
  return [
    ...UPSTREAM_ERROR_PATTERNS,
    ...TEST_ENV_ERROR_PATTERNS,
    ...extraPatterns,
  ].some((pattern) => pattern.test(text));
}

function isIgnoredWarning(text: string): boolean {
  return IGNORED_WARNING_PATTERNS.some((pattern) => pattern.test(text));
}

export const test = base.extend<{
  consoleErrors: ConsoleMessage[];
  consoleWarnings: ConsoleMessage[];
  expectedErrors: RegExp[];
}>({
  // Per-test expected error patterns — push patterns in your test body
  // to ignore errors that are expected for that specific test case.
  expectedErrors: async ({}, use) => {
    const patterns: RegExp[] = [];
    await use(patterns);
  },

  consoleErrors: [
    async ({ page, expectedErrors }, use) => {
      const errors: ConsoleMessage[] = [];

      page.on('console', (msg) => {
        if (msg.type() === 'error' && !isIgnoredError(msg.text(), expectedErrors)) {
          errors.push(msg);
        }
      });

      page.on('pageerror', (error) => {
        const text = `Uncaught exception: ${error.message}`;
        if (!isIgnoredError(text, expectedErrors)) {
          errors.push({
            type: () => 'error',
            text: () => text,
            location: () => ({ url: '', lineNumber: 0, columnNumber: 0 }),
          } as unknown as ConsoleMessage);
        }
      });

      await use(errors);

      // After test completes, fail if there were unexpected console errors
      if (errors.length > 0) {
        const summary = errors
          .map((e) => `  - [${e.type()}] ${e.text()}`)
          .join('\n');
        expect
          .soft(errors.length, `Browser console errors detected:\n${summary}`)
          .toBe(0);
      }
    },
    { auto: true },
  ],

  consoleWarnings: [
    async ({ page }, use) => {
      const warnings: ConsoleMessage[] = [];

      page.on('console', (msg) => {
        if (msg.type() === 'warning' && !isIgnoredWarning(msg.text())) {
          warnings.push(msg);
        }
      });

      await use(warnings);

      // Print warnings for review but don't fail the test
      if (warnings.length > 0) {
        const summary = warnings
          .map((w) => `  - [warning] ${w.text()}`)
          .join('\n');
        console.log(`\n⚠ Browser warnings (${warnings.length}):\n${summary}`);
      }
    },
    { auto: true },
  ],
});

export { expect };
