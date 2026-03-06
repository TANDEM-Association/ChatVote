"""
RAG Retriever evaluation tests.

Tests retrieval quality by measuring whether the vector store + reranker
return relevant context for golden questions.

Run:
    poetry run deepeval test run tests/eval/test_rag_retriever.py -v
"""

import asyncio
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
# Shared event loop for all tests in this module (avoids gRPC loop issues)
# ---------------------------------------------------------------------------

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


def _make_party(Party, party_id: str):
    return Party(
        party_id=party_id, name=party_id, long_name=party_id,
        description="", website_url="", candidate="", election_manifesto_url="",
    )


def _assert_doc_metadata(docs, expected_party_id: str):
    """Validate that retrieved documents have proper metadata for downstream use."""
    assert len(docs) > 0, "No documents retrieved"
    for doc in docs:
        meta = doc.metadata
        # Every doc must have a source identifier
        assert meta, f"Document has no metadata: {doc.page_content[:100]}"
        # namespace, party_id, or candidate_id should be present
        owner = meta.get("namespace") or meta.get("party_id") or meta.get("candidate_id")
        assert owner, (
            f"Document missing namespace/party_id/candidate_id in metadata: {meta}"
        )
        # When searching for a specific party, docs should belong to that party
        if expected_party_id and meta.get("namespace"):
            assert meta["namespace"] == expected_party_id, (
                f"Document namespace '{meta['namespace']}' doesn't match "
                f"expected party '{expected_party_id}'"
            )


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

    party_id = golden["party_ids"][0]
    party = _make_party(Party, party_id)

    loop = _get_loop()
    docs = loop.run_until_complete(
        identify_relevant_docs(party=party, rag_query=golden["input"], n_docs=5)
    )

    # Validate metadata on retrieved documents
    _assert_doc_metadata(docs, party_id)

    retrieval_context = [doc.page_content for doc in docs]

    # Check expected source keywords appear in context
    context_joined = " ".join(retrieval_context).lower()
    for keyword in golden.get("expected_source_keywords", []):
        assert keyword.lower() in context_joined, (
            f"Expected keyword '{keyword}' not found in retrieval context for {party_id}"
        )

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

    loop = _get_loop()
    all_context = []
    for party_id in golden["party_ids"]:
        party = _make_party(Party, party_id)
        docs = loop.run_until_complete(
            identify_relevant_docs(party=party, rag_query=golden["input"], n_docs=3)
        )
        # Validate metadata per party
        _assert_doc_metadata(docs, party_id)
        all_context.extend([doc.page_content for doc in docs])

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output="",
        expected_output=golden["expected_output"],
        retrieval_context=all_context,
    )

    assert_test(test_case, [contextual_recall_metric])
