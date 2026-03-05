"""
RAG Generator evaluation tests.

Tests generation quality by providing pre-built retrieval context
and measuring faithfulness, relevancy, and hallucination.

Run:
    poetry run deepeval test run tests/eval/test_rag_generator.py -v
"""

import json
import os
import sys
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATASETS_DIR = Path(__file__).parent / "datasets"


def _load_golden(category: str) -> list[dict]:
    data = json.loads((DATASETS_DIR / "golden_questions.json").read_text())
    return data.get(category, [])


def _skip_if_no_llm():
    """Skip if no LLM API key is available."""
    if not any(
        os.environ.get(k) for k in ["GOOGLE_API_KEY", "OPENAI_API_KEY", "AZURE_API_KEY"]
    ):
        pytest.skip("No LLM API key set — cannot run generator tests")


# ---------------------------------------------------------------------------
# Generator test with mock context (no Qdrant needed)
# ---------------------------------------------------------------------------

# Sample contexts simulating retrieved manifesto chunks
MOCK_CONTEXTS = {
    "europe-ecologie-les-verts": [
        "Les Écologistes - Programme 2026 : Nous proposons la sortie progressive du nucléaire "
        "d'ici 2040 et un investissement massif dans les énergies renouvelables : éolien, solaire, "
        "géothermie. Notre objectif est d'atteindre 100% d'énergies renouvelables.",
        "Politique environnementale des Écologistes : interdiction du glyphosate, promotion de "
        "l'agriculture biologique, création de 500 000 emplois verts dans la rénovation thermique.",
    ],
    "la-france-insoumise": [
        "Programme LFI - Retraites : La France Insoumise propose le rétablissement du droit à "
        "la retraite à 60 ans, avec 40 annuités de cotisation. Nous défendons un système de "
        "retraite par répartition renforcé, avec une pension minimale au niveau du SMIC.",
        "La France Insoumise - Économie : planification écologique, nationalisation des autoroutes "
        "et des énergies, augmentation du SMIC à 1 600€ net, blocage des prix de première nécessité.",
    ],
    "renaissance": [
        "Renaissance - Politique économique : Nous défendons la compétitivité française en Europe "
        "à travers des baisses de charges pour les entreprises, le soutien à l'innovation et la "
        "réforme du marché du travail. L'objectif est le plein emploi d'ici 2027.",
        "Renaissance soutient le nucléaire comme pilier de la transition énergétique française, "
        "avec la construction de 6 nouveaux EPR et le développement du petit nucléaire modulaire.",
    ],
}


@pytest.fixture(scope="module")
def llm_generator():
    """Import the chatbot generator (requires LLM API key)."""
    _skip_if_no_llm()

    os.environ.setdefault("ENV", "dev")

    from src.chatbot_async import generate_streaming_chatbot_response
    from src.models.party import Party
    from src.models.general import LLMSize
    from langchain_core.documents import Document

    return generate_streaming_chatbot_response, Party, LLMSize, Document


def _build_docs(party_id: str) -> list:
    """Build LangChain Documents from mock contexts."""
    from langchain_core.documents import Document

    contexts = MOCK_CONTEXTS.get(party_id, [])
    return [
        Document(
            page_content=ctx,
            metadata={"party_id": party_id, "source_document": "test_manifesto"},
        )
        for ctx in contexts
    ]


@pytest.mark.parametrize(
    "golden",
    _load_golden("single_party"),
    ids=lambda g: g.get("category", "unknown"),
)
def test_generator_faithfulness(
    golden,
    llm_generator,
    faithfulness_metric,
    answer_relevancy_metric,
):
    """Test that generated responses are faithful to retrieved context."""
    generate_fn, Party, LLMSize, Document = llm_generator

    party_id = golden["party_ids"][0]
    party = Party(party_id=party_id, name=party_id, long_name=party_id)

    docs = _build_docs(party_id)
    retrieval_context = [doc.page_content for doc in docs]

    if not retrieval_context:
        pytest.skip(f"No mock context for party {party_id}")

    import asyncio

    async def _generate():
        stream = await generate_fn(
            responder=party,
            conversation_history="",
            user_message=golden["input"],
            relevant_docs=docs,
            all_parties=[party],
            chat_response_llm_size=LLMSize.SMALL,
        )
        chunks = []
        async for chunk in stream:
            chunks.append(chunk.content if hasattr(chunk, "content") else str(chunk))
        return "".join(chunks)

    loop = asyncio.new_event_loop()
    actual_output = loop.run_until_complete(_generate())
    loop.close()

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output=actual_output,
        expected_output=golden["expected_output"],
        retrieval_context=retrieval_context,
    )

    assert_test(test_case, [faithfulness_metric, answer_relevancy_metric])


# ---------------------------------------------------------------------------
# Standalone generator tests with static input/output (no LLM call needed)
# ---------------------------------------------------------------------------

STATIC_TEST_CASES = [
    {
        "input": "Quelle est la position des Écologistes sur le nucléaire ?",
        "actual_output": (
            "Les Écologistes proposent une sortie progressive du nucléaire d'ici 2040 "
            "et un investissement massif dans les énergies renouvelables comme l'éolien, "
            "le solaire et la géothermie. Leur objectif est d'atteindre 100% d'énergies "
            "renouvelables. (Source : Programme des Écologistes 2026)"
        ),
        "retrieval_context": MOCK_CONTEXTS["europe-ecologie-les-verts"],
        "expected_output": "Les Écologistes sont opposés au nucléaire et proposent une transition vers les énergies renouvelables.",
    },
    {
        "input": "Que propose LFI pour les retraites ?",
        "actual_output": (
            "La France Insoumise propose le rétablissement du droit à la retraite à 60 ans, "
            "avec 40 annuités de cotisation. Le programme défend un système de retraite par "
            "répartition renforcé, avec une pension minimale au niveau du SMIC. "
            "(Source : Programme LFI)"
        ),
        "retrieval_context": MOCK_CONTEXTS["la-france-insoumise"],
        "expected_output": "LFI propose la retraite à 60 ans avec un système par répartition renforcé.",
    },
]


@pytest.mark.parametrize(
    "case",
    STATIC_TEST_CASES,
    ids=["ecologistes_nucleaire", "lfi_retraites"],
)
def test_generator_static_faithfulness(
    case,
    faithfulness_metric,
    answer_relevancy_metric,
):
    """Test faithfulness with pre-built static examples (no LLM call needed)."""
    test_case = LLMTestCase(
        input=case["input"],
        actual_output=case["actual_output"],
        expected_output=case["expected_output"],
        retrieval_context=case["retrieval_context"],
    )

    assert_test(test_case, [faithfulness_metric, answer_relevancy_metric])
