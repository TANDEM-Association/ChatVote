#!/usr/bin/env python3
"""
Seed script for local development.

Seeds Firestore emulator with dev data and creates Qdrant collections.
Optionally generates sample embeddings via Ollama for basic RAG testing.

Usage:
    poetry run python scripts/seed_local.py              # Seed Firestore + create Qdrant collections
    poetry run python scripts/seed_local.py --with-vectors  # Also generate sample embeddings
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path so we can import from src
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Force local environment before importing any src modules
os.environ.setdefault("ENV", "local")
os.environ.setdefault("API_NAME", "chatvote-api")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "llama3.2")
os.environ.setdefault("OLLAMA_EMBED_MODEL", "nomic-embed-text")
os.environ.setdefault("OLLAMA_EMBED_DIM", "768")

FIREBASE_DATA_DIR = PROJECT_ROOT / "firebase" / "firestore_data" / "dev"

# Collections to seed and their JSON files
FIRESTORE_COLLECTIONS = {
    "parties": "parties.json",
    "candidates": "candidates.json",
    "election_types": "election_types.json",
    "proposed_questions": "proposed_questions.json",
    "municipalities": "municipalities.json",
    "system_status": "system_status.json",
}


def wait_for_emulator(host: str, timeout: int = 30) -> bool:
    """Return True if the Firestore emulator is reachable within timeout seconds."""
    import socket
    import time

    host_part, _, port_part = host.partition(":")
    port = int(port_part) if port_part else 8081
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host_part, port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def seed_firestore():
    """Seed Firestore emulator with data from JSON files."""
    import firebase_admin
    from firebase_admin import firestore

    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST", "localhost:8081")
    if not wait_for_emulator(emulator_host):
        raise RuntimeError(
            f"Firestore emulator not reachable at {emulator_host}. "
            "Run 'make dev-infra' first."
        )

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": "chat-vote-dev"})

    db = firestore.client()

    for collection_name, json_filename in FIRESTORE_COLLECTIONS.items():
        json_path = FIREBASE_DATA_DIR / json_filename
        if not json_path.exists():
            logger.warning(f"Skipping {collection_name}: {json_path} not found")
            continue

        logger.info(f"Seeding '{collection_name}' from {json_filename}...")
        data = json.loads(json_path.read_text(encoding="utf-8"))

        # Filter out metadata keys (starting with _)
        entries = {k: v for k, v in data.items() if not k.startswith("_")}

        count = 0
        batch = db.batch()
        for doc_id, doc_data in entries.items():
            # Handle nested Firestore paths (e.g. "proposed_questions/chat-vote/questions/q1")
            # Strip the collection prefix if present, then use the remaining path segments
            path = doc_id
            if path.startswith(collection_name + "/"):
                path = path[len(collection_name) + 1:]

            parts = path.split("/")
            if len(parts) == 1:
                # Simple doc ID
                ref = db.collection(collection_name).document(parts[0])
            elif len(parts) % 2 == 0:
                # Even segments: subcollection path (doc/subcol/doc/...)
                ref = db.collection(collection_name)
                for i in range(0, len(parts) - 1, 2):
                    ref = ref.document(parts[i]).collection(parts[i + 1])
                ref = ref.document(parts[-1])
            else:
                # Odd segments: ends at a document (doc/subcol/doc)
                ref = db.collection(collection_name).document(parts[0])
                for i in range(1, len(parts), 2):
                    ref = ref.collection(parts[i]).document(parts[i + 1])

            batch.set(ref, doc_data)
            count += 1

            # Firestore batch limit is 500
            if count % 400 == 0:
                batch.commit()
                batch = db.batch()

        batch.commit()
        logger.info(f"  Seeded {count} documents into '{collection_name}'")

    logger.info("Firestore seeding complete.")


def create_qdrant_collections():
    """Create the 4 Qdrant dev collections with correct dimensions."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance

    qdrant_url = os.environ["QDRANT_URL"]
    embed_dim = int(os.environ.get("OLLAMA_EMBED_DIM", "768"))

    logger.info(f"Connecting to Qdrant at {qdrant_url}...")
    client = QdrantClient(url=qdrant_url, check_compatibility=False)

    # Use _dev suffix for local (same as ENV=local falls through to _dev in vector_store_helper.py)
    collection_names = [
        "all_parties_dev",
        "candidates_websites_dev",
        "justified_voting_behavior_dev",
        "parliamentary_questions_dev",
    ]

    for name in collection_names:
        try:
            existing = client.get_collections().collections
            exists = any(c.name == name for c in existing)

            if exists:
                # Check dimensions match
                info = client.get_collection(name)
                vectors_config = info.config.params.vectors
                existing_dim = None
                if isinstance(vectors_config, dict) and "dense" in vectors_config:
                    existing_dim = vectors_config["dense"].size
                elif hasattr(vectors_config, "size"):
                    existing_dim = vectors_config.size

                if existing_dim == embed_dim:
                    logger.info(f"  Collection '{name}' already exists with {embed_dim}d - skipping")
                    continue
                else:
                    logger.warning(
                        f"  Collection '{name}' has {existing_dim}d but expected {embed_dim}d - recreating"
                    )
                    client.delete_collection(name)

            client.create_collection(
                collection_name=name,
                vectors_config={
                    "dense": VectorParams(size=embed_dim, distance=Distance.COSINE)
                },
            )
            logger.info(f"  Created collection '{name}' ({embed_dim}d)")

        except Exception as e:
            logger.error(f"  Error with collection '{name}': {e}")
            raise

    logger.info("Qdrant collections ready.")


def seed_sample_vectors():
    """Generate sample embeddings from party descriptions and index into Qdrant."""
    from langchain_ollama import OllamaEmbeddings
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct
    import uuid

    parties_path = FIREBASE_DATA_DIR / "parties.json"
    if not parties_path.exists():
        logger.warning("No parties.json found, skipping vector seeding")
        return

    qdrant_url = os.environ["QDRANT_URL"]
    ollama_base_url = os.environ["OLLAMA_BASE_URL"]
    embed_model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    logger.info(f"Generating embeddings via Ollama ({embed_model})...")

    embeddings = OllamaEmbeddings(model=embed_model, base_url=ollama_base_url)
    client = QdrantClient(url=qdrant_url)

    parties_data = json.loads(parties_path.read_text(encoding="utf-8"))
    entries = {k: v for k, v in parties_data.items() if not k.startswith("_")}

    points = []
    for party_id, party in entries.items():
        description = party.get("description", "")
        name = party.get("name", "")
        long_name = party.get("long_name", "")

        text = f"{name} ({long_name}): {description}"
        if not text.strip() or text.strip() == "():":
            continue

        logger.info(f"  Embedding party '{name}'...")
        vector = embeddings.embed_query(text)

        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector={"dense": vector},
                payload={
                    "page_content": text,
                    "metadata": {
                        "namespace": party_id,
                        "document_name": f"{name} - Description",
                        "document_publish_date": "2024",
                    },
                },
            )
        )

    if points:
        client.upsert(collection_name="all_parties_dev", points=points)
        logger.info(f"  Indexed {len(points)} party descriptions into 'all_parties_dev'")
    else:
        logger.warning("  No party descriptions to index")

    logger.info("Sample vector seeding complete.")


def main():
    parser = argparse.ArgumentParser(description="Seed local dev environment")
    parser.add_argument(
        "--with-vectors",
        action="store_true",
        help="Also generate sample embeddings via Ollama",
    )
    args = parser.parse_args()

    logger.info("=== ChatVote Local Dev Seeder ===")
    logger.info(f"Firestore emulator: {os.environ.get('FIRESTORE_EMULATOR_HOST')}")
    logger.info(f"Qdrant: {os.environ.get('QDRANT_URL')}")

    # Step 1: Seed Firestore
    logger.info("\n--- Seeding Firestore ---")
    seed_firestore()

    # Step 2: Create Qdrant collections
    logger.info("\n--- Creating Qdrant Collections ---")
    create_qdrant_collections()

    # Step 3 (optional): Seed sample vectors
    if args.with_vectors:
        logger.info("\n--- Seeding Sample Vectors ---")
        seed_sample_vectors()

    logger.info("\n=== Seeding complete! ===")


if __name__ == "__main__":
    main()
