import { test as setup, chromium } from '@playwright/test';
import { resetEmulatorState } from '../support/emulator-cleanup';
import { readPorts } from '../support/port-utils';

/**
 * Setup project that resets Firebase emulator state once before
 * all message-sending tests run. This ensures a clean emulator
 * state after the parallel UI tests have finished.
 */
setup('reset firebase emulator', async () => {
  await resetEmulatorState();

  // After clearFirestoreEmulator(), the emulator's WebChannel (grpc-web) handler
  // needs a browser-based request to re-initialise. The REST API warmup in
  // resetEmulatorState() primes the HTTP channel, but the Firestore client SDK
  // in browsers uses WebChannel for reads/writes. Navigate a real browser to
  // the app so the Firebase SDK establishes its WebChannel connection to the
  // emulator before any test browser tries to write (createChatSession).
  const ports = readPorts();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(`http://localhost:${ports.frontend}/chat`, { waitUntil: 'load', timeout: 30000 });
    // Allow Firestore SDK time to complete its initial connection handshake.
    await page.waitForTimeout(2000);
    console.log('[EmulatorReset] Browser WebChannel warmup complete');
  } finally {
    await browser.close();
  }
});
