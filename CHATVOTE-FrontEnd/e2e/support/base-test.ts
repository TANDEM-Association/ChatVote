import { test as base, expect } from '@playwright/test';
import type { ConsoleMessage } from '@playwright/test';

/**
 * Custom test fixture that collects browser console errors and fails
 * the test if any unexpected errors are detected (e.g. Next.js hydration
 * errors, unhandled exceptions).
 *
 * Usage: import { test, expect } from '../support/base-test';
 */

// Known warnings that are safe to ignore (upstream bugs, expected in dev).
const IGNORED_PATTERNS = [
  // React useId hydration mismatch — upstream React bug affecting all libs
  // using useId (Radix, React Aria, Mantine, etc). See:
  // https://github.com/radix-ui/primitives/issues/3700
  /Prop `aria-controls` did not match/,
  /Prop `id` did not match/,
  // Next.js dev mode noise
  /Download the React DevTools/,
  /Fast Refresh/,
  // Firebase emulator warnings
  /firestore.*emulator/i,
  /auth.*emulator/i,
];

function isIgnored(text: string): boolean {
  return IGNORED_PATTERNS.some((pattern) => pattern.test(text));
}

export const test = base.extend<{ consoleErrors: ConsoleMessage[] }>({
  consoleErrors: [
    async ({ page }, use) => {
      const errors: ConsoleMessage[] = [];

      page.on('console', (msg) => {
        if (msg.type() === 'error' && !isIgnored(msg.text())) {
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
});

export { expect };
