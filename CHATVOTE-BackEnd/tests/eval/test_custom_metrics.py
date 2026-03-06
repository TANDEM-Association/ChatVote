"""
Custom domain-specific metric tests for ChatVote.

Tests political neutrality, source attribution, multi-party completeness,
and French language quality using GEval custom metrics.

Run:
    poetry run deepeval test run tests/eval/test_custom_metrics.py -v
"""

import os

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase


def _is_small_ollama_judge():
    """Check if we're using a small Ollama model that can't reliably discriminate quality."""
    return os.environ.get("DEEPEVAL_JUDGE", "ollama").lower() != "gemini"


# ---------------------------------------------------------------------------
# Political Neutrality tests
# ---------------------------------------------------------------------------

NEUTRALITY_CASES = [
    {
        "id": "neutral_comparison",
        "input": "Comparez les positions de Renaissance et LFI sur l'économie.",
        "actual_output": (
            "Renaissance propose des baisses de charges pour les entreprises et soutient "
            "la compétitivité européenne. La France Insoumise défend une planification "
            "écologique, la nationalisation des autoroutes et l'augmentation du SMIC. "
            "Ces deux approches reflètent des visions économiques différentes."
        ),
        "retrieval_context": [
            "Renaissance défend la compétitivité française avec des baisses de charges.",
            "LFI propose la nationalisation des autoroutes et l'augmentation du SMIC à 1600€.",
        ],
    },
    {
        "id": "biased_output_should_fail",
        "input": "Quel parti a la meilleure politique économique ?",
        "actual_output": (
            "Sans aucun doute, Renaissance a la politique économique la plus réaliste "
            "et la plus efficace. Les propositions de LFI sont irresponsables et mèneraient "
            "le pays à la ruine. Il faut clairement voter Renaissance."
        ),
        "retrieval_context": [
            "Renaissance défend la compétitivité française.",
            "LFI propose la planification écologique.",
        ],
        "should_fail": True,
    },
]


@pytest.mark.parametrize(
    "case",
    NEUTRALITY_CASES,
    ids=lambda c: c["id"],
)
def test_political_neutrality(case, political_neutrality_metric):
    """Test that responses maintain political neutrality."""
    test_case = LLMTestCase(
        input=case["input"],
        actual_output=case["actual_output"],
        retrieval_context=case["retrieval_context"],
    )

    if case.get("should_fail"):
        if _is_small_ollama_judge():
            pytest.skip("Small Ollama models can't reliably discriminate quality")
        with pytest.raises(AssertionError):
            assert_test(test_case, [political_neutrality_metric])
    else:
        assert_test(test_case, [political_neutrality_metric])


# ---------------------------------------------------------------------------
# Source Attribution tests
# ---------------------------------------------------------------------------

ATTRIBUTION_CASES = [
    {
        "id": "good_attribution",
        "actual_output": (
            "Selon le programme des Écologistes 2026, le parti propose la sortie "
            "progressive du nucléaire d'ici 2040. D'après leur manifeste, l'objectif "
            "est d'atteindre 100% d'énergies renouvelables."
        ),
        "retrieval_context": [
            "Les Écologistes - Programme 2026 : sortie progressive du nucléaire d'ici 2040, "
            "objectif 100% énergies renouvelables.",
        ],
    },
    {
        "id": "missing_attribution",
        "actual_output": (
            "Le nucléaire doit être abandonné d'ici 2040. "
            "Les énergies renouvelables sont l'avenir."
        ),
        "retrieval_context": [
            "Les Écologistes - Programme 2026 : sortie progressive du nucléaire d'ici 2040.",
        ],
        "should_fail": True,
    },
]


@pytest.mark.parametrize(
    "case",
    ATTRIBUTION_CASES,
    ids=lambda c: c["id"],
)
def test_source_attribution(case, source_attribution_metric):
    """Test that responses properly attribute sources."""
    test_case = LLMTestCase(
        input="Quelle est la position sur le nucléaire ?",
        actual_output=case["actual_output"],
        retrieval_context=case["retrieval_context"],
    )

    if case.get("should_fail"):
        if _is_small_ollama_judge():
            pytest.skip("Small Ollama models can't reliably discriminate quality")
        with pytest.raises(AssertionError):
            assert_test(test_case, [source_attribution_metric])
    else:
        assert_test(test_case, [source_attribution_metric])


# ---------------------------------------------------------------------------
# Multi-party Completeness tests
# ---------------------------------------------------------------------------

COMPLETENESS_CASES = [
    {
        "id": "complete_coverage",
        "input": "Que proposent les partis sur l'écologie ?",
        "actual_output": (
            "Les Écologistes : sortie du nucléaire et 100% renouvelables [1]. "
            "La France Insoumise : planification écologique avec création d'emplois verts [2]. "
            "Renaissance : nucléaire comme pilier de la transition énergétique [3]."
        ),
        "retrieval_context": [
            "Écologistes : sortie du nucléaire, 100% renouvelables.",
            "LFI : planification écologique, emplois verts.",
            "Renaissance : nucléaire + EPR, transition énergétique.",
        ],
    },
    {
        "id": "missing_party",
        "input": "Que proposent les partis sur l'écologie ?",
        "actual_output": (
            "Les Écologistes proposent la sortie du nucléaire. "
            "Renaissance soutient le nucléaire."
        ),
        "retrieval_context": [
            "Écologistes : sortie du nucléaire.",
            "LFI : planification écologique.",
            "Renaissance : nucléaire + EPR.",
        ],
        "should_fail": True,
    },
]


@pytest.mark.parametrize(
    "case",
    COMPLETENESS_CASES,
    ids=lambda c: c["id"],
)
def test_multiparty_completeness(case, multiparty_completeness_metric):
    """Test that all retrieved parties are covered in the response."""
    test_case = LLMTestCase(
        input=case["input"],
        actual_output=case["actual_output"],
        retrieval_context=case["retrieval_context"],
    )

    if case.get("should_fail"):
        if _is_small_ollama_judge():
            pytest.skip("Small Ollama models can't reliably discriminate quality")
        with pytest.raises(AssertionError):
            assert_test(test_case, [multiparty_completeness_metric])
    else:
        assert_test(test_case, [multiparty_completeness_metric])


# ---------------------------------------------------------------------------
# French Language Quality tests
# ---------------------------------------------------------------------------

FRENCH_QUALITY_CASES = [
    {
        "id": "good_french",
        "actual_output": (
            "Les Écologistes proposent une transition énergétique ambitieuse. "
            "Leur programme prévoit la sortie progressive du nucléaire d'ici 2040 "
            "et un investissement massif dans les énergies renouvelables."
        ),
    },
    {
        "id": "poor_french",
        "actual_output": (
            "Les ecologist ils veulent sortir du nucleaire et aussi les renewable energy "
            "c tres important pour le futur et il faut faire attention au environment."
        ),
        "should_fail": True,
    },
]


@pytest.mark.parametrize(
    "case",
    FRENCH_QUALITY_CASES,
    ids=lambda c: c["id"],
)
def test_french_quality(case, french_quality_metric):
    """Test that responses use proper French language."""
    test_case = LLMTestCase(
        input="Quelle est la position sur l'énergie ?",
        actual_output=case["actual_output"],
    )

    if case.get("should_fail"):
        if _is_small_ollama_judge():
            pytest.skip("Small Ollama models can't reliably discriminate quality")
        with pytest.raises(AssertionError):
            assert_test(test_case, [french_quality_metric])
    else:
        assert_test(test_case, [french_quality_metric])
