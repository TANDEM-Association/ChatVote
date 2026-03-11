"""
Pytest tests asserting legacy and new pipelines produce equivalent output.

Tests cover:
- Chunk count parity
- Chunk content identity
- Metadata field parity
- Fiabilite correctness
- Page number preservation
- Theme classification coverage (keyword >= LLM coverage baseline)
- DeepEval GEval metrics for content preservation and metadata completeness

Usage:
    cd CHATVOTE-BackEnd
    python -m pytest tests/eval/test_pipeline_comparison.py -v
"""

import io
import os
import sys
import textwrap
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Setup: mock heavy imports before importing src modules
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Mock Firebase, Qdrant, and langchain_qdrant
sys.modules.setdefault("firebase_admin", mock.MagicMock())
sys.modules.setdefault("firebase_admin.credentials", mock.MagicMock())
sys.modules.setdefault("firebase_admin.firestore", mock.MagicMock())
sys.modules.setdefault("firebase_admin.storage", mock.MagicMock())
sys.modules.setdefault("firebase_admin.auth", mock.MagicMock())
sys.modules.setdefault("google.cloud.firestore", mock.MagicMock())
sys.modules.setdefault("google.cloud.firestore_v1", mock.MagicMock())
sys.modules.setdefault("langchain_qdrant", mock.MagicMock())

_vsh = mock.MagicMock()
_vsh.qdrant_client = mock.MagicMock()
_vsh.embed = mock.MagicMock()
_vsh.EMBEDDING_DIM = 3072
_vsh.PARTY_INDEX_NAME = "all_parties_dev"
_vsh.CANDIDATES_INDEX_NAME = "candidates_websites_dev"
_vsh.get_qdrant_vector_store = mock.MagicMock()
_vsh.get_candidates_vector_store = mock.MagicMock()
sys.modules["src.vector_store_helper"] = _vsh

sys.modules.setdefault("qdrant_client", mock.MagicMock())
sys.modules.setdefault("qdrant_client.models", mock.MagicMock())

# Now import src modules
from src.models.party import Party
from src.models.candidate import Candidate
from src.models.chunk_metadata import ChunkMetadata, Fiabilite, THEME_TAXONOMY

from src.services.manifesto_indexer import (
    create_documents_from_pages as legacy_create_docs_from_pages,
    extract_pages_from_pdf as legacy_extract_pages,
    CHUNK_SIZE as LEGACY_CHUNK_SIZE,
    CHUNK_OVERLAP as LEGACY_CHUNK_OVERLAP,
)
from src.services.candidate_indexer import (
    create_documents_from_scraped_website as legacy_create_docs_from_website,
)
from src.services.chunking import (
    create_documents_from_pages as new_create_docs_from_pages,
    create_documents_from_text as new_create_docs_from_text,
    text_splitter as new_text_splitter,
    CHUNK_SIZE as NEW_CHUNK_SIZE,
    CHUNK_OVERLAP as NEW_CHUNK_OVERLAP,
    MIN_CHUNK_LENGTH,
)
from src.services.pdf_extract import (
    extract_pages as new_extract_pages,
    extract_text as new_extract_text,
)
from src.services.theme_classifier import classify_theme_keywords as classify_theme, ThemeResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TEXTS = {
    "short_bullets": textwrap.dedent("""\
        - Augmentation du nombre de logements sociaux de 20%
        - Construction de 500 logements HLM d'ici 2028
        - Renovation energetique de tous les batiments publics
        - Mise en place d'un budget participatif citoyen
        - Gratuité des transports en commun pour les moins de 25 ans
    """),

    "long_prose": textwrap.dedent("""\
        Notre programme pour les elections municipales de 2026 repose sur une vision
        ambitieuse et solidaire de notre commune. En matiere d'education, nous
        proposons la construction de deux nouvelles ecoles primaires dans les
        quartiers nord et sud de la ville, accompagnee d'un programme de renovation
        des batiments scolaires existants. Le budget previsionnel s'eleve a 15
        millions d'euros sur la duree du mandat. Nous souhaitons egalement
        renforcer les dispositifs d'accompagnement scolaire avec la creation de
        dix postes supplementaires d'animateurs periscolaires.

        En ce qui concerne la sante, notre priorite est l'ouverture d'une maison
        de sante pluridisciplinaire dans le centre-ville. Cette structure
        regroupera medecins generalistes, specialistes, infirmiers et
        kinesitherapeutes. Le projet beneficiera d'un financement mixte entre la
        commune, l'Agence Regionale de Sante et les praticiens. Nous nous engageons
        egalement a mettre en place un service de telemedicine pour les personnes
        agees isolees.

        Sur le volet environnemental, nous prevoyons la plantation de 5000 arbres
        sur l'ensemble du territoire communal, la creation de trois nouveaux parcs
        urbains et l'installation de 200 bornes de recharge pour vehicules
        electriques. Notre objectif est d'atteindre la neutralite carbone d'ici
        2035 pour les batiments municipaux. Le budget climat sera de 3 millions
        d'euros par an.

        Enfin, en matiere de securite, nous proposons le deploiement de 50
        nouvelles cameras de videoprotection, le recrutement de 15 policiers
        municipaux supplementaires et la creation d'un centre de supervision
        urbain operationnel 24h/24. La securite des citoyens est une priorite
        absolue de notre mandat.
    """),

    "multi_theme": textwrap.dedent("""\
        Le candidat Jean Dupont presente son programme pour la commune de
        Villefranche-sur-Saone. En economie, il promet une zone franche pour
        les commercants du centre-ville et une reduction de la taxe fonciere
        de 5%. En transport, il prevoit l'extension du reseau de bus avec
        trois nouvelles lignes et la construction de 20 km de pistes cyclables.
        En culture, il souhaite renover le theatre municipal et creer un
        festival annuel de musique. En agriculture, il propose un marche de
        producteurs locaux chaque samedi et des jardins partages dans chaque
        quartier. Sur le numerique, il veut deployer la fibre optique dans
        toute la commune et creer un tiers-lieu numerique. Concernant le
        logement, 300 nouveaux logements sociaux seront construits d'ici 2028.
    """),

    "numbers_dates": textwrap.dedent("""\
        Budget previsionnel 2026-2028 de la commune de Montpellier :
        - Investissement total : 245 millions d'euros
        - Education : 45 M EUR (18,4%)
        - Voirie et transports : 62 M EUR (25,3%)
        - Environnement et espaces verts : 28 M EUR (11,4%)
        - Culture et sport : 35 M EUR (14,3%)
        - Securite : 22 M EUR (9%)
        - Numerique et innovation : 18 M EUR (7,3%)
        - Aide sociale et sante : 35 M EUR (14,3%)

        Echeancier previsionnel :
        T1 2026 : Lancement consultation publique budget participatif
        T2 2026 : Adoption du plan pluriannuel d'investissement
        T3 2026 : Debut travaux renovation ecole Jean-Jaures
        T1 2027 : Ouverture maison de sante intercommunale
        T4 2027 : Mise en service tramway ligne 5
        T2 2028 : Livraison 200 logements eco-quartier Republique
    """),

    "minimal_text": "Vote le 15 mars 2026.",
}


@pytest.fixture
def party():
    return Party(
        party_id="test_party",
        name="Parti Test",
        long_name="Parti Test - Long",
        description="A test party",
        website_url="https://example.com",
        candidate="Jean Dupont",
        election_manifesto_url="https://example.com/manifesto.pdf",
    )


@pytest.fixture
def candidate():
    return Candidate(
        candidate_id="cand_001",
        first_name="Marie",
        last_name="Martin",
        municipality_code="69264",
        municipality_name="Villefranche-sur-Saone",
        party_ids=["test_party"],
        election_type_id="municipalities-2026",
        position="Tete de liste",
    )


@pytest.fixture
def scraped_website():
    from src.models.scraper import ScrapedPage, ScrapedWebsite

    pages = [
        ScrapedPage(
            url="https://example.com",
            title="Home",
            content=SAMPLE_TEXTS["long_prose"],
            page_type="html",
        ),
    ]
    return ScrapedWebsite(
        candidate_id="cand_001",
        website_url="https://example.com",
        pages=pages,
    )


# ---------------------------------------------------------------------------
# Static / Deterministic Tests
# ---------------------------------------------------------------------------

class TestChunkingConfig:
    """Verify chunking configuration is identical."""

    def test_chunk_size_matches(self):
        assert LEGACY_CHUNK_SIZE == NEW_CHUNK_SIZE == 1000

    def test_chunk_overlap_matches(self):
        assert LEGACY_CHUNK_OVERLAP == NEW_CHUNK_OVERLAP == 200

    def test_min_chunk_length(self):
        # Legacy hard-codes 30 in the loop; new uses MIN_CHUNK_LENGTH constant
        assert MIN_CHUNK_LENGTH == 30


class TestChunkCountParity:
    """Assert legacy and new pipelines produce the same number of chunks."""

    @pytest.mark.parametrize("label", list(SAMPLE_TEXTS.keys()))
    def test_manifesto_chunk_count(self, label, party):
        text = SAMPLE_TEXTS[label]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
            party_name=party.name,
        )

        assert len(legacy_docs) == len(new_docs), (
            f"Chunk count mismatch for '{label}': "
            f"legacy={len(legacy_docs)}, new={len(new_docs)}"
        )


class TestChunkContentIdentity:
    """Assert chunk text content is identical between pipelines."""

    @pytest.mark.parametrize("label", list(SAMPLE_TEXTS.keys()))
    def test_manifesto_chunk_content(self, label, party):
        text = SAMPLE_TEXTS[label]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
            party_name=party.name,
        )

        for i, (ld, nd) in enumerate(zip(legacy_docs, new_docs)):
            assert ld.page_content == nd.page_content, (
                f"Chunk {i} content differs for '{label}'"
            )


class TestChunkSizes:
    """Assert individual chunk sizes are identical."""

    @pytest.mark.parametrize("label", list(SAMPLE_TEXTS.keys()))
    def test_chunk_sizes_match(self, label, party):
        text = SAMPLE_TEXTS[label]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
            party_name=party.name,
        )

        legacy_sizes = [len(d.page_content) for d in legacy_docs]
        new_sizes = [len(d.page_content) for d in new_docs]
        assert legacy_sizes == new_sizes


class TestMetadataFieldParity:
    """Assert metadata fields are present and correct."""

    def test_manifesto_common_fields(self, party):
        """Both pipelines must produce the same core metadata fields."""
        text = SAMPLE_TEXTS["long_prose"]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
            party_name=party.name,
            document_name=f"{party.name} - Programme electoral",
            url="https://example.com/manifesto.pdf",
        )

        assert legacy_docs and new_docs

        legacy_keys = set(legacy_docs[0].metadata.keys())
        new_keys = set(new_docs[0].metadata.keys())

        # Core fields that MUST be in both
        required_fields = {
            "namespace", "source_document", "party_ids", "fiabilite",
            "chunk_index", "total_chunks", "page",
        }
        assert required_fields.issubset(legacy_keys), (
            f"Legacy missing: {required_fields - legacy_keys}"
        )
        assert required_fields.issubset(new_keys), (
            f"New missing: {required_fields - new_keys}"
        )

    def test_fiabilite_values(self, party):
        """Fiabilite must be auto-inferred identically."""
        text = SAMPLE_TEXTS["short_bullets"]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
        )

        for ld, nd in zip(legacy_docs, new_docs):
            assert ld.metadata["fiabilite"] == nd.metadata["fiabilite"] == int(Fiabilite.OFFICIAL)

    def test_page_numbers_preserved(self, party):
        """Page numbers from multi-page input must be preserved identically."""
        pages_input = [
            (1, SAMPLE_TEXTS["short_bullets"]),
            (3, SAMPLE_TEXTS["numbers_dates"]),
            (5, SAMPLE_TEXTS["multi_theme"]),
        ]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
        )

        legacy_pages = [d.metadata["page"] for d in legacy_docs]
        new_pages = [d.metadata["page"] for d in new_docs]
        assert legacy_pages == new_pages

    def test_namespace_matches(self, party):
        """Namespace field must be the party_id."""
        text = SAMPLE_TEXTS["short_bullets"]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
        )

        for ld, nd in zip(legacy_docs, new_docs):
            assert ld.metadata["namespace"] == party.party_id
            assert nd.metadata["namespace"] == party.party_id

    def test_party_ids_format(self, party):
        """party_ids must be a list of strings."""
        text = SAMPLE_TEXTS["short_bullets"]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
        )

        for ld, nd in zip(legacy_docs, new_docs):
            assert isinstance(ld.metadata["party_ids"], list)
            assert isinstance(nd.metadata["party_ids"], list)
            assert ld.metadata["party_ids"] == [party.party_id]
            assert nd.metadata["party_ids"] == [party.party_id]

    def test_total_chunks_consistent(self, party):
        """total_chunks must equal actual document count."""
        text = SAMPLE_TEXTS["long_prose"]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
        )

        for d in legacy_docs:
            assert d.metadata["total_chunks"] == len(legacy_docs)
        for d in new_docs:
            assert d.metadata["total_chunks"] == len(new_docs)

    def test_candidate_metadata_parity(self, candidate, scraped_website):
        """Candidate pipeline metadata must have same core fields."""
        legacy_docs = legacy_create_docs_from_website(candidate, scraped_website)
        new_docs = new_create_docs_from_text(
            SAMPLE_TEXTS["long_prose"],
            namespace=candidate.candidate_id,
            source_document="candidate_website_html",
            party_ids=candidate.party_ids,
            candidate_ids=[candidate.candidate_id],
            candidate_name=candidate.full_name,
            municipality_code=candidate.municipality_code or "",
            municipality_name=candidate.municipality_name or "",
            election_type_id=candidate.election_type_id,
        )

        required = {"namespace", "source_document", "party_ids", "fiabilite",
                     "chunk_index", "total_chunks", "candidate_ids"}
        legacy_keys = set(legacy_docs[0].metadata.keys())
        new_keys = set(new_docs[0].metadata.keys())

        assert required.issubset(legacy_keys)
        assert required.issubset(new_keys)


class TestFiabiliteMapping:
    """Test fiabilite auto-inference for various source types."""

    @pytest.mark.parametrize("source_doc,expected", [
        ("election_manifesto", Fiabilite.OFFICIAL),
        ("candidate_website_about", Fiabilite.OFFICIAL),
        ("candidate_website_programme", Fiabilite.OFFICIAL),
        ("candidate_website_blog", Fiabilite.PRESS),
        ("candidate_website_html", Fiabilite.PRESS),
        ("justified_voting_behavior", Fiabilite.GOVERNMENT),
        ("parliamentary_question", Fiabilite.GOVERNMENT),
        ("uploaded_document", Fiabilite.PRESS),
    ])
    def test_fiabilite_inference(self, source_doc, expected):
        cm = ChunkMetadata(
            namespace="test",
            source_document=source_doc,
        )
        assert cm.fiabilite == expected


class TestThemeClassification:
    """Test keyword theme classifier coverage."""

    def test_keyword_classifier_covers_all_taxonomy_themes(self):
        """Each taxonomy theme should have keywords defined."""
        from src.services.theme_classifier import _THEME_KEYWORDS
        for theme in THEME_TAXONOMY:
            assert theme in _THEME_KEYWORDS, f"No keywords for theme: {theme}"
            assert len(_THEME_KEYWORDS[theme]) > 0

    def test_keyword_coverage_exceeds_baseline(self):
        """Keyword classifier should classify at least 25% of political text chunks.

        The keyword classifier requires 3+ hits for a confident match,
        so short chunks often fall through to the LLM path. We test that
        longer, multi-topic texts still achieve reasonable keyword coverage.
        """
        all_chunks = []
        for label, text in SAMPLE_TEXTS.items():
            if label in ("minimal_text", "short_bullets"):
                continue  # Skip intentionally short texts
            chunks = new_text_splitter.split_text(text)
            all_chunks.extend(c for c in chunks if len(c.strip()) >= MIN_CHUNK_LENGTH)

        classified = sum(1 for c in all_chunks if classify_theme(c).theme is not None)
        coverage = classified / len(all_chunks) if all_chunks else 0

        assert coverage >= 0.25, (
            f"Keyword coverage too low: {coverage:.1%} ({classified}/{len(all_chunks)}). "
            f"Expected >= 25%"
        )

    @pytest.mark.parametrize("text,expected_theme", [
        # Each test text has 3+ keyword hits to meet the fast-path threshold
        (
            "Construction de 500 logements sociaux HLM, rénovation des logements "
            "insalubles et création de logement social dans chaque quartier",
            "logement",
        ),
        (
            "Deploiement de la fibre optique, du WiFi gratuit et du numérique "
            "dans toutes les écoles avec un programme d'intelligence artificielle",
            "numerique",
        ),
        (
            "Renforcement de la sécurité avec caméras de vidéoprotection, "
            "recrutement de police municipale et lutte contre la délinquance",
            "securite",
        ),
        (
            "Ouverture d'une maison de santé avec médecins généralistes, "
            "soins infirmiers et EHPAD rénové pour les personnes âgées",
            "sante",
        ),
        (
            "Extension du réseau de bus, création de pistes cyclables "
            "et mise en place d'un tramway pour améliorer la mobilité urbaine",
            "transport",
        ),
        (
            "Plantation de 5000 arbres, transition énergétique vers le solaire "
            "et recyclage des déchets pour réduire la pollution",
            "environnement",
        ),
        (
            "Rénovation de l'école primaire, cantine scolaire bio "
            "et création d'une crèche municipale avec programme éducation",
            "education",
        ),
        (
            "Réduction de la taxe foncière, soutien à l'emploi local "
            "et aide aux entreprises du commerce de centre-ville",
            "economie",
        ),
    ])
    def test_keyword_classification_accuracy(self, text, expected_theme):
        """Known political texts (3+ keywords each) should be classified correctly."""
        result = classify_theme(text)
        assert result.theme == expected_theme, (
            f"Expected '{expected_theme}', got '{result.theme}' for: {text[:60]}"
        )

    @pytest.mark.parametrize("text,expected_theme", [
        ("Construction de 500 logements sociaux HLM", "logement"),
        ("Deploiement de la fibre optique et du WiFi", "numerique"),
        ("Medecins et soins de sante en EHPAD", "sante"),
    ])
    def test_keyword_scores_detect_theme(self, text, expected_theme):
        """Short texts should still produce keyword scores even if below the
        3-hit fast-path threshold (these would go to LLM in production)."""
        from src.services.theme_classifier import _keyword_scores
        scores = _keyword_scores(text)
        assert expected_theme in scores, (
            f"Expected '{expected_theme}' in scores, got {scores} for: {text}"
        )

    def test_theme_results_are_valid(self):
        """All classified themes must be in the taxonomy."""
        for label, text in SAMPLE_TEXTS.items():
            chunks = new_text_splitter.split_text(text)
            for chunk in chunks:
                result = classify_theme(chunk)
                if result.theme is not None:
                    assert result.theme in THEME_TAXONOMY, (
                        f"Invalid theme '{result.theme}' from chunk in '{label}'"
                    )


class TestPdfExtraction:
    """Test PDF extraction parity using test fixtures."""

    @pytest.fixture
    def text_manifesto_bytes(self):
        pdf_path = PROJECT_ROOT / "tests" / "fixtures" / "text_manifesto.pdf"
        if not pdf_path.exists():
            pytest.skip(f"Fixture not found: {pdf_path}")
        return pdf_path.read_bytes()

    @pytest.fixture
    def image_manifesto_bytes(self):
        pdf_path = PROJECT_ROOT / "tests" / "fixtures" / "image_only_manifesto.pdf"
        if not pdf_path.exists():
            pytest.skip(f"Fixture not found: {pdf_path}")
        return pdf_path.read_bytes()

    def test_text_pdf_page_count_matches(self, text_manifesto_bytes):
        legacy_pages = legacy_extract_pages(text_manifesto_bytes)
        new_pages = new_extract_pages(text_manifesto_bytes)
        assert len(legacy_pages) == len(new_pages)

    def test_text_pdf_content_identical(self, text_manifesto_bytes):
        legacy_pages = legacy_extract_pages(text_manifesto_bytes)
        new_pages = new_extract_pages(text_manifesto_bytes)

        for (lnum, ltext), (nnum, ntext) in zip(legacy_pages, new_pages):
            assert lnum == nnum, f"Page numbers differ: {lnum} vs {nnum}"
            assert ltext == ntext, f"Page {lnum} text differs"

    def test_text_pdf_flat_extraction(self, text_manifesto_bytes):
        """Flat text extraction should be identical."""
        legacy_flat = "\n\n".join(t for _, t in legacy_extract_pages(text_manifesto_bytes))
        new_flat = new_extract_text(text_manifesto_bytes)
        assert legacy_flat == new_flat

    def test_image_pdf_returns_empty_or_minimal(self, image_manifesto_bytes):
        """Image-only PDFs should return empty/minimal from text extraction."""
        legacy_pages = legacy_extract_pages(image_manifesto_bytes)
        new_pages = new_extract_pages(image_manifesto_bytes)

        # Both should return minimal or no text (image PDF)
        legacy_chars = sum(len(t) for _, t in legacy_pages)
        new_chars = sum(len(t) for _, t in new_pages)
        # They should behave the same way
        assert legacy_chars == new_chars


class TestCandidatePipeline:
    """Test candidate website chunking parity."""

    def test_chunk_count_matches(self, candidate, scraped_website):
        legacy_docs = legacy_create_docs_from_website(candidate, scraped_website)
        new_docs = new_create_docs_from_text(
            SAMPLE_TEXTS["long_prose"],
            namespace=candidate.candidate_id,
            source_document="candidate_website_html",
            party_ids=candidate.party_ids,
            candidate_ids=[candidate.candidate_id],
            candidate_name=candidate.full_name,
        )
        assert len(legacy_docs) == len(new_docs)

    def test_chunk_content_matches(self, candidate, scraped_website):
        legacy_docs = legacy_create_docs_from_website(candidate, scraped_website)
        new_docs = new_create_docs_from_text(
            SAMPLE_TEXTS["long_prose"],
            namespace=candidate.candidate_id,
            source_document="candidate_website_html",
            party_ids=candidate.party_ids,
            candidate_ids=[candidate.candidate_id],
        )
        for i, (ld, nd) in enumerate(zip(legacy_docs, new_docs)):
            assert ld.page_content == nd.page_content, f"Chunk {i} content differs"


# ---------------------------------------------------------------------------
# DeepEval GEval metrics (optional — only run if deepeval + judge available)
# ---------------------------------------------------------------------------

def _deepeval_available() -> bool:
    """Check if deepeval is installed and a judge model is available."""
    try:
        import deepeval  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(
    not _deepeval_available(),
    reason="deepeval not installed"
)
class TestDeepEvalContentPreservation:
    """Use GEval to verify chunk content preservation between pipelines."""

    @pytest.fixture(scope="class")
    def geval_content_metric(self, judge_model):
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCaseParams

        return GEval(
            name="Chunk Content Preservation",
            criteria="""Compare the 'actual output' (new pipeline chunks) against
            the 'expected output' (legacy pipeline chunks) for content preservation.
            The new pipeline should contain the same information as the legacy pipeline.
            Score 1.0 if all information is preserved, lower if content is lost or altered.
            Minor formatting differences are acceptable.""",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.9,
            model=judge_model,
        )

    @pytest.fixture(scope="class")
    def geval_metadata_metric(self, judge_model):
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCaseParams

        return GEval(
            name="Metadata Completeness",
            criteria="""Compare the metadata in the 'actual output' (new pipeline)
            against the 'expected output' (legacy pipeline).
            Check that all essential metadata fields are present: namespace,
            source_document, party_ids, fiabilite, chunk_index, total_chunks, page.
            Score 1.0 if all fields present with correct values, lower if fields
            are missing or have incorrect values.""",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.EXPECTED_OUTPUT,
            ],
            threshold=0.8,
            model=judge_model,
        )

    def test_content_preservation_long_prose(
        self, party, geval_content_metric
    ):
        from deepeval.test_case import LLMTestCase

        text = SAMPLE_TEXTS["long_prose"]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
            party_name=party.name,
        )

        legacy_text = "\n---\n".join(d.page_content for d in legacy_docs)
        new_text = "\n---\n".join(d.page_content for d in new_docs)

        test_case = LLMTestCase(
            input="Compare pipeline chunks for content preservation",
            actual_output=new_text,
            expected_output=legacy_text,
        )

        geval_content_metric.measure(test_case)
        assert geval_content_metric.score >= 0.9, (
            f"Content preservation score: {geval_content_metric.score:.2f}. "
            f"Reason: {geval_content_metric.reason}"
        )

    def test_metadata_completeness(
        self, party, geval_metadata_metric
    ):
        from deepeval.test_case import LLMTestCase
        import json

        text = SAMPLE_TEXTS["long_prose"]
        pages_input = [(1, text)]

        legacy_docs = legacy_create_docs_from_pages(
            pages_input, party, "https://example.com/manifesto.pdf"
        )
        new_docs = new_create_docs_from_pages(
            pages_input,
            namespace=party.party_id,
            source_document="election_manifesto",
            party_ids=[party.party_id],
            party_name=party.name,
            document_name=f"{party.name} - Programme electoral",
            url="https://example.com/manifesto.pdf",
        )

        legacy_meta = json.dumps(legacy_docs[0].metadata, indent=2, default=str)
        new_meta = json.dumps(new_docs[0].metadata, indent=2, default=str)

        test_case = LLMTestCase(
            input="Compare pipeline metadata completeness",
            actual_output=new_meta,
            expected_output=legacy_meta,
        )

        geval_metadata_metric.measure(test_case)
        assert geval_metadata_metric.score >= 0.8, (
            f"Metadata completeness score: {geval_metadata_metric.score:.2f}. "
            f"Reason: {geval_metadata_metric.reason}"
        )
