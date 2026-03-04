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
      projectId:
        process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || "chat-vote-dev",
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

  console.log(
    `[municipalities] Fetching from Firestore (emulator=${process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true"}, host=${process.env.FIRESTORE_EMULATOR_HOST ?? "production"})`,
  );

  const snapshot = await db.collection("municipalities").get();

  console.log(`[municipalities] Fetched ${snapshot.docs.length} documents`);

  const municipalities = snapshot.docs.map(
    (docSnap) => docSnap.data() as Municipality,
  );

  // Sort by population (descending)
  municipalities.sort((a, b) => (b.population || 0) - (a.population || 0));

  cachedMunicipalities = municipalities;
  cacheTimestamp = now;

  return municipalities;
}

export async function GET() {
  try {
    const municipalities = await loadMunicipalities();

    const isDev =
      process.env.NEXT_PUBLIC_USE_FIREBASE_EMULATORS === "true";

    return NextResponse.json(municipalities, {
      headers: {
        "Cache-Control": isDev
          ? "no-store"
          : "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800",
      },
    });
  } catch (error) {
    console.error("Error fetching municipalities:", error);
    return NextResponse.json(
      { error: "Failed to fetch municipalities" },
      { status: 500 },
    );
  }
}
