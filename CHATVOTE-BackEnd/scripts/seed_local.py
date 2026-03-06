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

# Load .env first so its values take priority over defaults below
from dotenv import load_dotenv
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)

# Force local environment before importing any src modules
os.environ.setdefault("ENV", "local")
os.environ.setdefault("API_NAME", "chatvote-api")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
# Model defaults — see src/model_config.py for the central registry
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "qwen3:32b")
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
    # Use the same embedding provider logic as the app
    from src.vector_store_helper import _get_embeddings as get_embeddings
    _, embed_dim = get_embeddings()
    logger.info(f"Embedding dimension: {embed_dim}")

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


def seed_crawled_vectors():
    """
    Read crawled markdown from crawled_content/, chunk, embed, and index
    into Qdrant collections matching the production metadata format.

    Supports Ollama (local) or Scaleway (cloud) embeddings.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct
    import re
    import uuid

    crawled_dir = FIREBASE_DATA_DIR / "crawled_content"
    if not crawled_dir.exists():
        logger.warning("No crawled_content/ directory found, skipping vector seeding")
        return

    qdrant_url = os.environ["QDRANT_URL"]

    # Use the same embedding provider as the app (Google, Scaleway, OpenAI, or Ollama)
    from src.vector_store_helper import _get_embeddings as get_embeddings
    embeddings, embed_dim = get_embeddings()
    logger.info(f"Embedding provider ready ({embed_dim}d)")

    client = QdrantClient(url=qdrant_url)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""],
    )

    # Load party names for metadata
    parties_path = FIREBASE_DATA_DIR / "parties.json"
    party_names = {}
    if parties_path.exists():
        parties_data = json.loads(parties_path.read_text(encoding="utf-8"))
        for pid, p in parties_data.items():
            if not pid.startswith("_"):
                party_names[pid] = p.get("name", pid)

    # Load candidate data for metadata
    candidates_path = FIREBASE_DATA_DIR / "candidates.json"
    candidate_data = {}
    if candidates_path.exists():
        cand_raw = json.loads(candidates_path.read_text(encoding="utf-8"))
        for cid, c in cand_raw.items():
            if not cid.startswith("_"):
                candidate_data[cid] = c

    def _extract_source_url(md_text: str) -> str:
        """Extract source URL from crawler-ingest markdown format."""
        match = re.search(r"^> Source: (.+)$", md_text, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _embed_and_collect(
        md_files: list[Path],
        namespace: str,
        chunk_metadata_factory,  # callable(chunk_index, source_url, page_title) -> ChunkMetadata
    ) -> list[PointStruct]:
        """Read markdown files, chunk, embed, and return Qdrant points."""
        points = []
        chunk_index = 0
        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            if len(content.strip()) < 50:
                continue

            source_url = _extract_source_url(content)
            chunks = text_splitter.split_text(content)

            for i, chunk in enumerate(chunks):
                vector = embeddings.embed_query(chunk)
                cm = chunk_metadata_factory(chunk_index, source_url, md_file.stem)
                metadata = cm.to_qdrant_payload()
                metadata["total_chunks"] = len(chunks)
                points.append(
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector={"dense": vector},
                        payload={
                            "page_content": chunk,
                            "metadata": metadata,
                        },
                    )
                )
                chunk_index += 1
        return points

    # --- Seed party crawled content ---
    parties_dir = crawled_dir / "parties"
    if parties_dir.exists():
        for party_dir in sorted(parties_dir.iterdir()):
            if not party_dir.is_dir():
                continue
            party_id = party_dir.name
            party_name = party_names.get(party_id, party_id)
            # Markdown files live in markdown/ subdirectory (from crawler output)
            md_dir = party_dir / "markdown"
            md_files = sorted(md_dir.glob("*.md")) if md_dir.exists() else sorted(party_dir.glob("*.md"))
            if not md_files:
                continue

            logger.info(f"  Indexing {len(md_files)} pages for party '{party_name}'...")
            from src.models.chunk_metadata import ChunkMetadata

            def party_metadata_factory(idx, url, title):
                return ChunkMetadata(
                    namespace=party_id,
                    source_document="party_website",
                    party_ids=[party_id],
                    party_name=party_name,
                    document_name=f"{party_name} - Site web",
                    url=url,
                    page_title=title,
                    page=idx + 1,
                    chunk_index=idx,
                )

            points = _embed_and_collect(
                md_files,
                namespace=party_id,
                chunk_metadata_factory=party_metadata_factory,
            )
            if points:
                # Upsert in batches of 50
                for i in range(0, len(points), 50):
                    client.upsert(
                        collection_name="all_parties_dev",
                        points=points[i : i + 50],
                    )
                logger.info(f"    Indexed {len(points)} chunks into 'all_parties_dev'")

    # --- Seed candidate crawled content ---
    candidates_dir = crawled_dir / "candidates"
    if candidates_dir.exists():
        for cand_dir in sorted(candidates_dir.iterdir()):
            if not cand_dir.is_dir():
                continue
            candidate_id = cand_dir.name
            cand_info = candidate_data.get(candidate_id, {})
            cand_name = cand_info.get("full_name", candidate_id)
            municipality_code = cand_info.get("municipality_code", "")
            municipality_name = cand_info.get("municipality_name", "")
            party_ids = cand_info.get("party_ids", [])
            party_ids_str = ",".join(party_ids) if isinstance(party_ids, list) else str(party_ids)

            # Markdown files live in markdown/ subdirectory (from crawler output)
            md_dir = cand_dir / "markdown"
            md_files = sorted(md_dir.glob("*.md")) if md_dir.exists() else sorted(cand_dir.glob("*.md"))
            if not md_files:
                continue

            logger.info(f"  Indexing {len(md_files)} pages for candidate '{cand_name}'...")

            def candidate_metadata_factory(idx, url, title):
                return ChunkMetadata(
                    namespace=candidate_id,
                    source_document="candidate_website",
                    party_ids=party_ids if isinstance(party_ids, list) else [],
                    candidate_ids=[candidate_id],
                    candidate_name=cand_name,
                    municipality_code=municipality_code,
                    municipality_name=municipality_name,
                    document_name=f"{cand_name} - Site web",
                    url=url,
                    page_title=title,
                    page=idx + 1,
                    chunk_index=idx,
                )

            points = _embed_and_collect(
                md_files,
                namespace=candidate_id,
                chunk_metadata_factory=candidate_metadata_factory,
            )
            if points:
                for i in range(0, len(points), 50):
                    client.upsert(
                        collection_name="candidates_websites_dev",
                        points=points[i : i + 50],
                    )
                logger.info(f"    Indexed {len(points)} chunks into 'candidates_websites_dev'")

    logger.info("Crawled content vector seeding complete.")


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

    # Step 3 (optional): Seed vectors from crawled content
    if args.with_vectors:
        logger.info("\n--- Seeding Crawled Content Vectors ---")
        seed_crawled_vectors()

    logger.info("\n=== Seeding complete! ===")


if __name__ == "__main__":
    main()
