"""
Metadata quality evaluation tests.

Tests that chunk metadata is rich enough for source tracing and geographic
filtering. Uses GEval custom metrics to judge metadata completeness.

Run:
    poetry run deepeval test run tests/eval/test_metadata_quality.py -v
"""

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase


# ---------------------------------------------------------------------------
# Source Traceability — chunks carry enough metadata for verification
# ---------------------------------------------------------------------------

TRACEABILITY_CASES = [
    {
        "id": "rich_manifesto_metadata",
        "retrieval_context": [
            (
                "Vivre dans un environnement sain. Nous devons dépolluer notre environnement. "
                "[metadata: party_name=Les Écologistes, source_document=election_manifesto, "
                "fiabilite=2 (Official), document_name=Les Écologistes - Programme électoral, "
                "url=https://storage.example.com/eelv/programme.pdf, page=12, "
                "election_year=2026, municipality_name=Montcenis, "
                "municipality_postal_code=71710, nuance_politique=ECO]"
            ),
            (
                "Protéger nos ressources en eau face aux pénuries. "
                "[metadata: party_name=Place Publique, source_document=election_manifesto, "
                "fiabilite=2 (Official), document_name=Place Publique - Programme électoral, "
                "url=https://storage.example.com/pp/programme.pdf, page=28, "
                "election_year=2026, epci_nom=CC du Grand Autunois Morvan]"
            ),
        ],
    },
    {
        "id": "rich_candidate_metadata",
        "retrieval_context": [
            (
                "Jean Dupont propose un plan de rénovation énergétique des bâtiments publics. "
                "[metadata: candidate_name=Jean Dupont, source_document=candidate_website_programme, "
                "fiabilite=2 (Official), url=https://jeandupont.fr/programme, "
                "municipality_name=Montcenis, municipality_code=71302, "
                "is_tete_de_liste=true, nuance_politique=DVC, is_incumbent=false]"
            ),
        ],
    },
    {
        "id": "poor_metadata_should_fail",
        "retrieval_context": [
            "Nous devons dépolluer notre environnement.",
            "Protéger nos ressources en eau.",
            "Plan de rénovation énergétique.",
        ],
        "should_fail": True,
    },
]


@pytest.mark.parametrize(
    "case",
    TRACEABILITY_CASES,
    ids=lambda c: c["id"],
)
def test_metadata_source_traceability(case, metadata_source_traceability_metric):
    """Test that chunks with rich metadata score higher on traceability."""
    test_case = LLMTestCase(
        input="Quelles sont les propositions environnementales ?",
        actual_output="",
        retrieval_context=case["retrieval_context"],
    )

    if case.get("should_fail"):
        metadata_source_traceability_metric.measure(test_case)
        assert metadata_source_traceability_metric.score < metadata_source_traceability_metric.threshold, (
            f"Expected low score for bad metadata, got {metadata_source_traceability_metric.score}"
        )
    else:
        assert_test(test_case, [metadata_source_traceability_metric])


# ---------------------------------------------------------------------------
# Geographic Relevance — retrieval matches geographic context in query
# ---------------------------------------------------------------------------

GEOGRAPHIC_CASES = [
    {
        "id": "matching_commune",
        "input": "Quelles sont les propositions pour Montcenis ?",
        "retrieval_context": [
            (
                "Rénovation de l'école primaire et création d'un espace vert. "
                "[metadata: municipality_name=Montcenis, municipality_postal_code=71710, "
                "epci_nom=CC du Grand Autunois Morvan, party_name=Montcenis Demain]"
            ),
            (
                "Amélioration du réseau d'eau potable pour le bourg. "
                "[metadata: municipality_name=Montcenis, municipality_code=71302, "
                "candidate_name=Marie Dupont, is_tete_de_liste=true]"
            ),
        ],
    },
    {
        "id": "wrong_commune_should_fail",
        "input": "Quelles sont les propositions pour Montcenis ?",
        "retrieval_context": [
            (
                "Construction d'un nouveau tramway pour la métropole. "
                "[metadata: municipality_name=Lyon, municipality_postal_code=69001]"
            ),
            (
                "Réaménagement des quais du Rhône. "
                "[metadata: municipality_name=Lyon, municipality_code=69123]"
            ),
        ],
        "should_fail": True,
    },
]


@pytest.mark.parametrize(
    "case",
    GEOGRAPHIC_CASES,
    ids=lambda c: c["id"],
)
def test_metadata_geographic_relevance(case, metadata_geographic_relevance_metric):
    """Test that retrieval context matches the geographic scope of the question."""
    test_case = LLMTestCase(
        input=case["input"],
        actual_output="",
        retrieval_context=case["retrieval_context"],
    )

    if case.get("should_fail"):
        metadata_geographic_relevance_metric.measure(test_case)
        assert metadata_geographic_relevance_metric.score < metadata_geographic_relevance_metric.threshold, (
            f"Expected low score for wrong commune, got {metadata_geographic_relevance_metric.score}"
        )
    else:
        assert_test(test_case, [metadata_geographic_relevance_metric])


# ---------------------------------------------------------------------------
# Source Attribution with metadata — enhanced test using new fields
# ---------------------------------------------------------------------------

ATTRIBUTION_WITH_METADATA_CASES = [
    {
        "id": "attribution_with_full_metadata",
        "input": "Que propose Montcenis Demain pour l'environnement ?",
        "actual_output": (
            "Selon le programme de Montcenis Demain (page 4), la liste menée par "
            "Marie Dupont (DVC) propose un plan de rénovation énergétique des "
            "bâtiments communaux et la création d'un parc naturel intercommunal "
            "en coordination avec la CC du Grand Autunois Morvan. "
            "[Source: programme officiel, fiabilité: Officiel]"
        ),
        "retrieval_context": [
            (
                "Plan de rénovation énergétique des bâtiments communaux. Création d'un "
                "parc naturel intercommunal. "
                "[metadata: party_name=Montcenis Demain, candidate_name=Marie Dupont, "
                "source_document=election_manifesto, fiabilite=2, page=4, "
                "municipality_name=Montcenis, municipality_postal_code=71710, "
                "nuance_politique=DVC, epci_nom=CC du Grand Autunois Morvan, "
                "is_tete_de_liste=true, election_year=2026]"
            ),
        ],
    },
]


@pytest.mark.parametrize(
    "case",
    ATTRIBUTION_WITH_METADATA_CASES,
    ids=lambda c: c["id"],
)
def test_source_attribution_with_metadata(case, source_attribution_metric):
    """Test that responses leveraging rich metadata produce better source attribution."""
    test_case = LLMTestCase(
        input=case["input"],
        actual_output=case["actual_output"],
        retrieval_context=case["retrieval_context"],
    )

    assert_test(test_case, [source_attribution_metric])
