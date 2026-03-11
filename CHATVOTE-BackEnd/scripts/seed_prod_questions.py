"""Seed proposed_questions into prod Firestore.

Usage:
    ENV=prod poetry run python scripts/seed_prod_questions.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils import load_env

_target_env = os.getenv("ENV")
load_env()
if _target_env:
    os.environ["ENV"] = _target_env

from src.firebase_service import db

COLLECTION = "proposed_questions"
JSON_FILE = Path(__file__).parent.parent / "firebase" / "firestore_data" / "dev" / "proposed_questions.json"


def seed():
    data = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    entries = {k: v for k, v in data.items() if not k.startswith("_") and k != "metadata"}

    batch = db.batch()
    count = 0

    for doc_id, doc_data in entries.items():
        path = doc_id
        if path.startswith(COLLECTION + "/"):
            path = path[len(COLLECTION) + 1:]

        parts = path.split("/")
        if len(parts) == 1:
            ref = db.collection(COLLECTION).document(parts[0])
        elif len(parts) % 2 == 0:
            ref = db.collection(COLLECTION)
            for i in range(0, len(parts) - 1, 2):
                ref = ref.document(parts[i]).collection(parts[i + 1])
            ref = ref.document(parts[-1])
        else:
            ref = db.collection(COLLECTION).document(parts[0])
            for i in range(1, len(parts), 2):
                ref = ref.collection(parts[i]).document(parts[i + 1])

        batch.set(ref, doc_data)
        count += 1

        if count % 400 == 0:
            batch.commit()
            batch = db.batch()

    batch.commit()
    print(f"Seeded {count} documents into '{COLLECTION}'")


if __name__ == "__main__":
    env = os.getenv("ENV", "dev")
    print(f"Seeding proposed_questions into Firestore (ENV={env})")
    if env == "prod":
        print("WARNING: Writing to PRODUCTION Firestore!")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            sys.exit(0)
    seed()
