import { NextResponse } from "next/server";

import { type Municipality } from "@lib/election/election.types";
import { credential } from "firebase-admin";
import {
  type App as FirebaseApp,
  getApps,
  initializeApp as initializeAdminApp,
} from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";

// --- Firebase Admin singleton (emulator-aware) ---

function getAdminApp(): FirebaseApp {
  const existingApps = getApps();
  if (existingApps.length > 0) {
    return existingApps[0];
  }

  const useEmulators =
    process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true";

  if (useEmulators) {
    process.env.FIRESTORE_EMULATOR_HOST ??= "localhost:8081";
    return initializeAdminApp({
      projectId: "chat-vote-dev",
    });
  }

  const {
    NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    FIREBASE_CLIENT_EMAIL,
    FIREBASE_PRIVATE_KEY,
  } = process.env;

  if (
    !NEXT_PUBLIC_FIREBASE_PROJECT_ID ||
    !FIREBASE_CLIENT_EMAIL ||
    !FIREBASE_PRIVATE_KEY
  ) {
    throw new Error("Missing Firebase environment variables.");
  }

  return initializeAdminApp({
    credential: credential.cert({
      projectId: NEXT_PUBLIC_FIREBASE_PROJECT_ID,
      clientEmail: FIREBASE_CLIENT_EMAIL,
      privateKey: FIREBASE_PRIVATE_KEY.replace(/\\n/g, "\n"),
    }),
  });
}

// --- Municipality loading ---

let cachedMunicipalities: Municipality[] | null = null;
let cacheTimestamp = 0;
const CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours

async function loadMunicipalities(): Promise<Municipality[]> {
  const now = Date.now();

  if (cachedMunicipalities !== null && now - cacheTimestamp < CACHE_TTL) {
    return cachedMunicipalities;
  }

  const app = getAdminApp();
  const db = getFirestore(app);

  console.info(
    `[municipalities] Fetching from Firestore (emulator=${process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true"}, host=${process.env.FIRESTORE_EMULATOR_HOST ?? "production"})`,
  );

  const snapshot = await db.collection("municipalities").get();

  console.info(`[municipalities] Fetched ${snapshot.docs.length} documents`);

  const municipalities = snapshot.docs.map(
    (docSnap) => docSnap.data() as Municipality,
  );

  // Sort by population (descending)
  municipalities.sort((a, b) => (b.population || 0) - (a.population || 0));

  cachedMunicipalities = municipalities;
  cacheTimestamp = now;

  return municipalities;
}

const MAX_RESULTS = 20;

function searchMunicipalities(
  municipalities: Municipality[],
  q: string,
): Municipality[] {
  const term = q.trim().toLowerCase();
  if (term.length < 2) return [];

  const isNumeric = /^\d+$/.test(term);

  const results = municipalities.filter((m) => {
    if (isNumeric) {
      return (
        m.code.includes(term) ||
        (m.codesPostaux ?? []).some((cp) => cp.includes(term))
      );
    }
    return m.nom.toLowerCase().includes(term);
  });

  return results.slice(0, MAX_RESULTS);
}

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const q = searchParams.get("q") ?? "";
    const code = searchParams.get("code") ?? "";

    const municipalities = await loadMunicipalities();

    const isDev = process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true";
    const cacheHeader = isDev
      ? "no-store"
      : "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800";

    // Single lookup by INSEE code
    if (code) {
      const match = municipalities.find((m) => m.code === code) ?? null;
      return NextResponse.json(match, { headers: { "Cache-Control": cacheHeader } });
    }

    // Search query — filter server-side
    if (q) {
      const results = searchMunicipalities(municipalities, q);
      return NextResponse.json(results, { headers: { "Cache-Control": cacheHeader } });
    }

    // No params — return empty (avoid dumping all data to client)
    return NextResponse.json([], { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Error fetching municipalities:", error);
    return NextResponse.json(
      { error: "Failed to fetch municipalities" },
      { status: 500 },
    );
  }
}
