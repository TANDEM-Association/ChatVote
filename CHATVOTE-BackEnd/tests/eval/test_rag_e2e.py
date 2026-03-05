"""
End-to-end RAG evaluation tests.

Runs the full pipeline: query improvement → retrieval → reranking → generation,
then evaluates the output against all metrics.

Requires: Qdrant running + LLM API key + Firestore (or emulator).

Run:
    poetry run deepeval test run tests/eval/test_rag_e2e.py -v
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

    party = Party(party_id=party_id, name=party_id, long_name=party_id)

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
):
    """Full E2E test for single-party questions."""
    import asyncio

    party_id = golden["party_ids"][0]

    loop = asyncio.new_event_loop()
    actual_output, retrieval_context = loop.run_until_complete(
        _run_single_party_pipeline(rag_pipeline, golden["input"], party_id)
    )
    loop.close()

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output=actual_output,
        expected_output=golden["expected_output"],
        retrieval_context=retrieval_context,
    )

    assert_test(
        test_case,
        [faithfulness_metric, answer_relevancy_metric, contextual_recall_metric],
    )


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

    import asyncio

    party_id = golden["party_ids"][0]

    loop = asyncio.new_event_loop()
    actual_output, retrieval_context = loop.run_until_complete(
        _run_single_party_pipeline(rag_pipeline, golden["input"], party_id)
    )
    loop.close()

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output=actual_output,
        retrieval_context=retrieval_context,
    )

    assert_test(test_case, [political_neutrality_metric])
