/**
 * Utility to clear Firebase emulator state between tests.
 *
 * The Firestore emulator accumulates documents, snapshot listeners, and
 * connection state across tests. After ~30 tests this can cause setDoc /
 * onSnapshot calls to hang, leading to flaky failures in tests that depend
 * on Firebase writes (streaming, quick-replies, persisted-sessions).
 *
 * Clearing via the emulator REST API resets internal state (including dead
 * listener bookkeeping) so subsequent tests start fresh.
 */

const PROJECT_ID = 'chat-vote-dev';
const FIRESTORE_HOST = 'http://localhost:8081';
const AUTH_HOST = 'http://localhost:9099';

/**
 * Clear all documents from the Firestore emulator.
 * Also resets internal listener/connection state.
 */
export async function clearFirestoreEmulator(): Promise<void> {
  await fetch(
    `${FIRESTORE_HOST}/emulator/v1/projects/${PROJECT_ID}/databases/(default)/documents`,
    { method: 'DELETE' },
  );
}

/**
 * Clear all auth accounts from the Auth emulator.
 */
export async function clearAuthEmulator(): Promise<void> {
  await fetch(
    `${AUTH_HOST}/emulator/v1/projects/${PROJECT_ID}/accounts`,
    { method: 'DELETE' },
  );
}

/**
 * Re-seed the minimum reference data needed for tests to work.
 * This must be called after clearFirestoreEmulator() since it wipes everything.
 */
export async function seedReferenceData(): Promise<void> {
  const adminModule = await import('firebase-admin');
  const admin = adminModule.default ?? adminModule;
  const fs = await import('fs');
  const path = await import('path');

  process.env.FIRESTORE_EMULATOR_HOST = 'localhost:8081';

  const apps = admin.apps ?? [];
  if (!apps.length) {
    admin.initializeApp({ projectId: PROJECT_ID });
  }

  const db = admin.firestore();

  // Seed parties
  const partiesPath = path.resolve(
    __dirname,
    '../../../CHATVOTE-BackEnd/firebase/firestore_data/dev/parties.json',
  );
  if (fs.existsSync(partiesPath)) {
    const parties = JSON.parse(fs.readFileSync(partiesPath, 'utf-8'));
    const partyEntries: [string, any][] = Array.isArray(parties)
      ? parties.map((p: any) => [p.party_id || p.id, p])
      : Object.entries(parties);
    const batch = db.batch();
    for (const [id, data] of partyEntries) {
      batch.set(db.collection('parties').doc(id as string), data);
    }
    await batch.commit();
  }

  // Seed municipalities
  const municipalities = [
    { code: '75056', nom: 'Paris', zone: 'metro', population: 2165423 },
    { code: '69123', nom: 'Lyon', zone: 'metro', population: 522250 },
    { code: '13055', nom: 'Marseille', zone: 'metro', population: 870731 },
  ];
  const muniBatch = db.batch();
  for (const muni of municipalities) {
    muniBatch.set(db.collection('municipalities').doc(muni.code), muni);
  }
  await muniBatch.commit();

  // Seed system status
  await db.collection('system_status').doc('llm_status').set({ is_at_rate_limit: false });

  // Clean up admin app
  await admin.app().delete();
  delete process.env.FIRESTORE_EMULATOR_HOST;
}

/**
 * Full reset: clear emulators + re-seed reference data.
 * Call this from test.beforeAll() in files that send messages.
 */
export async function resetEmulatorState(): Promise<void> {
  await Promise.all([
    clearFirestoreEmulator(),
    clearAuthEmulator(),
  ]);
  await seedReferenceData();
  // After a clearFirestoreEmulator() the emulator's internal gRPC/HTTP channels
  // can take a moment to settle.  The first client-SDK setDoc (e.g. createChatSession)
  // will hang for several seconds if the emulator isn't fully ready yet, causing the
  // first serial test to time out.  We probe via the Firestore REST API here — inside
  // the setup project — so that cost is paid once in setup, not inside a test.
  await waitForFirestoreReady();
}

async function waitForFirestoreReady(maxAttempts = 20): Promise<void> {
  const docUrl =
    `${FIRESTORE_HOST}/v1/projects/${PROJECT_ID}/databases/(default)/documents/_e2e_warmup/ping`;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const resp = await fetch(docUrl, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fields: { ts: { integerValue: String(Date.now()) } } }),
        signal: AbortSignal.timeout(3000),
      });
      if (resp.ok) {
        // Clean up the warmup document so it doesn't pollute Firestore
        await fetch(docUrl, { method: 'DELETE', signal: AbortSignal.timeout(2000) }).catch(() => {});
        console.log('[EmulatorCleanup] Firestore emulator ready');
        return;
      }
    } catch {
      // not ready yet — retry
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  console.warn('[EmulatorCleanup] Firestore warmup timed out — proceeding anyway');
}
