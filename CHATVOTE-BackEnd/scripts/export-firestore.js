#!/usr/bin/env node

/**
 * Export production Firestore collections to JSON seed files.
 *
 * Reads from production (or dev) Firestore and writes JSON files
 * compatible with the existing seed_local.py / import-firestore.js workflow.
 *
 * Usage:
 *   node scripts/export-firestore.js                    # Export all collections from prod
 *   node scripts/export-firestore.js --env dev          # Export from dev project
 *   node scripts/export-firestore.js --collections parties,candidates  # Export specific collections
 *   node scripts/export-firestore.js --max-depth 3      # Include subcollections up to depth 3
 *
 * Prerequisites:
 *   - Service account key at CHATVOTE-BackEnd/chat-vote-firebase-adminsdk.json (prod)
 *     or chat-vote-dev-firebase-adminsdk-*.json (dev)
 *   - npm install in scripts/ directory
 */

const admin = require('firebase-admin');
const fs = require('fs');
const path = require('path');

// --- Argument parsing ---
const args = process.argv.slice(2);
function getArg(name, defaultValue) {
  const idx = args.indexOf(`--${name}`);
  if (idx === -1 || idx + 1 >= args.length) return defaultValue;
  return args[idx + 1];
}

const env = getArg('env', 'prod');
const maxDepth = parseInt(getArg('max-depth', '2'), 10);
const collectionsArg = getArg('collections', null);

// Collections to export (default: all known seed collections)
const DEFAULT_COLLECTIONS = [
  'parties',
  'candidates',
  'election_types',
  'proposed_questions',
  'municipalities',
  'system_status',
  'chat_sessions',
  'cached_answers',
  'feedback',
];

const collectionsToExport = collectionsArg
  ? collectionsArg.split(',').map(s => s.trim())
  : DEFAULT_COLLECTIONS;

const OUTPUT_DIR = path.join(__dirname, '..', 'firebase', 'firestore_data', 'dev');

// --- Firebase init ---
function findCredentials() {
  const projectRoot = path.join(__dirname, '..');
  const patterns = env === 'prod'
    ? ['chat-vote-firebase-adminsdk.json']
    : ['chat-vote-dev-firebase-adminsdk'];

  const files = fs.readdirSync(projectRoot);
  for (const pattern of patterns) {
    const match = files.find(f => f.includes(pattern) && f.endsWith('.json'));
    if (match) return path.join(projectRoot, match);
  }

  // Also check scripts/ dir
  const scriptFiles = fs.readdirSync(__dirname);
  for (const pattern of patterns) {
    const match = scriptFiles.find(f => f.includes(pattern) && f.endsWith('.json'));
    if (match) return path.join(__dirname, match);
  }

  return null;
}

const credPath = findCredentials();
if (!credPath) {
  console.error(`❌ No Firebase credentials found for env="${env}".`);
  console.error(`   Expected: chat-vote-firebase-adminsdk.json (prod) or chat-vote-dev-firebase-adminsdk-*.json (dev)`);
  console.error(`   Place it in: ${path.join(__dirname, '..')}`);
  process.exit(1);
}

console.log(`🔑 Using credentials: ${path.basename(credPath)}`);
console.log(`🌍 Environment: ${env}`);

const serviceAccount = require(path.resolve(credPath));
admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
});

const db = admin.firestore();

// --- Export logic ---

/**
 * Recursively export a collection using pagination to handle large datasets.
 */
async function exportCollection(collectionRef, depth = 0) {
  const result = {};
  const PAGE_SIZE = 500;
  let lastDoc = null;
  let page = 0;

  while (true) {
    let query = collectionRef.limit(PAGE_SIZE);
    if (lastDoc) {
      query = query.startAfter(lastDoc);
    }

    const snapshot = await query.get();
    if (snapshot.empty) break;

    page++;
    for (const doc of snapshot.docs) {
      const data = doc.data();
      convertTimestamps(data);
      result[doc.id] = data;

      // Export subcollections if within depth limit
      if (depth < maxDepth) {
        const subcollections = await doc.ref.listCollections();
        for (const subcol of subcollections) {
          const subDocs = await exportCollection(subcol, depth + 1);
          for (const [subDocId, subDocData] of Object.entries(subDocs)) {
            const fullPath = `${doc.id}/${subcol.id}/${subDocId}`;
            result[fullPath] = subDocData;
          }
        }
      }
    }

    const total = Object.keys(result).length;
    process.stdout.write(`\r  📂 ${collectionRef.id}... ${total} docs (page ${page})`);

    lastDoc = snapshot.docs[snapshot.docs.length - 1];
    if (snapshot.docs.length < PAGE_SIZE) break;
  }

  return result;
}

/**
 * Convert Firestore Timestamp objects to ISO strings in-place.
 */
function convertTimestamps(obj) {
  if (!obj || typeof obj !== 'object') return;

  for (const [key, value] of Object.entries(obj)) {
    if (value && typeof value === 'object') {
      if (typeof value.toDate === 'function') {
        // Firestore Timestamp
        obj[key] = value.toDate().toISOString();
      } else if (value._seconds !== undefined && value._nanoseconds !== undefined) {
        // Serialized Timestamp
        obj[key] = new Date(value._seconds * 1000).toISOString();
      } else if (Array.isArray(value)) {
        value.forEach(item => convertTimestamps(item));
      } else {
        convertTimestamps(value);
      }
    }
  }
}

async function main() {
  // Ensure output directory exists
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  console.log(`\n📦 Exporting ${collectionsToExport.length} collections to ${OUTPUT_DIR}\n`);

  let totalDocs = 0;

  for (const collectionName of collectionsToExport) {
    process.stdout.write(`  📂 ${collectionName}...`);

    try {
      let collectionRef = db.collection(collectionName);

      const data = await exportCollection(collectionRef);
      const docCount = Object.keys(data).length;

      if (docCount === 0) {
        console.log(` (empty, skipped)`);
        continue;
      }

      const outputPath = path.join(OUTPUT_DIR, `${collectionName}.json`);
      fs.writeFileSync(outputPath, JSON.stringify(data, null, 2), 'utf8');

      console.log(` ✅ ${docCount} documents`);
      totalDocs += docCount;
    } catch (err) {
      console.log(` ❌ Error: ${err.message}`);
    }
  }

  console.log(`\n🎉 Export complete: ${totalDocs} total documents`);
  console.log(`📁 Files saved to: ${OUTPUT_DIR}`);
  console.log(`\nTo seed locally: poetry run python scripts/seed_local.py`);
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error('❌ Fatal error:', err);
    process.exit(1);
  });
