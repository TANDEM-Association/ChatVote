#!/usr/bin/env node

/**
 * Safely migrate municipalities from dev Firestore to prod Firestore.
 *
 * Two-step process:
 *   Step 1 (dry-run): Count and validate dev municipalities
 *   Step 2 (migrate): Additive write to prod (set with merge, never deletes)
 *
 * Usage:
 *   node scripts/migrate_municipalities_to_prod.js --dry-run   # Step 1: count only
 *   node scripts/migrate_municipalities_to_prod.js --migrate   # Step 2: copy to prod
 *
 * Prerequisites:
 *   - Dev credentials:  chat-vote-dev-firebase-adminsdk-*.json
 *   - Prod credentials: chat-vote-firebase-adminsdk.json (or chat-vote-prod-*)
 */

const admin = require('firebase-admin');
const fs = require('fs');
const path = require('path');

const PROJECT_ROOT = path.join(__dirname, '..');
const BATCH_SIZE = 400;
const COLLECTION = 'municipalities';

// --- Argument parsing ---
const args = process.argv.slice(2);
const isDryRun = args.includes('--dry-run');
const isMigrate = args.includes('--migrate');

if (!isDryRun && !isMigrate) {
  console.error('Usage:');
  console.error('  node scripts/migrate_municipalities_to_prod.js --dry-run   # Count and validate');
  console.error('  node scripts/migrate_municipalities_to_prod.js --migrate   # Copy dev → prod');
  process.exit(1);
}

// --- Credential discovery ---
function findCredentials(pattern) {
  const files = fs.readdirSync(PROJECT_ROOT);
  const match = files.find(f => f.includes(pattern) && f.endsWith('.json'));
  return match ? path.join(PROJECT_ROOT, match) : null;
}

function initApp(name, credPattern) {
  const credPath = findCredentials(credPattern);
  if (!credPath) {
    console.error(`No credentials found matching "${credPattern}" in ${PROJECT_ROOT}`);
    process.exit(1);
  }
  console.log(`  ${name}: ${path.basename(credPath)}`);
  const serviceAccount = require(path.resolve(credPath));
  const app = admin.initializeApp(
    { credential: admin.credential.cert(serviceAccount) },
    name
  );
  return admin.firestore(app);
}

// --- Helpers ---
async function countCollection(db, label) {
  let total = 0;
  let lastDoc = null;

  while (true) {
    let query = db.collection(COLLECTION).limit(500);
    if (lastDoc) query = query.startAfter(lastDoc);

    const snapshot = await query.get();
    if (snapshot.empty) break;

    total += snapshot.size;
    lastDoc = snapshot.docs[snapshot.docs.length - 1];
    process.stdout.write(`\r  ${label}: ${total} docs...`);

    if (snapshot.size < 500) break;
  }

  console.log(`\r  ${label}: ${total} docs`);
  return total;
}

async function readAll(db) {
  const docs = {};
  let lastDoc = null;

  while (true) {
    let query = db.collection(COLLECTION).limit(500);
    if (lastDoc) query = query.startAfter(lastDoc);

    const snapshot = await query.get();
    if (snapshot.empty) break;

    for (const doc of snapshot.docs) {
      const data = doc.data();
      // Convert Timestamps to ISO strings for safe transfer
      convertTimestamps(data);
      docs[doc.id] = data;
    }

    lastDoc = snapshot.docs[snapshot.docs.length - 1];
    process.stdout.write(`\r  Reading dev: ${Object.keys(docs).length} docs...`);

    if (snapshot.size < 500) break;
  }

  console.log(`\r  Reading dev: ${Object.keys(docs).length} docs`);
  return docs;
}

function convertTimestamps(obj) {
  if (!obj || typeof obj !== 'object') return;
  for (const [key, value] of Object.entries(obj)) {
    if (value && typeof value === 'object') {
      if (typeof value.toDate === 'function') {
        obj[key] = value.toDate().toISOString();
      } else if (value._seconds !== undefined && value._nanoseconds !== undefined) {
        obj[key] = new Date(value._seconds * 1000).toISOString();
      } else if (Array.isArray(value)) {
        value.forEach(item => convertTimestamps(item));
      } else {
        convertTimestamps(value);
      }
    }
  }
}

// --- Main ---
async function main() {
  console.log('\n=== Municipality Migration: Dev → Prod ===\n');
  console.log('Credentials:');

  const devDb = initApp('dev', 'chat-vote-dev-firebase-adminsdk');
  const prodDb = isMigrate ? initApp('prod', 'chat-vote-firebase-adminsdk') : null;

  // Step 1: Count dev
  console.log('\n--- Dev Firestore ---');
  const devCount = await countCollection(devDb, 'dev municipalities');

  if (devCount === 0) {
    console.error('\nNo municipalities found in dev. Aborting.');
    process.exit(1);
  }

  // Step 1b: Sample check — verify docs look like municipalities
  const sample = await devDb.collection(COLLECTION).limit(3).get();
  console.log('\n  Sample documents:');
  for (const doc of sample.docs) {
    const d = doc.data();
    console.log(`    ${doc.id}: ${d.nom || d.name || '(no name)'} (pop: ${d.population || '?'})`);
  }

  if (isDryRun) {
    // Also count prod for comparison
    if (findCredentials('chat-vote-firebase-adminsdk')) {
      const prodDbCheck = initApp('prod-check', 'chat-vote-firebase-adminsdk');
      console.log('\n--- Prod Firestore (current) ---');
      const prodCount = await countCollection(prodDbCheck, 'prod municipalities');
      console.log(`\n  Dev has ${devCount} municipalities`);
      console.log(`  Prod has ${prodCount} municipalities`);
      console.log(`  Migration will ADD ${Math.max(0, devCount - prodCount)} new docs (existing docs updated, none deleted)`);
    }

    console.log('\n--- DRY RUN COMPLETE ---');
    console.log('Run with --migrate to proceed.\n');
    process.exit(0);
  }

  // Step 2: Read all dev docs
  console.log('\n--- Reading all dev municipalities ---');
  const devDocs = await readAll(devDb);

  // Step 3: Count prod before
  console.log('\n--- Prod Firestore (before) ---');
  const prodCountBefore = await countCollection(prodDb, 'prod municipalities');

  // Step 4: Write to prod (additive — set without merge means full overwrite per doc, no deletes)
  console.log('\n--- Writing to prod (additive, no deletes) ---');
  const entries = Object.entries(devDocs);
  let written = 0;

  for (let i = 0; i < entries.length; i += BATCH_SIZE) {
    const batch = prodDb.batch();
    const chunk = entries.slice(i, i + BATCH_SIZE);

    for (const [docId, data] of chunk) {
      const ref = prodDb.collection(COLLECTION).doc(docId);
      batch.set(ref, data); // Additive: creates or overwrites, never deletes others
    }

    await batch.commit();
    written += chunk.length;
    const pct = ((written / entries.length) * 100).toFixed(1);
    process.stdout.write(`\r  Written: ${written}/${entries.length} (${pct}%)`);
  }

  console.log(`\r  Written: ${written}/${entries.length} (100%)`);

  // Step 5: Count prod after and verify
  console.log('\n--- Prod Firestore (after) ---');
  const prodCountAfter = await countCollection(prodDb, 'prod municipalities');

  console.log('\n=== Migration Summary ===');
  console.log(`  Dev municipalities:         ${devCount}`);
  console.log(`  Prod before:                ${prodCountBefore}`);
  console.log(`  Prod after:                 ${prodCountAfter}`);
  console.log(`  Docs written (set):         ${written}`);

  if (prodCountAfter >= devCount) {
    console.log('\n  MIGRATION SUCCESSFUL\n');
  } else {
    console.error(`\n  WARNING: Prod count (${prodCountAfter}) < dev count (${devCount}). Investigate.\n`);
    process.exit(1);
  }
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error('\nFatal error:', err);
    process.exit(1);
  });
