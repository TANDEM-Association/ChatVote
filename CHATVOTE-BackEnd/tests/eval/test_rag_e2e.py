"""
End-to-end RAG evaluation tests.

Runs the full pipeline: query improvement → retrieval → reranking → generation,
then evaluates the output against all metrics.

Requires: Qdrant running + LLM API key + Firestore (or emulator).

Run:
    poetry run deepeval test run tests/eval/test_rag_e2e.py -v
"""

import asyncio
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


_module_loop = None


def _get_loop():
    global _module_loop
    if _module_loop is None or _module_loop.is_closed():
        _module_loop = asyncio.new_event_loop()
    return _module_loop


def teardown_module(module):
    global _module_loop
    if _module_loop and not _module_loop.is_closed():
        _module_loop.close()
        _module_loop = None


def _skip_if_no_infra():
    """Skip if required infrastructure is not available."""
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    try:
        import urllib.request
        urllib.request.urlopen(qdrant_url, timeout=2)
    except Exception:
        pytest.skip(f"Qdrant not reachable at {qdrant_url}")

    if not any(
        os.environ.get(k) for k in ["GOOGLE_API_KEY", "OPENAI_API_KEY"]
    ):
        pytest.skip("No LLM API key set")


def _assert_sources_in_context(actual_output: str, retrieval_context: list[str], golden: dict):
    """Programmatic check: party names and source keywords from golden must appear
    in either the output or the retrieval context."""
    output_lower = actual_output.lower()
    context_joined = " ".join(retrieval_context).lower()

    # Check expected parties are mentioned in the output
    for party in golden.get("expected_parties", []):
        assert party.lower() in output_lower, (
            f"Expected party '{party}' not found in output: {actual_output[:200]}..."
        )

    # Check expected source keywords appear in retrieval context
    for keyword in golden.get("expected_source_keywords", []):
        assert keyword.lower() in context_joined, (
            f"Expected source keyword '{keyword}' not found in retrieval context"
        )


@pytest.fixture(scope="module")
def rag_pipeline():
    """Set up the full RAG pipeline components."""
    _skip_if_no_infra()

    os.environ.setdefault("ENV", "dev")

    from src.chatbot_async import (
        generate_improvement_rag_query,
        generate_streaming_chatbot_response,
        generate_streaming_chatbot_comparing_response,
    )
    from src.vector_store_helper import (
        identify_relevant_docs_with_llm_based_reranking,
    )
    from src.models.party import Party
    from src.models.general import LLMSize

    return {
        "improve_query": generate_improvement_rag_query,
        "retrieve_and_rerank": identify_relevant_docs_with_llm_based_reranking,
        "generate_single": generate_streaming_chatbot_response,
        "generate_comparing": generate_streaming_chatbot_comparing_response,
        "Party": Party,
        "LLMSize": LLMSize,
    }


async def _run_single_party_pipeline(pipeline, question: str, party_id: str) -> tuple:
    """Run the full single-party RAG pipeline, return (output, retrieval_context)."""
    Party = pipeline["Party"]
    LLMSize = pipeline["LLMSize"]

    party = Party(
        party_id=party_id, name=party_id, long_name=party_id,
        description="", website_url="", candidate="", election_manifesto_url="",
    )

    # Step 1: Improve query
    improved_query = await pipeline["improve_query"](
        responder=party,
        conversation_history="",
        last_user_message=question,
    )

    # Step 2: Retrieve + rerank
    docs = await pipeline["retrieve_and_rerank"](
        responder=party,
        rag_query=improved_query,
        chat_history="",
        user_message=question,
        n_docs=20,
    )

    retrieval_context = [doc.page_content for doc in docs]

    # Step 3: Generate
    stream = await pipeline["generate_single"](
        responder=party,
        conversation_history="",
        user_message=question,
        relevant_docs=docs,
        all_parties=[party],
        chat_response_llm_size=LLMSize.SMALL,
    )

    chunks = []
    async for chunk in stream:
        content = chunk.content if hasattr(chunk, "content") else str(chunk)
        chunks.append(content)

    return "".join(chunks), retrieval_context


async def _run_multi_party_pipeline(pipeline, question: str, party_ids: list[str]) -> tuple:
    """Run the full multi-party RAG pipeline, return (output, retrieval_context)."""
    Party = pipeline["Party"]
    LLMSize = pipeline["LLMSize"]

    parties = [
        Party(
            party_id=pid, name=pid, long_name=pid,
            description="", website_url="", candidate="", election_manifesto_url="",
        )
        for pid in party_ids
    ]

    all_docs = []
    for party in parties:
        improved_query = await pipeline["improve_query"](
            responder=party,
            conversation_history="",
            last_user_message=question,
        )
        docs = await pipeline["retrieve_and_rerank"](
            responder=party,
            rag_query=improved_query,
            chat_history="",
            user_message=question,
            n_docs=10,
        )
        all_docs.extend(docs)

    retrieval_context = [doc.page_content for doc in all_docs]

    # Group docs by party for the comparing pipeline
    # Qdrant stores party identifier in metadata.namespace
    docs_per_party = {}
    for p in parties:
        docs_per_party[p.party_id] = [
            d for d in all_docs
            if d.metadata.get("namespace") == p.party_id
            or d.metadata.get("party_id") == p.party_id
        ]

    stream = await pipeline["generate_comparing"](
        conversation_history="",
        user_message=question,
        relevant_docs=docs_per_party,
        relevant_parties=parties,
        chat_response_llm_size=LLMSize.SMALL,
    )

    chunks = []
    async for chunk in stream:
        content = chunk.content if hasattr(chunk, "content") else str(chunk)
        chunks.append(content)

    return "".join(chunks), retrieval_context


# ---------------------------------------------------------------------------
# Single-party E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "golden",
    _load_golden("single_party"),
    ids=lambda g: g.get("category", "unknown"),
)
def test_e2e_single_party(
    golden,
    rag_pipeline,
    faithfulness_metric,
    answer_relevancy_metric,
    contextual_recall_metric,
    source_attribution_metric,
):
    """Full E2E test for single-party questions with source attribution."""
    party_id = golden["party_ids"][0]

    loop = _get_loop()
    actual_output, retrieval_context = loop.run_until_complete(
        _run_single_party_pipeline(rag_pipeline, golden["input"], party_id)
    )

    # Programmatic source verification
    _assert_sources_in_context(actual_output, retrieval_context, golden)

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output=actual_output,
        expected_output=golden["expected_output"],
        retrieval_context=retrieval_context,
    )

    assert_test(
        test_case,
        [faithfulness_metric, answer_relevancy_metric, contextual_recall_metric,
         source_attribution_metric],
    )


# ---------------------------------------------------------------------------
# Multi-party E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "golden",
    _load_golden("multi_party_comparison"),
    ids=lambda g: g.get("category", "unknown"),
)
def test_e2e_multi_party(
    golden,
    rag_pipeline,
    faithfulness_metric,
    answer_relevancy_metric,
    multiparty_completeness_metric,
    source_attribution_metric,
):
    """Full E2E test for multi-party comparison questions."""
    loop = _get_loop()
    actual_output, retrieval_context = loop.run_until_complete(
        _run_multi_party_pipeline(rag_pipeline, golden["input"], golden["party_ids"])
    )

    # Programmatic: check all expected parties are mentioned
    _assert_sources_in_context(actual_output, retrieval_context, golden)

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output=actual_output,
        expected_output=golden["expected_output"],
        retrieval_context=retrieval_context,
    )

    assert_test(
        test_case,
        [faithfulness_metric, answer_relevancy_metric,
         multiparty_completeness_metric, source_attribution_metric],
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "golden",
    _load_golden("edge_cases"),
    ids=lambda g: g.get("category", "unknown"),
)
def test_e2e_edge_cases(
    golden,
    rag_pipeline,
    political_neutrality_metric,
):
    """E2E test for edge cases (refusals, off-topic, injection)."""
    if not golden.get("party_ids"):
        pytest.skip("Edge case without party_ids — tested in red_team tests")
    if len(golden["party_ids"]) > 1:
        pytest.skip("Multi-party edge case — single-party pipeline cannot test this")

    party_id = golden["party_ids"][0]

    loop = _get_loop()
    actual_output, retrieval_context = loop.run_until_complete(
        _run_single_party_pipeline(rag_pipeline, golden["input"], party_id)
    )

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output=actual_output,
        retrieval_context=retrieval_context,
    )

    assert_test(test_case, [political_neutrality_metric])
