#!/usr/bin/env npx tsx
/**
 * Seed RAGFlow datasets via API.
 *
 * Creates:
 *   - One dataset per party (chunk_method: "laws") — for political manifestos
 *   - One "all-manifestos" global dataset (chunk_method: "laws")
 *   - One "candidates-websites" dataset (chunk_method: "naive") — for scraped content
 *
 * Idempotent: skips datasets that already exist by name.
 *
 * Usage:
 *   npx tsx scripts/ragflow-seed-datasets.ts
 *
 * Requires RAGFLOW_API_URL and RAGFLOW_API_KEY in .env.local
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';

// Load .env.local manually (no dotenv dependency needed)
const envPath = resolve(__dirname, '..', '.env.local');
try {
  const envContent = readFileSync(envPath, 'utf-8');
  for (const line of envContent.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim();
    if (!process.env[key]) process.env[key] = value;
  }
} catch {
  console.warn('⚠️  Could not read .env.local — using existing env vars');
}

import { createDataset, listDatasets } from '../src/lib/ai/ragflow-client';
import { initializeApp, cert, getApps } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';

// ── Firebase Admin init (reuse pattern from firebase-admin.ts) ───────────────
if (getApps().length === 0) {
  const credBase64 = process.env.FIREBASE_CREDENTIALS_BASE64;
  if (credBase64) {
    const cred = JSON.parse(Buffer.from(credBase64, 'base64').toString());
    initializeApp({ credential: cert(cred) });
  } else {
    // Local dev: uses FIREBASE_AUTH_EMULATOR_HOST / FIRESTORE_EMULATOR_HOST
    initializeApp({ projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? 'chat-vote-dev' });
  }
}
const db = getFirestore();

async function main() {
  console.log('🔍 Fetching existing RAGFlow datasets...');
  const existing = await listDatasets();
  if (existing.length === 0 && !process.env.RAGFLOW_API_KEY) {
    console.error('❌ RAGFLOW_API_KEY is not set. Get it from RAGFlow UI → Settings → API Keys (http://localhost:8680)');
    process.exit(1);
  }
  const existingNames = new Set(existing.map((d) => d.name));
  console.log(`   Found ${existing.length} existing datasets: ${[...existingNames].join(', ') || '(none)'}`);

  // ── Fetch party IDs from Firestore ─────────────────────────────────────────
  console.log('🔍 Fetching parties from Firestore...');
  const partiesSnap = await db.collection('parties').get();
  const parties = partiesSnap.docs.map((doc) => ({
    id: doc.id,
    name: (doc.data().name as string) ?? doc.id,
  }));
  console.log(`   Found ${parties.length} parties`);

  // ── Create datasets ────────────────────────────────────────────────────────
  let created = 0;

  // Global datasets
  for (const { name, method } of [
    { name: 'all-manifestos', method: 'laws' },
    { name: 'candidates-websites', method: 'naive' },
  ]) {
    if (existingNames.has(name)) {
      console.log(`   ⏭️  "${name}" already exists — skipping`);
    } else {
      const result = await createDataset(name, method, 'French');
      if (result) created++;
    }
  }

  // Per-party datasets
  for (const party of parties) {
    const dsName = `manifesto-${party.id}`;
    if (existingNames.has(dsName)) {
      console.log(`   ⏭️  "${dsName}" already exists — skipping`);
    } else {
      const result = await createDataset(dsName, 'laws', 'French');
      if (result) created++;
    }
  }

  console.log(`\n✅ Done. Created ${created} new dataset(s). Upload documents via RAGFlow UI at http://localhost:8680`);
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
