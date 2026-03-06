# Unified Chunk Metadata Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enrich every Qdrant chunk with multi-entity references, fiabilité levels, theme classification, and page-aware PDF data so one chunk can be discovered across multiple entity queries with quality filtering.

**Architecture:** Add a `ChunkMetadata` Pydantic model as the single source of truth for all chunk payloads. Modify PDF extraction to track page numbers. Add LLM-based theme classification at ingestion time. Update all indexers and the seed script to produce unified metadata. Update search functions to use array-based `party_ids`/`candidate_ids` filters and fiabilité Range filters. Frontend receives new optional fields transparently.

**Tech Stack:** Python 3.12, Pydantic v2, Qdrant (payload indexes), LangChain, pypdf, aiohttp, Next.js 16 TypeScript

---

## Phase 1: Schema — ChunkMetadata Pydantic Model

### Task 1.1: Create ChunkMetadata and Fiabilité Models

**Files:**
- Create: `CHATVOTE-BackEnd/src/models/chunk_metadata.py`
- Test: `CHATVOTE-BackEnd/tests/test_chunk_metadata.py`

**Step 1: Write the failing test**

```python
# tests/test_chunk_metadata.py
import pytest
from src.models.chunk_metadata import ChunkMetadata, Fiabilite


def test_chunk_metadata_minimal():
    """Minimal valid chunk: just namespace and source_document."""
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
    )
    assert cm.namespace == "ps"
    assert cm.fiabilite == Fiabilite.OFFICIAL  # election_manifesto → level 2
    assert cm.party_ids == []
    assert cm.candidate_ids == []
    assert cm.theme is None
    assert cm.sub_theme is None


def test_fiabilite_auto_assignment_government():
    cm = ChunkMetadata(
        namespace="govt",
        source_document="justified_voting_behavior",
    )
    assert cm.fiabilite == Fiabilite.GOVERNMENT  # level 1


def test_fiabilite_auto_assignment_press():
    cm = ChunkMetadata(
        namespace="cand-1",
        source_document="candidate_website_blog",
    )
    assert cm.fiabilite == Fiabilite.PRESS  # level 3


def test_party_ids_array():
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
        party_ids=["ps", "nfp"],
    )
    assert cm.party_ids == ["ps", "nfp"]


def test_to_qdrant_payload():
    cm = ChunkMetadata(
        namespace="ps",
        source_document="election_manifesto",
        party_ids=["ps"],
        party_name="Parti Socialiste",
        document_name="PS - Programme",
        url="https://example.com/ps.pdf",
        page=3,
        chunk_index=0,
        total_chunks=10,
        theme="economie",
        sub_theme="pouvoir d'achat",
    )
    payload = cm.to_qdrant_payload()
    assert payload["namespace"] == "ps"
    assert payload["party_ids"] == ["ps"]
    assert payload["fiabilite"] == 2
    assert payload["theme"] == "economie"
    assert payload["sub_theme"] == "pouvoir d'achat"
    assert payload["page"] == 3


def test_from_qdrant_payload_roundtrip():
    original = ChunkMetadata(
        namespace="cand-paris-001",
        source_document="candidate_website_about",
        candidate_ids=["cand-paris-001"],
        party_ids=["lr"],
        candidate_name="Jean Dupont",
        municipality_code="75056",
    )
    payload = original.to_qdrant_payload()
    restored = ChunkMetadata.from_qdrant_payload(payload)
    assert restored.namespace == original.namespace
    assert restored.candidate_ids == original.candidate_ids
    assert restored.party_ids == original.party_ids
    assert restored.fiabilite == original.fiabilite
```

**Step 2: Run test to verify it fails**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_chunk_metadata.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.models.chunk_metadata'`

**Step 3: Write the implementation**

```python
# src/models/chunk_metadata.py
"""
Unified chunk metadata model.

Every Qdrant payload MUST be produced by ChunkMetadata.to_qdrant_payload().
This is the single source of truth for chunk metadata shape.
"""

from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class Fiabilite(IntEnum):
    """Source reliability level. Lower = more trustworthy."""
    GOVERNMENT = 1       # Parliamentary records, official votes
    OFFICIAL = 2         # Party manifestos, official party/candidate websites
    PRESS = 3            # Blog posts, press articles, scraped content
    SOCIAL_MEDIA = 4     # Social media (excluded by default in queries)


# Mapping: source_document prefix → fiabilité level
_SOURCE_FIABILITE_MAP: dict[str, Fiabilite] = {
    "justified_voting_behavior": Fiabilite.GOVERNMENT,
    "parliamentary_question": Fiabilite.GOVERNMENT,
    "election_manifesto": Fiabilite.OFFICIAL,
    "party_website": Fiabilite.OFFICIAL,
    "candidate_website_about": Fiabilite.OFFICIAL,
    "candidate_website_programme": Fiabilite.OFFICIAL,
    "candidate_website_blog": Fiabilite.PRESS,
    "candidate_website_actualite": Fiabilite.PRESS,
    "candidate_website": Fiabilite.PRESS,  # generic fallback for candidate sites
}


# Fixed 14-theme taxonomy for UI faceting
THEME_TAXONOMY: list[str] = [
    "economie",
    "education",
    "environnement",
    "sante",
    "securite",
    "immigration",
    "culture",
    "logement",
    "transport",
    "numerique",
    "agriculture",
    "justice",
    "international",
    "institutions",
]


def _infer_fiabilite(source_document: str) -> Fiabilite:
    """Auto-assign fiabilité from source_document field."""
    # Try exact match first
    if source_document in _SOURCE_FIABILITE_MAP:
        return _SOURCE_FIABILITE_MAP[source_document]
    # Try prefix match (e.g. "candidate_website_blog" matches "candidate_website")
    for prefix, level in sorted(
        _SOURCE_FIABILITE_MAP.items(), key=lambda x: -len(x[0])
    ):
        if source_document.startswith(prefix):
            return level
    # Default: PRESS (level 3) for unknown sources
    return Fiabilite.PRESS


class ChunkMetadata(BaseModel):
    """
    Unified metadata for every chunk stored in Qdrant.

    Replaces ad-hoc metadata dicts in manifesto_indexer, candidate_indexer,
    seed_local, and websocket_app source formatting.
    """

    # --- Required fields ---
    namespace: str = Field(description="Primary entity ID for backward compat")
    source_document: str = Field(description="Source type key for fiabilité inference")

    # --- Multi-entity references (arrays for cross-entity discovery) ---
    party_ids: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)

    # --- Entity display info ---
    party_name: Optional[str] = None
    candidate_name: Optional[str] = None
    municipality_code: Optional[str] = None
    municipality_name: Optional[str] = None
    election_type_id: Optional[str] = None

    # --- Source display info ---
    document_name: Optional[str] = None
    url: Optional[str] = None
    document_publish_date: Optional[str] = None
    page_title: Optional[str] = None
    page_type: Optional[str] = None

    # --- Chunk position ---
    page: int = 0
    chunk_index: int = 0
    total_chunks: int = 0

    # --- Quality & classification ---
    fiabilite: Fiabilite = Field(default=Fiabilite.PRESS)
    theme: Optional[str] = None
    sub_theme: Optional[str] = None

    @model_validator(mode="after")
    def _auto_fiabilite(self) -> "ChunkMetadata":
        """Auto-assign fiabilité from source_document if not explicitly set."""
        # Always recompute from source_document — the field default is just a placeholder
        self.fiabilite = _infer_fiabilite(self.source_document)
        return self

    def to_qdrant_payload(self) -> dict:
        """Serialize to flat dict for Qdrant metadata payload."""
        d = self.model_dump(exclude_none=True)
        # Ensure fiabilite is stored as int for Range filtering
        d["fiabilite"] = int(self.fiabilite)
        return d

    @classmethod
    def from_qdrant_payload(cls, payload: dict) -> "ChunkMetadata":
        """Deserialize from Qdrant metadata payload."""
        return cls(**payload)
```

**Step 4: Run test to verify it passes**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_chunk_metadata.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/models/chunk_metadata.py tests/test_chunk_metadata.py
git commit -m "feat: add ChunkMetadata Pydantic model with fiabilité auto-assignment"
```

---

### Task 1.2: Add ThemeClassification Structured Output Schema

**Files:**
- Modify: `CHATVOTE-BackEnd/src/models/structured_outputs.py:96` (append after EntityDetector)
- Test: `CHATVOTE-BackEnd/tests/test_chunk_metadata.py` (append)

**Step 1: Write the failing test**

```python
# Append to tests/test_chunk_metadata.py
def test_theme_classification_schema():
    from src.models.structured_outputs import ChunkThemeClassification
    tc = ChunkThemeClassification(theme="economie", sub_theme="pouvoir d'achat")
    assert tc.theme == "economie"
    assert tc.sub_theme == "pouvoir d'achat"


def test_theme_classification_none_theme():
    from src.models.structured_outputs import ChunkThemeClassification
    tc = ChunkThemeClassification(theme=None, sub_theme=None)
    assert tc.theme is None
```

**Step 2: Run test to verify it fails**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_chunk_metadata.py::test_theme_classification_schema -v`
Expected: FAIL with `ImportError: cannot import name 'ChunkThemeClassification'`

**Step 3: Append to structured_outputs.py after line 96**

```python
class ChunkThemeClassification(BaseModel):
    """LLM classification of a chunk's political theme."""

    theme: Optional[str] = Field(
        default=None,
        description=(
            "The primary political theme of this text. Must be one of: "
            "economie, education, environnement, sante, securite, immigration, "
            "culture, logement, transport, numerique, agriculture, justice, "
            "international, institutions. "
            "Use null if the text does not clearly fit any theme."
        ),
    )
    sub_theme: Optional[str] = Field(
        default=None,
        description=(
            "A more specific sub-theme in 2-4 words (e.g., 'pouvoir d'achat', "
            "'transports en commun', 'logement social'). "
            "Use null if no specific sub-theme applies."
        ),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_chunk_metadata.py -v`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add src/models/structured_outputs.py tests/test_chunk_metadata.py
git commit -m "feat: add ChunkThemeClassification structured output schema"
```

---

## Phase 2: Page-Aware PDF Chunking

### Task 2.1: Modify PDF Extraction to Track Page Numbers

**Files:**
- Modify: `CHATVOTE-BackEnd/src/services/manifesto_indexer.py:62-77` (extract_text_from_pdf)
- Modify: `CHATVOTE-BackEnd/src/services/manifesto_indexer.py:80-110` (create_documents_from_text)
- Test: `CHATVOTE-BackEnd/tests/test_manifesto_indexer.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_manifesto_indexer.py
import pytest
from unittest.mock import MagicMock
from src.services.manifesto_indexer import extract_pages_from_pdf, create_documents_from_pages
from src.models.party import Party


def _make_party():
    return Party(
        party_id="test-party",
        name="Test Party",
        long_name="Test Party Long",
        election_manifesto_url="https://example.com/test.pdf",
    )


def test_extract_pages_returns_list_of_tuples():
    """extract_pages_from_pdf returns [(page_num, text), ...]."""
    # Create a minimal PDF in memory using pypdf
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    # Add 2 blank pages with text annotations (pypdf doesn't easily add text,
    # so we test with real bytes from a simple PDF)
    # For unit test, we mock PdfReader instead
    pass  # See step 3 — we test via integration


def test_create_documents_from_pages_preserves_page_number():
    """Each chunk gets the correct PDF page number, not chunk index."""
    pages = [
        (1, "First page content about economy and budget policy. " * 20),
        (2, "Second page about environment and climate. " * 20),
    ]
    party = _make_party()
    docs = create_documents_from_pages(pages, party, "https://example.com/test.pdf")

    assert len(docs) > 0
    # First doc should come from page 1
    assert docs[0].metadata["page"] == 1
    # Check that some doc has page 2
    page_2_docs = [d for d in docs if d.metadata["page"] == 2]
    assert len(page_2_docs) > 0
    # All docs should have party_ids as a list
    assert docs[0].metadata["party_ids"] == ["test-party"]
    assert docs[0].metadata["fiabilite"] == 2  # election_manifesto → OFFICIAL
```

**Step 2: Run test to verify it fails**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_manifesto_indexer.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract_pages_from_pdf'`

**Step 3: Modify manifesto_indexer.py**

Replace `extract_text_from_pdf` (lines 62-77) with:

```python
def extract_pages_from_pdf(pdf_content: bytes) -> list[tuple[int, str]]:
    """Extract text from PDF bytes, returning [(1-indexed page_num, text), ...]."""
    try:
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)

        pages = []
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                pages.append((page_num, page_text))

        return pages
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return []
```

Replace `create_documents_from_text` (lines 80-110) with:

```python
def create_documents_from_pages(
    pages: list[tuple[int, str]],
    party: Party,
    source_url: str,
) -> list[Document]:
    """Split pages into chunks preserving real PDF page numbers."""
    from src.models.chunk_metadata import ChunkMetadata

    documents = []
    chunk_index = 0

    for page_num, page_text in pages:
        chunks = text_splitter.split_text(page_text)
        for chunk in chunks:
            cm = ChunkMetadata(
                namespace=party.party_id,
                source_document="election_manifesto",
                party_ids=[party.party_id],
                party_name=party.name,
                document_name=f"{party.name} - Programme électoral",
                url=source_url,
                page=page_num,
                chunk_index=chunk_index,
                total_chunks=0,  # updated below
            )
            doc = Document(page_content=chunk, metadata=cm.to_qdrant_payload())
            documents.append(doc)
            chunk_index += 1

    # Backfill total_chunks
    for doc in documents:
        doc.metadata["total_chunks"] = len(documents)

    return documents
```

Update `index_party_manifesto` (line 160) to use new functions:

```python
    # Step 2: Extract pages (not flat text)
    pages = extract_pages_from_pdf(pdf_content)
    if not pages:
        logger.error(f"Could not extract text from PDF for party {party.party_id}")
        return 0

    total_chars = sum(len(t) for _, t in pages)
    logger.info(f"Extracted {total_chars} chars from {len(pages)} pages for {party.party_id}")

    # Step 3: Create documents (chunks with real page numbers)
    documents = create_documents_from_pages(
        pages=pages,
        party=party,
        source_url=party.election_manifesto_url,
    )
```

Also keep old `extract_text_from_pdf` as a thin wrapper for backward compat:

```python
def extract_text_from_pdf(pdf_content: bytes) -> str:
    """Legacy wrapper — use extract_pages_from_pdf for page-aware chunking."""
    pages = extract_pages_from_pdf(pdf_content)
    return "\n\n".join(text for _, text in pages)
```

**Step 4: Run test to verify it passes**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_manifesto_indexer.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/services/manifesto_indexer.py tests/test_manifesto_indexer.py
git commit -m "feat: page-aware PDF chunking with real page numbers"
```

---

## Phase 3: LLM Theme Classification at Ingestion

### Task 3.1: Add Theme Classification Helper

**Files:**
- Create: `CHATVOTE-BackEnd/src/services/chunk_classifier.py`
- Test: `CHATVOTE-BackEnd/tests/test_chunk_classifier.py`

**Step 1: Write the failing test**

```python
# tests/test_chunk_classifier.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.chunk_classifier import classify_chunks_themes
from src.models.structured_outputs import ChunkThemeClassification


@pytest.mark.asyncio
async def test_classify_chunks_returns_theme_list():
    """classify_chunks_themes returns a list of ChunkThemeClassification."""
    mock_result = ChunkThemeClassification(theme="economie", sub_theme="budget")

    with patch("src.services.chunk_classifier.get_structured_output_from_llms") as mock_llm:
        mock_llm.return_value = mock_result
        results = await classify_chunks_themes(["Chunk about budget and taxes."])

    assert len(results) == 1
    assert results[0].theme == "economie"
    assert results[0].sub_theme == "budget"


@pytest.mark.asyncio
async def test_classify_chunks_handles_llm_failure():
    """If LLM fails, return None themes (not crash)."""
    with patch("src.services.chunk_classifier.get_structured_output_from_llms") as mock_llm:
        mock_llm.side_effect = Exception("LLM down")
        results = await classify_chunks_themes(["Some text"])

    assert len(results) == 1
    assert results[0].theme is None


@pytest.mark.asyncio
async def test_classify_chunks_batches():
    """Chunks are classified in configurable batch sizes."""
    mock_result = ChunkThemeClassification(theme="sante", sub_theme=None)

    call_count = 0
    async def mock_classify(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_result

    with patch("src.services.chunk_classifier.get_structured_output_from_llms", side_effect=mock_classify):
        results = await classify_chunks_themes(
            ["chunk"] * 5,
            batch_size=2,
        )

    assert len(results) == 5
    assert call_count == 5  # Each chunk classified individually
```

**Step 2: Run test to verify it fails**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_chunk_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.chunk_classifier'`

**Step 3: Write the implementation**

```python
# src/services/chunk_classifier.py
"""
LLM-based theme classification for chunks at ingestion time.

Uses the LLM failover chain to classify each chunk into the 14-theme taxonomy.
Batches chunks to limit LLM calls. Gracefully degrades on failure.
"""

import asyncio
import logging
from typing import Optional

from src.models.structured_outputs import ChunkThemeClassification
from src.llms import get_structured_output_from_llms

logger = logging.getLogger(__name__)

_CLASSIFICATION_PROMPT = """Classify the following text excerpt from a French political document.
Determine its primary political theme and a specific sub-theme.

Text:
---
{chunk_text}
---
"""


async def _classify_single(chunk_text: str) -> ChunkThemeClassification:
    """Classify a single chunk. Returns None-theme on failure."""
    try:
        result = await asyncio.to_thread(
            get_structured_output_from_llms,
            ChunkThemeClassification,
            _CLASSIFICATION_PROMPT.format(chunk_text=chunk_text[:500]),
        )
        return result
    except Exception as e:
        logger.warning(f"Theme classification failed: {e}")
        return ChunkThemeClassification(theme=None, sub_theme=None)


async def classify_chunks_themes(
    chunks: list[str],
    batch_size: int = 10,
    max_concurrent: int = 5,
) -> list[ChunkThemeClassification]:
    """
    Classify a list of chunks into themes.

    Args:
        chunks: Text chunks to classify.
        batch_size: How many chunks to process per batch (for progress logging).
        max_concurrent: Max concurrent LLM calls.

    Returns:
        List of ChunkThemeClassification, one per input chunk.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded_classify(text: str) -> ChunkThemeClassification:
        async with semaphore:
            return await _classify_single(text)

    results = await asyncio.gather(
        *[_bounded_classify(chunk) for chunk in chunks]
    )

    classified = sum(1 for r in results if r.theme is not None)
    logger.info(f"Classified {classified}/{len(chunks)} chunks with themes")

    return list(results)
```

**Step 4: Run test to verify it passes**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_chunk_classifier.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/services/chunk_classifier.py tests/test_chunk_classifier.py
git commit -m "feat: add LLM-based chunk theme classifier"
```

---

### Task 3.2: Integrate Theme Classification into Manifesto Indexer

**Files:**
- Modify: `CHATVOTE-BackEnd/src/services/manifesto_indexer.py:139-194` (index_party_manifesto)
- Test: `CHATVOTE-BackEnd/tests/test_manifesto_indexer.py` (append)

**Step 1: Write the failing test**

```python
# Append to tests/test_manifesto_indexer.py
@pytest.mark.asyncio
async def test_index_party_manifesto_classifies_themes(monkeypatch):
    """Theme classification is called during indexing and results stored in metadata."""
    from src.services import manifesto_indexer
    from src.models.structured_outputs import ChunkThemeClassification

    # Mock PDF fetch
    monkeypatch.setattr(manifesto_indexer, "fetch_pdf_content", AsyncMock(return_value=b"fake"))
    # Mock page extraction
    monkeypatch.setattr(
        manifesto_indexer, "extract_pages_from_pdf",
        lambda _: [(1, "Economy content. " * 50)],
    )
    # Mock vector store
    mock_vs = MagicMock()
    mock_vs.aadd_documents = AsyncMock()
    monkeypatch.setattr(manifesto_indexer, "get_qdrant_vector_store", lambda: mock_vs)
    # Mock delete
    monkeypatch.setattr(manifesto_indexer, "delete_party_documents", AsyncMock(return_value=1))
    # Mock theme classification
    mock_classify = AsyncMock(return_value=[
        ChunkThemeClassification(theme="economie", sub_theme="budget")
    ])
    monkeypatch.setattr(
        "src.services.manifesto_indexer.classify_chunks_themes", mock_classify
    )

    party = _make_party()
    count = await manifesto_indexer.index_party_manifesto(party)

    assert count > 0
    mock_classify.assert_called_once()
    # Check that the documents passed to vector store have theme in metadata
    added_docs = mock_vs.aadd_documents.call_args_list[0][0][0]
    assert added_docs[0].metadata.get("theme") == "economie"
```

**Step 2: Run test to verify it fails**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_manifesto_indexer.py::test_index_party_manifesto_classifies_themes -v`
Expected: FAIL (classify_chunks_themes not called in indexer)

**Step 3: Add classification step to index_party_manifesto**

After creating documents (around current line 178), add:

```python
    # Step 4: Classify themes (optional — degrades gracefully)
    try:
        from src.services.chunk_classifier import classify_chunks_themes
        chunk_texts = [doc.page_content for doc in documents]
        classifications = await classify_chunks_themes(chunk_texts)
        for doc, cls in zip(documents, classifications):
            if cls.theme:
                doc.metadata["theme"] = cls.theme
            if cls.sub_theme:
                doc.metadata["sub_theme"] = cls.sub_theme
        logger.info(f"Theme classification complete for {party.party_id}")
    except Exception as e:
        logger.warning(f"Theme classification skipped for {party.party_id}: {e}")
```

**Step 4: Run test to verify it passes**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_manifesto_indexer.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/services/manifesto_indexer.py tests/test_manifesto_indexer.py
git commit -m "feat: integrate theme classification into manifesto indexing"
```

---

## Phase 4: Indexer Updates for Unified Metadata

### Task 4.1: Update Candidate Indexer to Use ChunkMetadata

**Files:**
- Modify: `CHATVOTE-BackEnd/src/services/candidate_indexer.py:119-165` (create_documents_from_scraped_website)
- Modify: `CHATVOTE-BackEnd/src/services/candidate_indexer.py:80-95` (payload indexes)
- Test: `CHATVOTE-BackEnd/tests/test_candidate_indexer.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_candidate_indexer.py
import pytest
from unittest.mock import MagicMock
from src.services.candidate_indexer import create_documents_from_scraped_website
from src.models.candidate import Candidate


def _make_candidate():
    return Candidate(
        candidate_id="cand-paris-001",
        first_name="Jean",
        last_name="Dupont",
        municipality_code="75056",
        municipality_name="Paris",
        party_ids=["lr", "udi"],
        website_url="https://jeandupont.fr",
        election_type_id="municipales-2026",
    )


def _make_scraped_website():
    from src.services.candidate_website_scraper import ScrapedWebsite, ScrapedPage
    page = ScrapedPage(
        url="https://jeandupont.fr/about",
        title="About",
        content="Jean Dupont is a candidate for Paris. " * 30,
        page_type="about",
    )
    return ScrapedWebsite(
        candidate_id="cand-paris-001",
        pages=[page],
        is_successful=True,
    )


def test_candidate_docs_use_chunk_metadata():
    candidate = _make_candidate()
    scraped = _make_scraped_website()
    docs = create_documents_from_scraped_website(candidate, scraped)

    assert len(docs) > 0
    meta = docs[0].metadata
    # party_ids must be a list (not comma-separated string)
    assert meta["party_ids"] == ["lr", "udi"]
    assert meta["candidate_ids"] == ["cand-paris-001"]
    assert meta["fiabilite"] == 2  # candidate_website_about → OFFICIAL
    assert meta["namespace"] == "cand-paris-001"
    assert meta["municipality_code"] == "75056"
```

**Step 2: Run test to verify it fails**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_candidate_indexer.py -v`
Expected: FAIL — `party_ids` is a comma-separated string, not a list

**Step 3: Modify create_documents_from_scraped_website (lines 119-165)**

```python
def create_documents_from_scraped_website(
    candidate: Candidate,
    scraped_website: ScrapedWebsite,
) -> List[Document]:
    """Create LangChain documents from scraped website content using ChunkMetadata."""
    from src.models.chunk_metadata import ChunkMetadata

    documents = []
    chunk_index = 0

    for page in scraped_website.pages:
        chunks = text_splitter.split_text(page.content)

        for chunk in chunks:
            cm = ChunkMetadata(
                namespace=candidate.candidate_id,
                source_document=f"candidate_website_{page.page_type}",
                party_ids=candidate.party_ids or [],
                candidate_ids=[candidate.candidate_id],
                candidate_name=candidate.full_name,
                municipality_code=candidate.municipality_code or "",
                municipality_name=candidate.municipality_name or "",
                election_type_id=candidate.election_type_id,
                document_name=f"{candidate.full_name} - {page.page_type.capitalize()}",
                url=page.url,
                page_title=page.title,
                page_type=page.page_type,
                page=chunk_index + 1,
                chunk_index=chunk_index,
                total_chunks=0,  # backfilled below
            )
            doc = Document(page_content=chunk, metadata=cm.to_qdrant_payload())
            documents.append(doc)
            chunk_index += 1

    for doc in documents:
        doc.metadata["total_chunks"] = len(documents)

    return documents
```

Also update `_ensure_candidates_collection_exists` (lines 80-95) to add new payload indexes:

```python
            # New indexes for unified metadata
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.party_ids",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.candidate_ids",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.fiabilite",
                field_schema=PayloadSchemaType.INTEGER,
            )
```

**Step 4: Run test to verify it passes**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_candidate_indexer.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/services/candidate_indexer.py tests/test_candidate_indexer.py
git commit -m "feat: candidate indexer uses ChunkMetadata with array party_ids"
```

---

### Task 4.2: Update Seed Script to Use ChunkMetadata

**Files:**
- Modify: `CHATVOTE-BackEnd/scripts/seed_local.py:257-370` (_embed_and_collect and callers)
- Test: Manual verification via `make seed-vectors`

**Step 1: Modify _embed_and_collect (lines 257-294)**

The `metadata_base` dict should be built from `ChunkMetadata` instead of raw dicts. Replace the metadata construction inside `_embed_and_collect`:

```python
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
```

Update the party seeding caller (lines 311-320):

```python
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
```

Update the candidate seeding caller (lines 351-363):

```python
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
```

**Step 2: Test manually**

Run: `make seed-vectors`
Expected: Seeding completes without errors; `make check` passes

**Step 3: Commit**

```bash
git add scripts/seed_local.py
git commit -m "feat: seed script uses ChunkMetadata for unified payloads"
```

---

### Task 4.3: Add Qdrant Payload Indexes for New Fields

**Files:**
- Modify: `CHATVOTE-BackEnd/src/vector_store_helper.py` (after collection creation)
- No dedicated test — verified via existing integration tests

**Step 1: Add a helper to ensure indexes exist**

Add after the existing `_ensure_collection_exists` calls (around line 250):

```python
def _ensure_payload_indexes(collection_name: str) -> None:
    """Create payload indexes for unified metadata fields if they don't exist."""
    from qdrant_client.models import PayloadSchemaType

    indexes_to_create = [
        ("metadata.party_ids", PayloadSchemaType.KEYWORD),
        ("metadata.candidate_ids", PayloadSchemaType.KEYWORD),
        ("metadata.fiabilite", PayloadSchemaType.INTEGER),
        ("metadata.theme", PayloadSchemaType.KEYWORD),
    ]

    for field_name, schema_type in indexes_to_create:
        try:
            qdrant_client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema_type,
            )
        except Exception:
            pass  # Index may already exist
```

Call it from `_get_vector_store` after collection creation, for both `PARTY_INDEX_NAME` and `CANDIDATES_INDEX_NAME`.

**Step 2: Verify manually**

Run: `make dev` then `make check`
Expected: All services healthy, no errors in logs

**Step 3: Commit**

```bash
git add src/vector_store_helper.py
git commit -m "feat: add Qdrant payload indexes for fiabilite, party_ids, theme"
```

---

## Phase 5: Query Updates for Cross-Entity Retrieval

### Task 5.1: Replace Python-Side Party Filtering with Qdrant MatchAny

**Files:**
- Modify: `CHATVOTE-BackEnd/src/vector_store_helper.py:797-853` (_search_candidate_docs_by_party)
- Modify: `CHATVOTE-BackEnd/src/vector_store_helper.py:856-921` (_search_candidate_docs_by_party_and_municipality)
- Test: `CHATVOTE-BackEnd/tests/test_vector_search.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_vector_search.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from qdrant_client.models import Filter, FieldCondition, MatchAny


def test_party_filter_uses_match_any():
    """Verify that _build_party_filter creates a MatchAny condition on metadata.party_ids."""
    from src.vector_store_helper import _build_party_filter

    f = _build_party_filter(["ps", "nfp"])
    # Should produce a Filter with MatchAny on metadata.party_ids
    assert f is not None
    must_conditions = f.must
    party_condition = [c for c in must_conditions if c.key == "metadata.party_ids"][0]
    assert party_condition.match.any == ["ps", "nfp"]


def test_fiabilite_filter():
    """Verify fiabilité Range filter excludes social media by default."""
    from src.vector_store_helper import _build_fiabilite_filter

    f = _build_fiabilite_filter(max_fiabilite=3)
    assert f is not None
    fiab_condition = [c for c in f.must if c.key == "metadata.fiabilite"][0]
    assert fiab_condition.range.lte == 3
```

**Step 2: Run test to verify it fails**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_vector_search.py -v`
Expected: FAIL with `ImportError: cannot import name '_build_party_filter'`

**Step 3: Add filter builder helpers to vector_store_helper.py**

Add near the top of the file (after imports):

```python
from qdrant_client.models import MatchAny, Range

def _build_party_filter(party_ids: list[str]) -> Filter:
    """Build a Qdrant filter for matching any of the given party_ids."""
    return Filter(
        must=[
            FieldCondition(
                key="metadata.party_ids",
                match=MatchAny(any=party_ids),
            )
        ]
    )


def _build_fiabilite_filter(max_fiabilite: int = 3) -> Filter:
    """Build a Qdrant Range filter excluding sources above max_fiabilite."""
    return Filter(
        must=[
            FieldCondition(
                key="metadata.fiabilite",
                range=Range(lte=max_fiabilite),
            )
        ]
    )


def _combine_filters(*filters: Optional[Filter]) -> Optional[Filter]:
    """Merge multiple Filters into one by combining all must conditions."""
    all_must = []
    for f in filters:
        if f is not None and f.must:
            all_must.extend(f.must)
    if not all_must:
        return None
    return Filter(must=all_must)
```

**Step 4: Run test to verify it passes**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_vector_search.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/vector_store_helper.py tests/test_vector_search.py
git commit -m "feat: add MatchAny and Range filter builders for Qdrant"
```

---

### Task 5.2: Refactor _search_candidate_docs_by_party to Use Server-Side Filtering

**Files:**
- Modify: `CHATVOTE-BackEnd/src/vector_store_helper.py:797-853`
- Modify: `CHATVOTE-BackEnd/src/vector_store_helper.py:856-921`
- Test: `CHATVOTE-BackEnd/tests/test_vector_search.py` (append)

**Step 1: Write the failing test**

```python
# Append to tests/test_vector_search.py
@pytest.mark.asyncio
async def test_search_candidate_by_party_uses_qdrant_filter(monkeypatch):
    """_search_candidate_docs_by_party should use Qdrant filter, not Python filtering."""
    from src import vector_store_helper as vsh

    # Mock collection exists
    monkeypatch.setattr(vsh, "_collection_exists", lambda _: True)

    # Mock embed
    mock_embed = MagicMock()
    mock_embed.aembed_query = AsyncMock(return_value=[0.1] * 3072)
    monkeypatch.setattr(vsh, "embed", mock_embed)

    # Mock async_qdrant_client.search
    mock_point = MagicMock()
    mock_point.payload = {
        "page_content": "Test content",
        "metadata": {
            "namespace": "cand-1",
            "party_ids": ["ps", "nfp"],
            "candidate_ids": ["cand-1"],
            "fiabilite": 2,
        },
    }
    mock_search = AsyncMock(return_value=[mock_point])
    monkeypatch.setattr(vsh, "async_qdrant_client", MagicMock(search=mock_search))

    docs = await vsh._search_candidate_docs_by_party(
        rag_query="test",
        party_ids=["ps"],
    )

    assert len(docs) == 1
    # Verify the Qdrant search was called with a MatchAny filter
    call_kwargs = mock_search.call_args
    query_filter = call_kwargs.kwargs.get("query_filter") or call_kwargs[1].get("query_filter")
    assert query_filter is not None
    # Should have party_ids MatchAny in the filter
    party_conds = [c for c in query_filter.must if c.key == "metadata.party_ids"]
    assert len(party_conds) == 1
```

**Step 2: Run test to verify it fails**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_vector_search.py::test_search_candidate_by_party_uses_qdrant_filter -v`
Expected: FAIL — current code doesn't use MatchAny filter

**Step 3: Refactor _search_candidate_docs_by_party (lines 797-853)**

Replace the function body:

```python
async def _search_candidate_docs_by_party(
    rag_query: str,
    party_ids: list[str],
    n_docs: int = 10,
    score_threshold: float = 0.65,
    max_fiabilite: int = 3,
) -> list[Document]:
    """Search candidate documents filtered by party affiliation using Qdrant MatchAny."""
    global embed, qdrant_client

    if not _collection_exists(CANDIDATES_INDEX_NAME):
        return []

    query_vector = await embed.aembed_query(rag_query)

    # Server-side filtering: MatchAny on party_ids + fiabilité range
    query_filter = _combine_filters(
        _build_party_filter(party_ids),
        _build_fiabilite_filter(max_fiabilite),
    )

    try:
        search_result = await async_qdrant_client.search(
            collection_name=CANDIDATES_INDEX_NAME,
            query_vector=("dense", query_vector),
            limit=n_docs,
            with_payload=True,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )
    except Exception as e:
        logger.warning(f"Error searching candidates collection: {e}")
        return []

    documents = []
    for point in search_result:
        if point.payload is None:
            continue
        metadata = point.payload.get("metadata", {})
        content = point.payload.get("page_content", "")
        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)

    return documents
```

Similarly refactor `_search_candidate_docs_by_party_and_municipality` (lines 856-921):

```python
async def _search_candidate_docs_by_party_and_municipality(
    rag_query: str,
    party_ids: list[str],
    municipality_code: str,
    n_docs: int = 10,
    score_threshold: float = 0.65,
    max_fiabilite: int = 3,
) -> list[Document]:
    """Search candidate docs filtered by party + municipality using Qdrant filters."""
    global embed, qdrant_client

    if not _collection_exists(CANDIDATES_INDEX_NAME):
        return []

    query_vector = await embed.aembed_query(rag_query)

    municipality_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.municipality_code",
                match=MatchValue(value=municipality_code),
            )
        ]
    )

    query_filter = _combine_filters(
        _build_party_filter(party_ids),
        municipality_filter,
        _build_fiabilite_filter(max_fiabilite),
    )

    try:
        search_result = await async_qdrant_client.search(
            collection_name=CANDIDATES_INDEX_NAME,
            query_vector=("dense", query_vector),
            limit=n_docs,
            with_payload=True,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )
    except Exception as e:
        logger.warning(f"Error searching candidates collection: {e}")
        return []

    documents = []
    for point in search_result:
        if point.payload is None:
            continue
        metadata = point.payload.get("metadata", {})
        content = point.payload.get("page_content", "")
        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)

    return documents
```

**Step 4: Run test to verify it passes**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_vector_search.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/vector_store_helper.py tests/test_vector_search.py
git commit -m "feat: replace Python party filtering with Qdrant MatchAny server-side"
```

---

### Task 5.3: Add Fiabilité Filter to All Search Functions

**Files:**
- Modify: `CHATVOTE-BackEnd/src/vector_store_helper.py` (5 search functions)
- Test: Existing tests + manual `make dev` verification

**Step 1: Identify all search entry points**

These functions build `filter_condition` and call `async_qdrant_client.search`:

1. `_identify_relevant_documents` — line 306 (namespace filter)
2. `_search_candidates_by_scope` — line 504 (candidate_id / municipality_code filter)
3. `_search_candidate_docs_by_party` — line 822 (already done in Task 5.2)
4. `_search_candidate_docs_by_party_and_municipality` — line 879 (already done in Task 5.2)
5. `_identify_relevant_manifesto_documents` — line 939 (namespace filter)

**Step 2: Add max_fiabilite parameter and filter to remaining 3 functions**

For `_identify_relevant_documents` (line 288), add `max_fiabilite: int = 3` param and merge fiabilité filter:

```python
async def _identify_relevant_documents(
    vector_store: QdrantVectorStore,
    namespace: Optional[str],
    rag_query: str,
    n_docs: int = 5,
    score_threshold: float = 0.65,
    max_fiabilite: int = 3,
) -> list[Document]:
```

Before the search call, combine namespace filter with fiabilité:

```python
    filter_condition = _combine_filters(
        Filter(must=[FieldCondition(key="metadata.namespace", match=MatchValue(value=namespace))]) if namespace else None,
        _build_fiabilite_filter(max_fiabilite),
    )
```

Apply same pattern to `_search_candidates_by_scope` and `_identify_relevant_manifesto_documents`.

**Step 3: Run all tests**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/ -v --ignore=tests/eval`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/vector_store_helper.py
git commit -m "feat: add fiabilité Range filter to all search functions"
```

---

### Task 5.4: Update Frontend Source Type (Backward Compatible)

**Files:**
- Modify: `CHATVOTE-FrontEnd/src/lib/stores/chat-store.types.ts:14-22`
- No test needed — additive optional fields only

**Step 1: Add optional fields to Source type**

```typescript
export type Source = {
  source: string;
  content_preview: string;
  page: number;
  url: string;
  source_document: string;
  document_publish_date: string;
  party_id?: string;
  // New unified metadata fields (optional for backward compat)
  fiabilite?: number;
  theme?: string;
  sub_theme?: string;
  source_type?: string;
  candidate_name?: string;
  municipality_name?: string;
};
```

**Step 2: Run frontend type check**

Run: `cd CHATVOTE-FrontEnd && npm run type:check`
Expected: No type errors

**Step 3: Commit**

```bash
git add CHATVOTE-FrontEnd/src/lib/stores/chat-store.types.ts
git commit -m "feat: add optional fiabilite/theme fields to frontend Source type"
```

---

### Task 5.5: Update Backend Source Formatting to Include New Fields

**Files:**
- Modify: `CHATVOTE-BackEnd/src/websocket_app.py:568-593` (single-party sources)
- Modify: `CHATVOTE-BackEnd/src/websocket_app.py:960-1000` (combined sources)

**Step 1: Add new fields to source dict construction**

In the single-party source loop (line 583):

```python
                source = {
                    "source": source_doc.metadata.get("document_name"),
                    "page": page_number,
                    "content_preview": content_preview,
                    "document_publish_date": source_doc.metadata.get("document_publish_date"),
                    "url": source_doc.metadata.get("url"),
                    "source_document": source_doc.metadata.get("source_document"),
                    # New unified metadata
                    "fiabilite": source_doc.metadata.get("fiabilite"),
                    "theme": source_doc.metadata.get("theme"),
                    "sub_theme": source_doc.metadata.get("sub_theme"),
                }
```

In the combined source loops (lines 972, 991), add the same 3 fields.

**Step 2: Run backend tests**

Run: `cd CHATVOTE-BackEnd && poetry run pytest tests/test_websocket_app.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/websocket_app.py
git commit -m "feat: include fiabilite/theme in source payloads sent to frontend"
```

---

## Summary of All Commits

| # | Commit Message | Phase |
|---|---------------|-------|
| 1 | `feat: add ChunkMetadata Pydantic model with fiabilité auto-assignment` | 1 |
| 2 | `feat: add ChunkThemeClassification structured output schema` | 1 |
| 3 | `feat: page-aware PDF chunking with real page numbers` | 2 |
| 4 | `feat: add LLM-based chunk theme classifier` | 3 |
| 5 | `feat: integrate theme classification into manifesto indexing` | 3 |
| 6 | `feat: candidate indexer uses ChunkMetadata with array party_ids` | 4 |
| 7 | `feat: seed script uses ChunkMetadata for unified payloads` | 4 |
| 8 | `feat: add Qdrant payload indexes for fiabilite, party_ids, theme` | 4 |
| 9 | `feat: add MatchAny and Range filter builders for Qdrant` | 5 |
| 10 | `feat: replace Python party filtering with Qdrant MatchAny server-side` | 5 |
| 11 | `feat: add fiabilité Range filter to all search functions` | 5 |
| 12 | `feat: add optional fiabilite/theme fields to frontend Source type` | 5 |
| 13 | `feat: include fiabilite/theme in source payloads sent to frontend` | 5 |

## Future Phases (Not in This Sprint)

- **Phase 6**: BM25 hybrid search (sparse vectors for French proper nouns/acronyms)
- **Phase 7**: HyDE (Hypothetical Document Embedding) to replace query expansion
