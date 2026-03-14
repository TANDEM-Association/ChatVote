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
from dotenv import load_dotenv  # noqa: E402
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

FIREBASE_DATA_DIR = PROJECT_ROOT / "firebase" / "firestore_data" / "dev"

# Map old crawled-content directory names (national election slugs) to current
# Firestore party_ids (nuance-based IDs used in municipal elections).
# The manifesto_indexer uses party.party_id from Firestore; this mapping keeps
# the seed script consistent so `make seed` doesn't create namespace mismatches.
DIR_TO_PARTY_ID: dict[str, str] = {
    "la-france-insoumise": "lfi",
    "renaissance": "union_centre",
    "place-publique": "ps",
    # These already match:
    # "europe-ecologie-les-verts": "europe-ecologie-les-verts",
    # "reconquete": "reconquete",
}

# Collections to seed and their JSON files
FIRESTORE_COLLECTIONS = {
    "parties": "parties.json",
    "candidates": "candidates.json",
    "election_types": "election_types.json",
    "proposed_questions": "proposed_questions.json",
    "municipalities": "municipalities.json",
    "electoral_lists": "electoral_lists.json",
    "system_status": "system_status.json",
    "chat_sessions": "chat_sessions.json",
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


def _resolve_doc_ref(db, collection_name: str, doc_id: str):
    """Resolve a doc_id (possibly with subcollection path) to a Firestore ref."""
    path = doc_id
    if path.startswith(collection_name + "/"):
        path = path[len(collection_name) + 1:]

    parts = path.split("/")
    if len(parts) == 1:
        return db.collection(collection_name).document(parts[0])
    elif len(parts) % 2 == 0:
        ref = db.collection(collection_name)
        for i in range(0, len(parts) - 1, 2):
            ref = ref.document(parts[i]).collection(parts[i + 1])
        return ref.document(parts[-1])
    else:
        ref = db.collection(collection_name).document(parts[0])
        for i in range(1, len(parts), 2):
            ref = ref.collection(parts[i]).document(parts[i + 1])
        return ref


# Max docs to seed per collection for local dev (keeps emulator fast).
# Small/static collections are unlimited; large data collections are capped.
_COLLECTION_LIMITS: dict[str, int | None] = {
    "parties": None,
    "system_status": None,
    "election_types": None,
    "proposed_questions": None,
    "chat_sessions": None,
    "candidates": 2000,
    "municipalities": 2000,
    "electoral_lists": 2000,
}


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

        # Cap large collections for local dev performance
        limit = _COLLECTION_LIMITS.get(collection_name)
        if limit and len(entries) > limit:
            logger.info(f"  Capping {collection_name} from {len(entries)} to {limit} docs (local dev)")
            entries = dict(list(entries.items())[:limit])

        count = 0
        committed = 0
        batch = db.batch()
        for doc_id, doc_data in entries.items():
            ref = _resolve_doc_ref(db, collection_name, doc_id)
            batch.set(ref, doc_data)
            count += 1

            # Firestore batch limit is 500
            if count % 400 == 0:
                try:
                    batch.commit()
                    committed += 400
                    if committed % 2000 == 0:
                        logger.info(f"  {collection_name}: {committed}/{len(entries)} docs committed...")
                except Exception as e:
                    logger.error(f"  Batch commit failed at {count} docs: {e}")
                batch = db.batch()

        # Commit remaining docs
        remaining = count - committed
        if remaining > 0:
            try:
                batch.commit()
                committed += remaining
            except Exception as e:
                logger.error(f"  Final batch commit failed ({remaining} docs): {e}")

        logger.info(f"  Seeded {committed}/{count} documents into '{collection_name}'")

    logger.info("Firestore seeding complete.")


def create_qdrant_collections():
    """Create the 4 Qdrant dev collections with correct dimensions."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, CreateAliasOperation, CreateAlias

    qdrant_url = os.environ["QDRANT_URL"]
    # Use the same embedding provider logic as the app
    from src.vector_store_helper import _get_embeddings as get_embeddings, ALL_COLLECTION_NAMES
    _, embed_dim = get_embeddings()
    logger.info(f"Embedding dimension: {embed_dim}")

    logger.info(f"Connecting to Qdrant at {qdrant_url}...")
    client = QdrantClient(url=qdrant_url, check_compatibility=False)

    # Real collection names use _dev suffix; bare names become aliases
    suffix = "_dev"
    collection_names = [f"{name}{suffix}" for name in ALL_COLLECTION_NAMES]

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

    # Create aliases: bare name → suffixed collection (e.g. candidates_websites → candidates_websites_dev)
    for bare_name in ALL_COLLECTION_NAMES:
        real_name = f"{bare_name}{suffix}"
        try:
            client.update_collection_aliases(
                change_aliases_operations=[
                    CreateAliasOperation(
                        create_alias=CreateAlias(
                            alias_name=bare_name,
                            collection_name=real_name,
                        )
                    )
                ]
            )
            logger.info(f"  Alias '{bare_name}' → '{real_name}'")
        except Exception as e:
            logger.warning(f"  Failed to set alias '{bare_name}' → '{real_name}': {e}")

    logger.info("Qdrant collections and aliases ready.")


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
            party_id = DIR_TO_PARTY_ID.get(party_dir.name, party_dir.name)
            party_name = party_names.get(party_id, party_names.get(party_dir.name, party_id))
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
            ",".join(party_ids) if isinstance(party_ids, list) else str(party_ids)

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


def restore_qdrant_snapshots():
    """Restore Qdrant collections from snapshot files if available."""
    import requests

    snapshots_dir = FIREBASE_DATA_DIR / "qdrant_snapshots"
    if not snapshots_dir.exists():
        logger.info("No qdrant_snapshots/ directory found, skipping snapshot restore")
        return

    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")

    # Map snapshot filenames to collection names
    snapshot_files = list(snapshots_dir.glob("*.snapshot"))
    if not snapshot_files:
        logger.info("No .snapshot files found in qdrant_snapshots/")
        return

    for snapshot_file in snapshot_files:
        # Derive collection name from filename (e.g. candidates_websites_dev.snapshot)
        collection_name = snapshot_file.stem
        logger.info(f"Restoring snapshot for '{collection_name}' ({snapshot_file.stat().st_size / 1024 / 1024:.0f} MB)...")

        # Check if collection already has data
        try:
            resp = requests.get(f"{qdrant_url}/collections/{collection_name}")
            if resp.ok:
                info = resp.json().get("result", {})
                points = info.get("points_count", 0)
                if points and points > 0:
                    logger.info(f"  Collection '{collection_name}' already has {points} points — skipping restore")
                    continue
        except Exception:
            pass

        # Delete collection if it exists (snapshot restore needs a clean slate)
        try:
            requests.delete(f"{qdrant_url}/collections/{collection_name}")
        except Exception:
            pass

        # Upload snapshot to restore
        try:
            with open(snapshot_file, "rb") as f:
                resp = requests.post(
                    f"{qdrant_url}/collections/{collection_name}/snapshots/upload",
                    files={"snapshot": (snapshot_file.name, f)},
                    params={"priority": "snapshot"},
                    timeout=300,
                )
            if resp.ok:
                # Verify restoration
                resp2 = requests.get(f"{qdrant_url}/collections/{collection_name}")
                points = resp2.json().get("result", {}).get("points_count", 0) if resp2.ok else "?"
                logger.info(f"  Restored '{collection_name}' — {points} points")
            else:
                logger.error(f"  Failed to restore '{collection_name}': {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.error(f"  Error restoring '{collection_name}': {e}")


def _qdrant_collections_have_data() -> bool:
    """Return True if any Qdrant dev collection already has vectors."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=os.environ["QDRANT_URL"], check_compatibility=False)
        from src.vector_store_helper import PARTY_INDEX_NAME, CANDIDATES_INDEX_NAME
        for name in [f"{PARTY_INDEX_NAME}_dev", f"{CANDIDATES_INDEX_NAME}_dev"]:
            try:
                info = client.get_collection(name)
                if info.points_count and info.points_count > 0:
                    logger.info(f"  Collection '{name}' has {info.points_count} points")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def main():
    parser = argparse.ArgumentParser(description="Seed local dev environment")
    parser.add_argument(
        "--with-vectors",
        action="store_true",
        help="Also generate sample embeddings via Ollama",
    )
    parser.add_argument(
        "--restore-snapshots",
        action="store_true",
        help="Restore Qdrant collections from snapshot files in qdrant_snapshots/",
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

    # Step 3a (optional): Restore Qdrant snapshots (fast, no embedding needed)
    if args.restore_snapshots:
        logger.info("\n--- Restoring Qdrant Snapshots ---")
        restore_qdrant_snapshots()

    # Step 3b (optional): Seed vectors from crawled content
    if args.with_vectors:
        # Skip if collections already have data (avoids slow re-embedding)
        if _qdrant_collections_have_data():
            logger.info("\n--- Qdrant collections already have vectors — skipping embedding ---")
            logger.info("    (Run 'make clean' first to force re-embedding)")
        else:
            logger.info("\n--- Seeding Crawled Content Vectors ---")
            seed_crawled_vectors()

    logger.info("\n=== Seeding complete! ===")


if __name__ == "__main__":
    main()
