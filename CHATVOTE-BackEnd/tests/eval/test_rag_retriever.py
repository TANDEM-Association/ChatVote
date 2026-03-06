"""
RAG Retriever evaluation tests.

Tests retrieval quality by measuring whether the vector store + reranker
return relevant context for golden questions.

Run:
    poetry run deepeval test run tests/eval/test_rag_retriever.py -v
"""

import json
import os
import sys
from pathlib import Path

import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATASETS_DIR = Path(__file__).parent / "datasets"


def _load_golden(category: str) -> list[dict]:
    data = json.loads((DATASETS_DIR / "golden_questions.json").read_text())
    return data.get(category, [])


def _skip_if_no_qdrant():
    """Skip tests if Qdrant is not reachable."""
    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    try:
        import urllib.request
        urllib.request.urlopen(qdrant_url, timeout=2)
    except Exception:
        pytest.skip(f"Qdrant not reachable at {qdrant_url}")


# ---------------------------------------------------------------------------
# Retriever integration test: run actual retrieval, measure context quality
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qdrant_retriever():
    """Import the vector store helper (requires Qdrant running)."""
    _skip_if_no_qdrant()

    os.environ.setdefault("ENV", "dev")
    from src.vector_store_helper import (
        identify_relevant_docs,
        get_qdrant_vector_store,
    )
    from src.models.party import Party

    # Verify the vector store is accessible
    try:
        vs = get_qdrant_vector_store()
    except Exception as e:
        pytest.skip(f"Vector store not available: {e}")

    return identify_relevant_docs, Party


@pytest.mark.parametrize(
    "golden",
    _load_golden("single_party"),
    ids=lambda g: g.get("category", "unknown"),
)
def test_retriever_single_party(
    golden,
    qdrant_retriever,
    contextual_recall_metric,
    contextual_relevancy_metric,
):
    """Test that retriever finds relevant docs for single-party questions."""
    identify_relevant_docs, Party = qdrant_retriever

    # Build a minimal Party object for retrieval
    party_id = golden["party_ids"][0]

    import asyncio

    party = Party(party_id=party_id, name=party_id, long_name=party_id)

    loop = asyncio.new_event_loop()
    docs = loop.run_until_complete(
        identify_relevant_docs(party=party, rag_query=golden["input"], n_docs=5)
    )
    loop.close()
    retrieval_context = [doc.page_content for doc in docs]

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output="",  # Not testing generation here
        expected_output=golden["expected_output"],
        retrieval_context=retrieval_context,
    )

    assert_test(test_case, [contextual_recall_metric, contextual_relevancy_metric])


@pytest.mark.parametrize(
    "golden",
    _load_golden("multi_party_comparison"),
    ids=lambda g: g.get("category", "unknown"),
)
def test_retriever_multi_party(
    golden,
    qdrant_retriever,
    contextual_recall_metric,
):
    """Test that retriever finds docs across multiple parties."""
    identify_relevant_docs, Party = qdrant_retriever

    import asyncio

    loop = asyncio.new_event_loop()
    all_context = []
    for party_id in golden["party_ids"]:
        party = Party(party_id=party_id, name=party_id, long_name=party_id)
        docs = loop.run_until_complete(
            identify_relevant_docs(party=party, rag_query=golden["input"], n_docs=3)
        )
        all_context.extend([doc.page_content for doc in docs])
    loop.close()

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output="",
        expected_output=golden["expected_output"],
        retrieval_context=all_context,
    )

    assert_test(test_case, [contextual_recall_metric])
