#!/usr/bin/env python3
"""
Export current Firestore emulator data to seed JSON files.

Reads all documents from the emulator and writes them to
firebase/firestore_data/dev/*.json in the same format seed_local.py expects.

Usage:
    poetry run python scripts/export_emulator_to_seed.py
"""

import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)

os.environ.setdefault("ENV", "local")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")

import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1.base_document import DocumentSnapshot

FIREBASE_DATA_DIR = PROJECT_ROOT / "firebase" / "firestore_data" / "dev"

# Collections to export — same as seed_local.py
COLLECTIONS_TO_EXPORT = [
    "parties",
    "candidates",
    "election_types",
    "proposed_questions",
    "municipalities",
    "electoral_lists",
    "system_status",
]

# Known subcollections to recurse into
KNOWN_SUBCOLLECTIONS = {
    "proposed_questions": ["questions"],
    "chat_sessions": ["messages"],
}


def convert_value(val):
    """Convert Firestore types to JSON-serializable types."""
    from google.cloud.firestore_v1 import DocumentReference
    from google.protobuf.timestamp_pb2 import Timestamp
    import datetime

    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, datetime.datetime):
        return val.isoformat()
    if isinstance(val, dict):
        return {k: convert_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return [convert_value(v) for v in val]
    if isinstance(val, DocumentReference):
        return val.path
    return str(val)


def export_collection(db, collection_name: str) -> dict:
    """Export a collection (and known subcollections) to a dict."""
    result = {}

    docs = list(db.collection(collection_name).stream())
    logger.info(f"  Found {len(docs)} top-level docs in '{collection_name}'")

    for doc in docs:
        data = convert_value(doc.to_dict())
        result[doc.id] = data

        # Check for known subcollections
        subcols = KNOWN_SUBCOLLECTIONS.get(collection_name, [])
        for subcol_name in subcols:
            subdocs = list(doc.reference.collection(subcol_name).stream())
            for subdoc in subdocs:
                key = f"{doc.id}/{subcol_name}/{subdoc.id}"
                result[key] = convert_value(subdoc.to_dict())
            if subdocs:
                logger.info(f"    Found {len(subdocs)} docs in '{doc.id}/{subcol_name}'")

    return result


def main():
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": "chat-vote-dev"})

    db = firestore.client()
    FIREBASE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for collection_name in COLLECTIONS_TO_EXPORT:
        logger.info(f"Exporting '{collection_name}'...")
        data = export_collection(db, collection_name)

        if not data:
            logger.warning(f"  No data found for '{collection_name}', skipping")
            continue

        out_path = FIREBASE_DATA_DIR / f"{collection_name}.json"
        out_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info(f"  Wrote {len(data)} entries to {out_path.name}")

    logger.info("Export complete!")


if __name__ == "__main__":
    main()
