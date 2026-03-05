import { test as base, expect } from '@playwright/test';
import type { ConsoleMessage } from '@playwright/test';

/**
 * Custom test fixture that collects browser console errors and warnings.
 * - Errors: fail the test (zero tolerance)
 * - Warnings: collected and printed for review (soft assertion)
 *
 * Known upstream issues are filtered via IGNORED_PATTERNS.
 *
 * Usage: import { test, expect } from '../support/base-test';
 */

// Known messages safe to ignore (upstream bugs, expected in test/dev).
const IGNORED_ERROR_PATTERNS = [
  // React useId hydration mismatch — upstream React bug affecting all libs
  // using useId (Radix, React Aria, Mantine, etc). See:
  // https://github.com/radix-ui/primitives/issues/3700
  /aria-controls/,
  /Prop `id` did not match/,
  /A tree hydrated but some attributes.*didn't match/,
  // Next.js dev mode noise
  /Download the React DevTools/,
  /Fast Refresh/,
  // Firebase emulator warnings
  /firestore.*emulator/i,
  /auth.*emulator/i,
  // Socket.IO connection errors (expected when mock server restarts between tests)
  /WebSocket connection to.*socket\.io.*failed/,
  // HTTP resource errors in test environment (mock server timing)
  /Failed to load resource/,
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
];

function isIgnoredError(text: string): boolean {
  return IGNORED_ERROR_PATTERNS.some((pattern) => pattern.test(text));
}

function isIgnoredWarning(text: string): boolean {
  return IGNORED_WARNING_PATTERNS.some((pattern) => pattern.test(text));
}

export const test = base.extend<{
  consoleErrors: ConsoleMessage[];
  consoleWarnings: ConsoleMessage[];
}>({
  consoleErrors: [
    async ({ page }, use) => {
      const errors: ConsoleMessage[] = [];

      page.on('console', (msg) => {
        if (msg.type() === 'error' && !isIgnoredError(msg.text())) {
          errors.push(msg);
        }
      });

      page.on('pageerror', (error) => {
        // pageerror fires for uncaught exceptions — always capture
        errors.push({
          type: () => 'error',
          text: () => `Uncaught exception: ${error.message}`,
          location: () => ({ url: '', lineNumber: 0, columnNumber: 0 }),
        } as unknown as ConsoleMessage);
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
