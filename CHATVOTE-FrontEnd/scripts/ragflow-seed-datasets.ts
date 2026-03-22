#!/usr/bin/env npx tsx
/**
 * Seed RAGFlow datasets with Knowledge Graph configuration.
 *
 * Creates datasets with GraphRAG enabled (political entity types) and applies
 * parser_config from the versioned knowledge-graph/config.ts presets.
 *
 * Idempotent: creates missing datasets, updates config on existing ones.
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

import { syncDatasets } from '../src/lib/knowledge-graph/setup';
import { POLITICAL_ENTITY_TYPES } from '../src/lib/knowledge-graph/config';
import { listDatasets } from '../src/lib/ai/ragflow-client';
import { initializeApp, cert, getApps } from 'firebase-admin/app';
import { getFirestore } from 'firebase-admin/firestore';

// ── Firebase Admin init ──────────────────────────────────────────────────────
if (getApps().length === 0) {
  const credBase64 = process.env.FIREBASE_CREDENTIALS_BASE64;
  if (credBase64) {
    const cred = JSON.parse(Buffer.from(credBase64, 'base64').toString());
    initializeApp({ credential: cert(cred) });
  } else {
    // Local dev: connect to emulator (same logic as firebase-admin.ts)
    process.env.FIRESTORE_EMULATOR_HOST ??= 'localhost:8081';
    initializeApp({ projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? 'chat-vote-dev' });
  }
}
const db = getFirestore();

async function main() {
  // Verify API key
  const testDs = await listDatasets();
  if (testDs.length === 0 && !process.env.RAGFLOW_API_KEY) {
    console.error('❌ RAGFLOW_API_KEY is not set. Get it from RAGFlow UI → Settings → API Keys (http://localhost:8680)');
    process.exit(1);
  }

  console.log(`📊 Knowledge Graph entity types: ${POLITICAL_ENTITY_TYPES.join(', ')}`);

  // Fetch party IDs from Firestore
  console.log('🔍 Fetching parties from Firestore...');
  const partiesSnap = await db.collection('parties').get();
  const partyIds: string[] = [];
  const partyNames = new Map<string, string>();
  for (const doc of partiesSnap.docs) {
    partyIds.push(doc.id);
    const name = (doc.data().name as string) ?? doc.id;
    partyNames.set(doc.id, name);
  }
  console.log(`   Found ${partyIds.length} parties: ${partyIds.join(', ')}`);

  // Sync datasets with KG config
  const result = await syncDatasets(partyIds, partyNames);

  console.log('\n📋 Results:');
  if (result.created.length) console.log(`   ✅ Created: ${result.created.join(', ')}`);
  if (result.updated.length) console.log(`   🔄 Updated: ${result.updated.join(', ')}`);
  if (result.skipped.length) console.log(`   ⏭️  Skipped: ${result.skipped.join(', ')}`);
  if (result.errors.length) console.log(`   ❌ Errors: ${result.errors.join(', ')}`);

  console.log('\n✅ Done. Upload documents via RAGFlow UI at http://localhost:8680');
  console.log('   GraphRAG will auto-extract political entities during document parsing.');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
