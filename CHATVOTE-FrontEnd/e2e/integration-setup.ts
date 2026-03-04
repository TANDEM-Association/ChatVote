import { ChildProcess, spawn } from 'child_process';
import path from 'path';

let backendProcess: ChildProcess | null = null;
let emulatorProcess: ChildProcess | null = null;

async function integrationSetup() {
  // Start Firebase emulators
  const firebaseDir = path.resolve(__dirname, '../../CHATVOTE-BackEnd/firebase');
  emulatorProcess = spawn(
    'npx',
    ['firebase', 'emulators:start', '--project', 'chat-vote-dev', '--only', 'auth,firestore'],
    {
      cwd: firebaseDir,
      stdio: 'pipe',
      detached: true,
    },
  );

  await waitForService('http://localhost:8081', 30000);
  await waitForService('http://localhost:9099', 30000);
  console.log('Firebase emulators ready');

  await seedEmulatorData();

  // Verify Ollama is running
  try {
    await fetch('http://localhost:11434/api/tags');
    console.log('Ollama is running');
  } catch {
    throw new Error('Ollama is not running. Start it with: ollama serve');
  }

  // Start Python backend
  const backendDir = path.resolve(__dirname, '../../CHATVOTE-BackEnd');
  backendProcess = spawn('poetry', ['run', 'python', '-m', 'src.aiohttp_app', '--debug'], {
    cwd: backendDir,
    stdio: 'pipe',
    detached: true,
    env: {
      ...process.env,
      ENV: 'local',
      OLLAMA_BASE_URL: 'http://localhost:11434',
      OLLAMA_MODEL: 'llama3.2',
    },
  });

  await waitForService('http://localhost:8080', 30000);
  console.log('Python backend ready on :8080');

  (globalThis as any).__BACKEND_PROCESS__ = backendProcess;
  (globalThis as any).__EMULATOR_PROCESS__ = emulatorProcess;
}

async function waitForService(url: string, timeoutMs: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const resp = await fetch(url);
      if (resp.ok || resp.status < 500) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Service at ${url} did not start within ${timeoutMs}ms`);
}

async function seedEmulatorData() {
  // Dynamic import returns { default: admin } in ESM context
  const adminModule = await import('firebase-admin');
  const admin = adminModule.default ?? adminModule;
  const fs = await import('fs');

  process.env.FIRESTORE_EMULATOR_HOST = 'localhost:8081';

  const apps = admin.apps ?? [];
  if (!apps.length) {
    admin.initializeApp({ projectId: 'chat-vote-dev' });
  }

  const db = admin.firestore();

  const partiesPath = path.resolve(
    __dirname,
    '../../CHATVOTE-BackEnd/firebase/firestore_data/dev/parties.json',
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
    console.log(`Seeded ${partyEntries.length} parties`);
  }

  await db.collection('system_status').doc('llm_status').set({ is_at_rate_limit: false });
  console.log('Seeded system status');

  await admin.app().delete();
  delete process.env.FIRESTORE_EMULATOR_HOST;
}

export default integrationSetup;
