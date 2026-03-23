#!/usr/bin/env npx tsx
/* eslint-disable no-console, @typescript-eslint/no-explicit-any */
/**
 * Download a conversation from Firestore (prod or dev) with all associated data:
 * - Chat session document + messages
 * - Candidate data for the municipality
 * - Associated PDFs (professions de foi)
 *
 * Usage:
 *   npx tsx scripts/download-conversation.ts <session-id> [--env prod|dev] [--out ./output]
 *
 * Examples:
 *   npx tsx scripts/download-conversation.ts c7cd8fda-7bef-4eeb-9e38-5c1f34f8abea
 *   npx tsx scripts/download-conversation.ts c7cd8fda-7bef-4eeb-9e38-5c1f34f8abea --env prod --out ./debug-session
 */

import admin from "firebase-admin";
import fs from "fs";
import path from "path";

// ---------------------------------------------------------------------------
// CLI args
// ---------------------------------------------------------------------------
const args = process.argv.slice(2);

function getArg(flag: string, defaultValue: string): string {
  const idx = args.indexOf(flag);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : defaultValue;
}

const sessionId: string = args.find((a) => !a.startsWith("--")) ?? "";
if (!sessionId) {
  console.error(
    "Usage: npx tsx scripts/download-conversation.ts <session-id> [--env prod|dev] [--out ./output]",
  );
  process.exit(1);
}

const env = getArg("--env", "prod");
const outDir = getArg("--out", `./debug-sessions/${sessionId}`);

// ---------------------------------------------------------------------------
// Firebase init
// ---------------------------------------------------------------------------
function initFirebase() {
  if (env === "dev") {
    process.env.FIRESTORE_EMULATOR_HOST =
      process.env.FIRESTORE_EMULATOR_HOST || "localhost:8081";
    return admin.initializeApp({ projectId: "chat-vote-dev" });
  }

  // Env vars loaded via bun --env-file=.env.prod.local
  const projectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
  const clientEmail = process.env.FIREBASE_CLIENT_EMAIL;
  const privateKey = process.env.FIREBASE_PRIVATE_KEY;

  if (projectId && clientEmail && privateKey) {
    return admin.initializeApp({
      credential: admin.credential.cert({
        projectId,
        clientEmail,
        privateKey: privateKey.replace(/\\n/g, "\n"),
      }),
    });
  }

  console.error("No Firebase credentials found.");
  console.error(
    "Run: vercel env pull .env.prod.local --environment production",
  );
  process.exit(1);
}

const app = initFirebase();
const db = admin.firestore(app);

// ---------------------------------------------------------------------------
// Download functions
// ---------------------------------------------------------------------------

async function downloadSession() {
  console.log(`\n📥 Downloading session: ${sessionId}`);
  const doc = await db.collection("chat_sessions").doc(sessionId).get();

  if (!doc.exists) {
    console.error(`❌ Session ${sessionId} not found in Firestore`);
    process.exit(1);
  }

  const data = doc.data() as Record<string, any>;
  console.log(`  Mode: ${data.mode || "socket"}`);
  console.log(`  Municipality: ${data.municipality_code || "none"}`);
  console.log(`  Party IDs: ${data.party_ids?.join(", ") || "none"}`);
  console.log(`  Messages (inline): ${data.messages?.length || 0}`);

  return { id: doc.id, ...data } as Record<string, any> & { id: string };
}

async function downloadSubMessages() {
  console.log(`\n📥 Downloading sub-collection messages...`);
  const snapshot = await db
    .collection("chat_sessions")
    .doc(sessionId)
    .collection("messages")
    .orderBy("created_at", "asc")
    .get();

  console.log(`  Found ${snapshot.docs.length} message groups`);
  return snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
}

async function downloadCandidates(municipalityCode: string) {
  console.log(
    `\n📥 Downloading candidates for municipality: ${municipalityCode}`,
  );
  const snapshot = await db
    .collection("candidates")
    .where("municipality_code", "==", municipalityCode)
    .get();

  console.log(`  Found ${snapshot.docs.length} candidates`);
  return snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
}

async function downloadParties(partyIds: string[]) {
  if (!partyIds?.length) return [];
  console.log(`\n📥 Downloading ${partyIds.length} parties...`);
  const results = [];
  for (const id of partyIds) {
    const doc = await db.collection("parties").doc(id).get();
    if (doc.exists) {
      results.push({ id: doc.id, ...doc.data() });
    }
  }
  console.log(`  Found ${results.length} parties`);
  return results;
}

async function downloadPdfs(candidates: any[]) {
  const pdfDir = path.join(outDir, "pdfs");
  fs.mkdirSync(pdfDir, { recursive: true });

  const s3Base = "https://chatvote-public-assets.s3.fr-par.scw.cloud";
  let downloaded = 0;

  for (const cand of candidates) {
    const code = cand.municipality_code;
    const candId = cand.id;

    // Try S3 profession de foi
    const pdfUrl = `${s3Base}/public/professions_de_foi/${code}/${candId}.pdf`;
    try {
      const res = await fetch(pdfUrl);
      if (res.ok) {
        const buffer = Buffer.from(await res.arrayBuffer());
        const filename = `${candId}.pdf`;
        fs.writeFileSync(path.join(pdfDir, filename), buffer);
        console.log(
          `  ✅ ${filename} (${(buffer.length / 1024).toFixed(0)} KB)`,
        );
        downloaded++;
      }
    } catch {
      // skip
    }

    // Try manifesto URL if set
    if (cand.manifesto_url && cand.manifesto_url.startsWith("http")) {
      try {
        const res = await fetch(cand.manifesto_url);
        if (res.ok) {
          const buffer = Buffer.from(await res.arrayBuffer());
          const filename = `${candId}-manifesto.pdf`;
          fs.writeFileSync(path.join(pdfDir, filename), buffer);
          console.log(
            `  ✅ ${filename} (${(buffer.length / 1024).toFixed(0)} KB)`,
          );
          downloaded++;
        }
      } catch {
        // skip
      }
    }
  }

  console.log(`  Downloaded ${downloaded} PDFs`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  console.log(`🔍 Environment: ${env}`);
  console.log(`📂 Output: ${outDir}`);

  fs.mkdirSync(outDir, { recursive: true });

  // 1. Download session
  const session = await downloadSession();
  fs.writeFileSync(
    path.join(outDir, "session.json"),
    JSON.stringify(session, null, 2),
  );

  // 2. Download sub-collection messages (socket mode)
  const subMessages = await downloadSubMessages();
  if (subMessages.length > 0) {
    fs.writeFileSync(
      path.join(outDir, "messages-subcollection.json"),
      JSON.stringify(subMessages, null, 2),
    );
  }

  // 3. Download candidates
  const municipalityCode = session.municipality_code;
  let candidates: any[] = [];
  if (municipalityCode) {
    candidates = await downloadCandidates(municipalityCode);
    fs.writeFileSync(
      path.join(outDir, "candidates.json"),
      JSON.stringify(candidates, null, 2),
    );
  }

  // 4. Download parties
  const partyIds = session.party_ids || [];
  const parties = await downloadParties(partyIds);
  if (parties.length > 0) {
    fs.writeFileSync(
      path.join(outDir, "parties.json"),
      JSON.stringify(parties, null, 2),
    );
  }

  // 5. Download PDFs
  if (candidates.length > 0) {
    console.log(`\n📥 Downloading PDFs...`);
    await downloadPdfs(candidates);
  }

  // 6. Summary
  console.log(`\n✅ Done! Files saved to: ${outDir}`);
  console.log(`\nContents:`);
  const files = fs.readdirSync(outDir, { recursive: true }) as string[];
  for (const f of files) {
    const stat = fs.statSync(path.join(outDir, f));
    if (stat.isFile()) {
      console.log(`  ${f} (${(stat.size / 1024).toFixed(1)} KB)`);
    }
  }

  // 7. Print diagnosis for source citation issue
  if (session.mode === "ai" && session.messages?.length) {
    console.log(`\n🔍 AI SDK Message Analysis:`);
    for (let i = 0; i < session.messages.length; i++) {
      const msg = session.messages[i];
      const citations = (msg.content || "").match(/\[\d+\]/g);
      console.log(
        `  msg[${i}] role=${msg.role} len=${msg.content?.length || 0} citations=${citations?.length || 0}${citations ? ` (${citations.join(", ")})` : ""}`,
      );
    }
    console.log(`\n⚠️  Note: AI SDK messages are stored as plain text only.`);
    console.log(
      `   Tool results (sources) are NOT persisted, so citations break on reload.`,
    );
  }

  process.exit(0);
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
