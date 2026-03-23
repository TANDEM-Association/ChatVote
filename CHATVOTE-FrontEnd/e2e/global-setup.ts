import { chromium } from "@playwright/test";
import { type ChildProcess, execSync, spawn } from "child_process";
import path from "path";

import { readPorts } from "./support/port-utils";

let emulatorProcess: ChildProcess | null = null;

async function globalSetup() {
  // Ports are already allocated synchronously by playwright.config.ts — just read them.
  const ports = readPorts();
  console.info(`Using ports — frontend: ${ports.frontend}`);

  // Check if emulators are already running
  const emulatorsRunning = await isServiceRunning("http://localhost:8081");

  if (!emulatorsRunning) {
    // Start Firebase emulators with permissive test rules
    const firebaseDir = path.resolve(
      __dirname,
      "../../CHATVOTE-BackEnd/firebase",
    );

    // Resolve full path to npx (nvm may not be in PATH for child processes)
    let npxPath = "npx";
    try {
      npxPath = execSync("which npx", { encoding: "utf-8" }).trim();
    } catch {
      // fallback to bare npx
    }

    emulatorProcess = spawn(
      npxPath,
      [
        "firebase",
        "emulators:start",
        "--project",
        "chat-vote-dev",
        "--only",
        "auth,firestore",
        "--config",
        "firebase-test.json",
      ],
      {
        cwd: firebaseDir,
        stdio: "pipe",
        detached: true,
        env: { ...process.env },
      },
    );

    // Log emulator output for debugging
    emulatorProcess.stdout?.on("data", (d) =>
      process.stdout.write(`[Emulator] ${d}`),
    );
    emulatorProcess.stderr?.on("data", (d) =>
      process.stderr.write(`[Emulator] ${d}`),
    );
    emulatorProcess.on("error", (err) =>
      console.error("Emulator spawn error:", err),
    );

    // Wait for emulators
    await waitForService("http://localhost:8081", 60000);
    await waitForService("http://localhost:9099", 60000);
    console.info("Firebase emulators started");
  } else {
    console.info("Firebase emulators already running");

    // Force-load permissive test rules even when emulators were started
    // externally (e.g. via `make dev` with production rules).
    const fs = await import("fs");
    const rulesPath = path.resolve(
      __dirname,
      "../../CHATVOTE-BackEnd/firebase/firestore-test.rules",
    );
    if (fs.existsSync(rulesPath)) {
      const rules = fs.readFileSync(rulesPath, "utf-8");
      try {
        const resp = await fetch(
          "http://localhost:8081/emulator/v1/projects/chat-vote-dev:securityRules",
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              rules: { files: [{ name: "firestore.rules", content: rules }] },
            }),
          },
        );
        if (resp.ok) {
          console.info("Loaded permissive test rules into running emulator");
        } else {
          console.warn(
            `Failed to load test rules: ${resp.status} ${await resp.text()}`,
          );
        }
      } catch (err) {
        console.warn("Could not upload test rules to emulator:", err);
      }
    }
  }

  // Seed test data
  await seedEmulatorData();

  // Warm up the Next.js test server using a real browser so Turbopack
  // compiles ALL client-side bundles before tests run.
  console.info("Warming up Next.js dev server...");
  await browserWarmup(`http://localhost:${ports.frontend}/chat`);
  console.info("Dev server warmed up");

  // Store references for teardown
  (globalThis as Record<string, unknown>).__EMULATOR_PROCESS__ =
    emulatorProcess;
}

async function isServiceRunning(url: string): Promise<boolean> {
  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(2000) });
    return resp.ok || resp.status < 500;
  } catch {
    return false;
  }
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

/**
 * Browser-based warmup: launches a headless Chromium, navigates to the given
 * URL with waitUntil:'load', which forces Turbopack to JIT-compile ALL
 * client-side bundles. After this runs, subsequent browser navigations in tests
 * hit the Turbopack cache and the 'load' event fires quickly even with 7+
 * parallel workers.
 */
async function browserWarmup(url: string): Promise<void> {
  // First confirm the HTTP server is up before launching the browser
  const start = Date.now();
  while (Date.now() - start < 60000) {
    try {
      const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (resp.status < 500) break;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(url, { waitUntil: "load", timeout: 120000 });
    await page.close();
  } finally {
    await browser.close();
  }
}

async function seedEmulatorData() {
  // Use firebase-admin to seed parties directly
  // Dynamic import returns { default: admin } in ESM context
  const adminModule = await import("firebase-admin");
  const admin = adminModule.default ?? adminModule;
  const fs = await import("fs");

  process.env.FIRESTORE_EMULATOR_HOST = "localhost:8081";

  const apps = admin.apps ?? [];
  if (!apps.length) {
    admin.initializeApp({ projectId: "chat-vote-dev" });
  }

  const db = admin.firestore();

  // Seed parties from existing data
  const partiesPath = path.resolve(
    __dirname,
    "../../CHATVOTE-BackEnd/firebase/firestore_data/dev/parties.json",
  );
  if (fs.existsSync(partiesPath)) {
    const parties = JSON.parse(fs.readFileSync(partiesPath, "utf-8"));

    // Handle both array and object formats
    type PartyRecord = Record<string, unknown> & {
      party_id?: string;
      id?: string;
    };
    const partyEntries: [string, PartyRecord][] = Array.isArray(parties)
      ? (parties as PartyRecord[]).map((p) => [
          String(p.party_id ?? p.id ?? ""),
          p,
        ])
      : (Object.entries(parties) as [string, PartyRecord][]);

    const batch = db.batch();
    for (const [id, data] of partyEntries) {
      // Ensure fields required by frontend queries exist
      if (!data.logo_url) {
        data.logo_url = `/images/logos/parties/${id}.svg`;
      }
      if (data.election_result_forecast_percent === undefined) {
        data.election_result_forecast_percent = 0;
      }
      batch.set(db.collection("parties").doc(id as string), data);
    }
    await batch.commit();
    console.info(`Seeded ${partyEntries.length} parties`);
  }

  // Seed municipalities (needed for municipality search)
  const testMunicipalities = [
    {
      code: "75056",
      nom: "Paris",
      zone: "metro",
      population: 2165423,
      surface: 10540,
      codesPostaux: [
        "75001",
        "75002",
        "75003",
        "75004",
        "75005",
        "75006",
        "75007",
        "75008",
        "75009",
        "75010",
        "75011",
        "75012",
        "75013",
        "75014",
        "75015",
        "75016",
        "75017",
        "75018",
        "75019",
        "75020",
      ],
      codeRegion: "11",
      codeDepartement: "75",
      siren: "217500016",
      codeEpci: "200054781",
      epci: { code: "200054781", nom: "Métropole du Grand Paris" },
      departement: { code: "75", nom: "Paris" },
      region: { code: "11", nom: "Île-de-France" },
      _syncedAt: new Date().toISOString(),
    },
    {
      code: "69123",
      nom: "Lyon",
      zone: "metro",
      population: 522250,
      surface: 4787,
      codesPostaux: [
        "69001",
        "69002",
        "69003",
        "69004",
        "69005",
        "69006",
        "69007",
        "69008",
        "69009",
      ],
      codeRegion: "84",
      codeDepartement: "69",
      siren: "216901231",
      codeEpci: "200046977",
      epci: { code: "200046977", nom: "Métropole de Lyon" },
      departement: { code: "69", nom: "Rhône" },
      region: { code: "84", nom: "Auvergne-Rhône-Alpes" },
      _syncedAt: new Date().toISOString(),
    },
    {
      code: "13055",
      nom: "Marseille",
      zone: "metro",
      population: 870731,
      surface: 24062,
      codesPostaux: [
        "13001",
        "13002",
        "13003",
        "13004",
        "13005",
        "13006",
        "13007",
        "13008",
        "13009",
        "13010",
        "13011",
        "13012",
        "13013",
        "13014",
        "13015",
        "13016",
      ],
      codeRegion: "93",
      codeDepartement: "13",
      siren: "211300553",
      codeEpci: "200054807",
      epci: { code: "200054807", nom: "Métropole d'Aix-Marseille-Provence" },
      departement: { code: "13", nom: "Bouches-du-Rhône" },
      region: { code: "93", nom: "Provence-Alpes-Côte d'Azur" },
      _syncedAt: new Date().toISOString(),
    },
  ];

  const muniBatch = db.batch();
  for (const muni of testMunicipalities) {
    muniBatch.set(db.collection("municipalities").doc(muni.code), muni);
  }
  await muniBatch.commit();
  console.info(`Seeded ${testMunicipalities.length} municipalities`);

  // Seed a test chat session (used by navigation test 1.9)
  await db.collection("chat_sessions").doc("e2e-nav-test-session").set({
    user_id: "anonymous",
    party_ids: [],
    title: "E2E Test Session",
    is_public: false,
    created_at: admin.firestore.Timestamp.now(),
    updated_at: admin.firestore.Timestamp.now(),
  });
  console.info("Seeded test chat session");

  // Seed system status
  await db
    .collection("system_status")
    .doc("llm_status")
    .set({ is_at_rate_limit: false });
  console.info("Seeded system status");

  // Clean up admin app to avoid conflicts with frontend firebase-admin
  await admin.app().delete();
  delete process.env.FIRESTORE_EMULATOR_HOST;
}

export default globalSetup;
