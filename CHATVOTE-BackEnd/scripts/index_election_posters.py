"""
Batch indexer for election poster PDFs from chatvote-cowork scraper output.

Consolidates with Firestore data:
- Uses Firestore electoral list labels (canonical) instead of CSV names
- Links to Firestore candidate_id when matched by panel number
- Coexists with candidate website chunks (different namespace prefix)
- Skips already-indexed posters unless --force

Usage:
    # Index all communes
    poetry run python scripts/index_election_posters.py

    # Index specific commune(s)
    poetry run python scripts/index_election_posters.py --commune 75056

    # Dry run (no Qdrant writes)
    poetry run python scripts/index_election_posters.py --dry-run

    # Force re-index (delete existing poster chunks first)
    poetry run python scripts/index_election_posters.py --force

Requires: ENV, GOOGLE_API_KEY, QDRANT_URL (+ QDRANT_API_KEY if remote)
          Firebase credentials (FIREBASE_CREDENTIALS_BASE64 or service account)
"""

import asyncio
import csv
import logging
import os
import sys
import time
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

from src.models.chunk_metadata import ChunkMetadata
from src.services.document_upload import extract_text
from src.vector_store_helper import (
    qdrant_client,
    get_candidates_vector_store,
    CANDIDATES_INDEX_NAME,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent  # ChatVote/
COWORK_OUTPUT = _REPO_ROOT.parent / "chatvote-cowork" / "scraper" / "output"
INDEX_CSV = COWORK_OUTPUT / "index.csv"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""],
)

# Max concurrent Gemini OCR calls (free tier: 15 RPM → safe at 5)
OCR_SEMAPHORE = asyncio.Semaphore(5)

# Keyword-based theme classification (same as aiohttp_app.py dashboard)
_THEME_KEYWORDS: dict[str, list[str]] = {
    "economie": ["économie", "economie", "impôt", "impot", "fiscal", "budget", "dette", "emploi", "chômage", "chomage", "salaire", "pouvoir d'achat", "inflation", "entreprise", "commerce", "travail"],
    "education": ["école", "ecole", "éducation", "education", "enseignant", "professeur", "université", "universite", "lycée", "lycee", "collège", "college", "scolaire", "formation", "étudiant", "etudiant"],
    "environnement": ["environnement", "écologie", "ecologie", "climat", "pollution", "déchet", "recyclage", "énergie", "energie", "renouvelable", "carbone", "vert", "biodiversité", "biodiversite"],
    "sante": ["santé", "sante", "hôpital", "hopital", "médecin", "medecin", "soins", "maladie", "vaccination", "pharmacie", "urgence", "infirmier"],
    "securite": ["sécurité", "securite", "police", "délinquance", "delinquance", "criminalité", "criminalite", "violence", "cambriolage", "vol", "agression", "gendarmerie"],
    "immigration": ["immigration", "immigré", "immigre", "migrant", "frontière", "frontiere", "étranger", "etranger", "asile", "régularisation", "regularisation", "intégration", "integration"],
    "culture": ["culture", "musée", "musee", "théâtre", "theatre", "cinéma", "cinema", "bibliothèque", "bibliotheque", "art", "patrimoine", "festival", "spectacle"],
    "logement": ["logement", "loyer", "immobilier", "HLM", "habitation", "propriétaire", "proprietaire", "locataire", "construction", "rénovation", "renovation", "appartement", "maison"],
    "transport": ["transport", "métro", "metro", "bus", "tramway", "vélo", "velo", "voiture", "route", "autoroute", "train", "mobilité", "mobilite", "circulation", "stationnement", "parking"],
    "numerique": ["numérique", "numerique", "internet", "digital", "fibre", "technologie", "données", "donnees", "cybersécurité", "cybersecurite", "IA", "intelligence artificielle"],
    "agriculture": ["agriculture", "agriculteur", "ferme", "paysan", "bio", "pesticide", "alimentaire", "PAC", "élevage", "elevage", "récolte", "recolte"],
    "justice": ["justice", "tribunal", "juge", "loi", "droit", "prison", "peine", "avocat", "procès", "proces", "juridique", "magistrat"],
    "international": ["international", "Europe", "UE", "OTAN", "diplomatie", "guerre", "paix", "défense", "defense", "armée", "armee", "géopolitique", "geopolitique"],
    "institutions": ["institution", "démocratie", "democratie", "élection", "election", "vote", "référendum", "referendum", "parlement", "sénat", "senat", "assemblée", "assemblee", "constitution", "maire", "conseil municipal"],
}


# --------------------------------------------------------------------------- #
# Firestore electoral list / candidate lookup
# --------------------------------------------------------------------------- #

@dataclass
class FirestoreListInfo:
    """Canonical electoral list info from Firestore."""
    panel_number: int
    list_label: str        # canonical label — used as party_name in Qdrant
    head_first_name: str
    head_last_name: str
    nuance_code: str
    candidate_id: Optional[str] = None   # matched from candidates collection
    party_ids: list[str] = field(default_factory=list)


async def fetch_firestore_lists(commune_code: str) -> dict[int, FirestoreListInfo]:
    """Fetch electoral lists from Firestore for a commune.
    Returns {panel_number: FirestoreListInfo}."""
    from src.firebase_service import db

    result: dict[int, FirestoreListInfo] = {}

    try:
        el_doc = db.collection("electoral_lists").document(commune_code).get()
        if not el_doc.exists:
            return result

        el_data = el_doc.to_dict() or {}
        for item in el_data.get("lists", []):
            pn = item.get("panel_number")
            if pn is None:
                continue
            result[int(pn)] = FirestoreListInfo(
                panel_number=int(pn),
                list_label=item.get("list_label", ""),
                head_first_name=item.get("head_first_name", ""),
                head_last_name=item.get("head_last_name", ""),
                nuance_code=item.get("nuance_code", ""),
            )
    except Exception as e:
        logger.warning(f"Could not fetch electoral lists for {commune_code}: {e}")

    # Try to match candidates by municipality
    try:
        from src.firebase_service import aget_candidates_by_municipality
        candidates = await aget_candidates_by_municipality(commune_code)
        # Build name→candidate map for matching
        for c in candidates:
            name_key = f"{c.last_name}".upper().strip()
            for pn, info in result.items():
                # Match by last name (head of list)
                if info.head_last_name.upper().strip() == name_key:
                    info.candidate_id = c.candidate_id
                    info.party_ids = c.party_ids or []
                    break
    except Exception as e:
        logger.debug(f"Could not match candidates for {commune_code}: {e}")

    return result


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #

@dataclass
class PosterRow:
    dept_code: str
    commune_code: str
    commune_name: str
    population: int
    code_postal: str
    panneau: int
    list_name: str          # from CSV (may differ from Firestore label)
    tete_de_liste: str
    pdf_path: str
    pdf_url: str
    # Consolidated from Firestore (set after lookup)
    canonical_list_label: Optional[str] = None
    candidate_id: Optional[str] = None
    party_ids: list[str] = field(default_factory=list)

    @property
    def namespace(self) -> str:
        return f"poster_{self.commune_code}_{self.panneau}"

    @property
    def display_list_name(self) -> str:
        """Use Firestore canonical label if available, else CSV name."""
        return self.canonical_list_label or self.list_name

    @property
    def full_pdf_path(self) -> Path:
        return COWORK_OUTPUT / self.pdf_path


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def classify_theme(text: str) -> str | None:
    """Keyword-based theme classification. Returns top theme or None."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for theme, keywords in _THEME_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[theme] = count
    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def parse_index_csv() -> list[PosterRow]:
    """Parse the index.csv and return PosterRow objects."""
    if not INDEX_CSV.exists():
        logger.error(f"index.csv not found at {INDEX_CSV}")
        return []

    rows: list[PosterRow] = []
    with open(INDEX_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append(PosterRow(
                    dept_code=row["dept_code"],
                    commune_code=row["commune_code"],
                    commune_name=row["commune_name"],
                    population=int(row.get("population", 0) or 0),
                    code_postal=row.get("code_postal", ""),
                    panneau=int(row["panneau"]),
                    list_name=row["list_name"],
                    tete_de_liste=row.get("tete_de_liste", ""),
                    pdf_path=row["pdf_path"],
                    pdf_url=row.get("pdf_url", ""),
                ))
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed row: {e} — {row}")
    return rows


def get_existing_poster_namespaces() -> set[str]:
    """Get all poster_* namespaces already in Qdrant."""
    namespaces: set[str] = set()
    try:
        offset = None
        while True:
            results, next_offset = qdrant_client.scroll(
                collection_name=CANDIDATES_INDEX_NAME,
                limit=256,
                offset=offset,
                with_payload=["metadata.namespace"],
                with_vectors=False,
            )
            if not results:
                break
            for point in results:
                ns = (point.payload or {}).get("metadata", {}).get("namespace", "")
                if ns.startswith("poster_"):
                    namespaces.add(ns)
            if next_offset is None:
                break
            offset = next_offset
    except Exception as e:
        logger.warning(f"Could not check existing poster namespaces: {e}")
    return namespaces


def delete_poster_namespace(namespace: str) -> None:
    """Delete all chunks for a given poster namespace."""
    try:
        qdrant_client.delete(
            collection_name=CANDIDATES_INDEX_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(
                        key="metadata.namespace",
                        match=MatchValue(value=namespace),
                    )]
                )
            ),
        )
    except Exception as e:
        logger.error(f"Error deleting namespace {namespace}: {e}")


async def ocr_and_extract(row: PosterRow) -> str:
    """Extract text from a poster PDF, using OCR if needed."""
    pdf_path = row.full_pdf_path
    if not pdf_path.exists():
        logger.warning(f"PDF not found: {pdf_path}")
        return ""

    data = pdf_path.read_bytes()
    filename = pdf_path.name

    async with OCR_SEMAPHORE:
        try:
            text = await extract_text(filename, data)
            return text
        except Exception as e:
            logger.error(f"Failed to extract text from {filename}: {e}")
            return ""


def build_documents(row: PosterRow, text: str) -> list[Document]:
    """Chunk text and create Documents with proper metadata.

    Uses canonical Firestore list label as party_name so the dashboard
    by_list grouping matches commune.lists exactly.
    """
    chunks = text_splitter.split_text(text)
    documents: list[Document] = []

    for i, chunk in enumerate(chunks):
        if len(chunk.strip()) < 30:
            continue

        theme = classify_theme(chunk)

        cm = ChunkMetadata(
            namespace=row.namespace,
            source_document="election_manifesto",
            party_ids=row.party_ids,
            candidate_ids=[row.candidate_id] if row.candidate_id else [],
            party_name=row.display_list_name,  # canonical Firestore label
            candidate_name=row.tete_de_liste,
            municipality_code=row.commune_code,
            municipality_name=row.commune_name,
            municipality_postal_code=row.code_postal,
            document_name=f"{row.display_list_name} - Affiche électorale",
            url=row.pdf_url,
            chunk_index=i,
            total_chunks=0,  # filled below
            theme=theme,
        )
        doc = Document(page_content=chunk, metadata=cm.to_qdrant_payload())
        documents.append(doc)

    for doc in documents:
        doc.metadata["total_chunks"] = len(documents)

    return documents


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #

async def index_poster(row: PosterRow, dry_run: bool = False) -> int:
    """Process one poster: OCR → chunk → classify → index. Returns chunk count."""
    text = await ocr_and_extract(row)
    if not text or len(text.strip()) < 50:
        logger.warning(f"  [{row.namespace}] No text extracted from {row.pdf_path}")
        return 0

    documents = build_documents(row, text)
    if not documents:
        logger.warning(f"  [{row.namespace}] No chunks created")
        return 0

    if dry_run:
        themes = [d.metadata.get("theme", "?") for d in documents]
        theme_dist = defaultdict(int)
        for t in themes:
            theme_dist[t or "none"] += 1
        logger.info(
            f"  [{row.namespace}] DRY RUN: {len(documents)} chunks, "
            f"list={row.display_list_name!r}, "
            f"candidate_id={row.candidate_id}, "
            f"themes: {dict(theme_dist)}"
        )
        return len(documents)

    # Delete existing chunks for this namespace (idempotent)
    delete_poster_namespace(row.namespace)

    # Index
    vector_store = get_candidates_vector_store()
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        await vector_store.aadd_documents(batch)

    return len(documents)


async def main():
    parser = ArgumentParser(description="Index election poster PDFs into Qdrant")
    parser.add_argument("--commune", nargs="*", help="Specific commune code(s) to index")
    parser.add_argument("--dry-run", action="store_true", help="Extract and chunk but don't write to Qdrant")
    parser.add_argument("--force", action="store_true", help="Re-index even if namespace already exists")
    args = parser.parse_args()

    logger.info(f"COWORK_OUTPUT: {COWORK_OUTPUT}")
    logger.info(f"INDEX_CSV: {INDEX_CSV}")
    logger.info(f"ENV: {os.getenv('ENV', 'dev')}")
    logger.info(f"QDRANT collection: {CANDIDATES_INDEX_NAME}")

    # Parse CSV
    rows = parse_index_csv()
    if not rows:
        logger.error("No rows found in index.csv")
        return

    # Filter by commune if specified
    if args.commune:
        commune_set = set(args.commune)
        rows = [r for r in rows if r.commune_code in commune_set]
        logger.info(f"Filtered to {len(rows)} rows for communes: {args.commune}")

    # Check existing namespaces (skip already indexed unless --force)
    if not args.force and not args.dry_run:
        existing = get_existing_poster_namespaces()
        before = len(rows)
        rows = [r for r in rows if r.namespace not in existing]
        skipped = before - len(rows)
        if skipped:
            logger.info(f"Skipping {skipped} already-indexed posters (use --force to re-index)")

    if not rows:
        logger.info("Nothing to index.")
        return

    # Group by commune
    by_commune: dict[str, list[PosterRow]] = defaultdict(list)
    for r in rows:
        by_commune[r.commune_code].append(r)

    logger.info(f"Will index {len(rows)} posters across {len(by_commune)} communes")

    # Consolidate with Firestore data per commune
    logger.info("Fetching electoral lists from Firestore for label consolidation...")
    for commune_code, commune_rows in by_commune.items():
        fs_lists = await fetch_firestore_lists(commune_code)
        matched = 0
        for row in commune_rows:
            info = fs_lists.get(row.panneau)
            if info:
                row.canonical_list_label = info.list_label
                row.candidate_id = info.candidate_id
                row.party_ids = info.party_ids
                matched += 1
            # else: keep CSV values as fallback
        if fs_lists:
            logger.info(
                f"  {commune_code}: {matched}/{len(commune_rows)} posters matched "
                f"to Firestore electoral lists"
            )

    # Process
    t0 = time.monotonic()
    total_chunks = 0
    success_count = 0
    fail_count = 0
    commune_stats: dict[str, int] = {}

    for commune_code, commune_rows in by_commune.items():
        commune_name = commune_rows[0].commune_name
        logger.info(f"\n{'='*60}")
        logger.info(f"Commune: {commune_name} ({commune_code}) — {len(commune_rows)} posters")

        commune_chunks = 0
        for row in commune_rows:
            try:
                count = await index_poster(row, dry_run=args.dry_run)
                if count > 0:
                    success_count += 1
                    commune_chunks += count
                    logger.info(f"  [{row.namespace}] {row.display_list_name}: {count} chunks")
                else:
                    fail_count += 1
            except Exception as e:
                logger.error(f"  [{row.namespace}] Error: {e}")
                fail_count += 1

        total_chunks += commune_chunks
        commune_stats[commune_code] = commune_chunks
        logger.info(f"  → {commune_name}: {commune_chunks} chunks total")

    elapsed = time.monotonic() - t0

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"DONE in {elapsed:.1f}s")
    logger.info(f"  Posters processed: {success_count} OK, {fail_count} failed")
    logger.info(f"  Total chunks indexed: {total_chunks}")
    logger.info(f"  Communes: {len(commune_stats)}")
    if commune_stats:
        logger.info("  Top communes by chunks:")
        for code, count in sorted(commune_stats.items(), key=lambda x: -x[1])[:10]:
            name = next((r.commune_name for r in rows if r.commune_code == code), code)
            logger.info(f"    {name} ({code}): {count}")


if __name__ == "__main__":
    asyncio.run(main())
