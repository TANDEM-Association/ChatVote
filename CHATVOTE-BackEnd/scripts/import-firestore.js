#!/usr/bin/env node

/**
 * Script pour importer des données JSON dans Firestore
 *
 * Usage:
 *   node scripts/import-firestore.js <collection> <json-file> [credentials-file] [--clean]
 *
 * Options:
 *   --clean    Supprime tous les documents existants avant d'importer
 *
 * Exemples:
 *   node scripts/import-firestore.js parties firebase/firestore_data/dev/parties.json
 *   node scripts/import-firestore.js parties firebase/firestore_data/dev/parties.json --clean
 */

const admin = require('firebase-admin');
const fs = require('fs');
const path = require('path');

// Parse arguments
const args = process.argv.slice(2);
const cleanFlag = args.includes('--clean');
const filteredArgs = args.filter(a => a !== '--clean');

if (filteredArgs.length < 2) {
  console.error('Usage: node scripts/import-firestore.js <collection> <json-file> [credentials-file] [--clean]');
  console.error('');
  console.error('Options:');
  console.error('  --clean    Delete all existing documents before importing');
  console.error('');
  console.error('Examples:');
  console.error('  node scripts/import-firestore.js parties firebase/firestore_data/dev/parties.json');
  console.error('  node scripts/import-firestore.js parties firebase/firestore_data/dev/parties.json --clean');
  process.exit(1);
}

const collectionName = filteredArgs[0];
const jsonFile = filteredArgs[1];

function findCredentialsFile() {
  if (filteredArgs[2]) return filteredArgs[2];

  // Directories to search for credentials (current dir, parent dir, project root)
  const searchDirs = ['.', '..', path.join(__dirname, '..')];

  for (const dir of searchDirs) {
    try {
      const files = fs.readdirSync(dir);
      const credFile = files.find(f => f.includes('firebase-adminsdk') && f.endsWith('.json'));
      if (credFile) {
        return path.join(dir, credFile);
      }
    } catch {
      // Directory doesn't exist or can't be read, skip
    }
  }

  console.error('Error: No Firebase credentials file found. Please specify one.');
  console.error('Searched in: current directory, parent directory, and project root.');
  process.exit(1);
}

// Validate files exist
if (!fs.existsSync(jsonFile)) {
  console.error(`Error: JSON file not found: ${jsonFile}`);
  process.exit(1);
}

// Initialize Firebase Admin
const useEmulator = process.env.FIRESTORE_EMULATOR_HOST;

if (useEmulator) {
  admin.initializeApp({ projectId: 'chat-vote-dev' });
  console.log(`Using Firestore emulator at ${useEmulator}`);
} else {
  const credentialsFile = findCredentialsFile();

  if (!fs.existsSync(credentialsFile)) {
    console.error(`Error: Credentials file not found: ${credentialsFile}`);
    process.exit(1);
  }

  const serviceAccount = require(path.resolve(credentialsFile));
  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
  });
}

const db = admin.firestore();

const BATCH_SIZE = 400; // Firestore limit is 500, use 400 to be safe

async function deleteCollection(collectionRef) {
  let totalDeleted = 0;
  let batchNum = 0;

  while (true) {
    // Get documents in batches of BATCH_SIZE
    const snapshot = await collectionRef.limit(BATCH_SIZE).get();

    if (snapshot.empty) {
      if (batchNum === 0) {
        console.log('  📭 Collection is empty, nothing to delete');
      }
      break;
    }

    const batch = db.batch();
    snapshot.docs.forEach((doc) => {
      batch.delete(doc.ref);
    });

    await batch.commit();
    totalDeleted += snapshot.docs.length;
    batchNum++;
    console.log(`  🗑️  Deleted batch ${batchNum} (${snapshot.docs.length} docs) - Total: ${totalDeleted}`);
  }

  return totalDeleted;
}

async function importData() {
  console.log(`📂 Reading ${jsonFile}...`);
  const data = JSON.parse(fs.readFileSync(jsonFile, 'utf8'));

  // Clean collection if --clean flag is set
  if (cleanFlag) {
    console.log(`\n🧹 Cleaning collection "${collectionName}"...`);
    const deletedCount = await deleteCollection(db.collection(collectionName));
    console.log(`  Deleted ${deletedCount} documents\n`);
  }

  const entries = Object.entries(data).filter(([docId]) => !docId.startsWith('_'));
  const totalDocs = entries.length;
  const totalBatches = Math.ceil(totalDocs / BATCH_SIZE);

  console.log(`📤 Importing ${totalDocs} documents to collection "${collectionName}" in ${totalBatches} batches...`);

  let totalCount = 0;

  for (let batchIndex = 0; batchIndex < totalBatches; batchIndex++) {
    const batch = db.batch();
    const start = batchIndex * BATCH_SIZE;
    const end = Math.min(start + BATCH_SIZE, totalDocs);
    const batchEntries = entries.slice(start, end);

    for (const [docId, docData] of batchEntries) {
      const docRef = db.collection(collectionName).doc(docId);
      batch.set(docRef, docData, { merge: false });
      totalCount++;
    }

    await batch.commit();
    const progress = ((batchIndex + 1) / totalBatches * 100).toFixed(1);
    console.log(`  📦 Batch ${batchIndex + 1}/${totalBatches} committed (${batchEntries.length} docs) - ${progress}%`);
  }

  console.log(`\n🎉 Successfully imported ${totalCount} documents to "${collectionName}"`);
}

importData()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error('❌ Error importing data:', error);
    process.exit(1);
  });
