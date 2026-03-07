"""
Shared fixtures for DeepEval RAG evaluation tests.

The judge_model fixture is inherited from tests/conftest.py.
This file provides metric fixtures used by eval tests.
"""

import os
import pytest

from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    ContextualRecallMetric,
    ContextualPrecisionMetric,
    ContextualRelevancyMetric,
    HallucinationMetric,
    GEval,
)
from deepeval.test_case import LLMTestCaseParams


# ---------------------------------------------------------------------------
# Tier 1 — Critical metrics
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def faithfulness_metric(judge_model):
    """Checks that LLM output is grounded in retrieved context."""
    # Lower threshold for Ollama (small models score stricter)
    threshold = 0.7 if os.environ.get("DEEPEVAL_JUDGE") == "gemini" else 0.5
    return FaithfulnessMetric(
        threshold=threshold,
        model=judge_model,
        include_reason=True,
    )


@pytest.fixture(scope="session")
def answer_relevancy_metric(judge_model):
    """Checks that the answer addresses the user's question."""
    threshold = 0.7 if os.environ.get("DEEPEVAL_JUDGE") == "gemini" else 0.5
    return AnswerRelevancyMetric(
        threshold=threshold,
        model=judge_model,
        include_reason=True,
    )


@pytest.fixture(scope="session")
def contextual_recall_metric(judge_model):
    """Checks that relevant docs were actually retrieved."""
    return ContextualRecallMetric(
        threshold=0.6,
        model=judge_model,
        include_reason=True,
    )


# ---------------------------------------------------------------------------
# Tier 2 — Important metrics
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def contextual_precision_metric(judge_model):
    """Checks that relevant docs are ranked higher by the reranker."""
    return ContextualPrecisionMetric(
        threshold=0.6,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def contextual_relevancy_metric(judge_model):
    """Checks chunk size / top-K returns useful context."""
    # Lower threshold: crawled websites contain noise (nav links, legal disclaimers, mixed topics)
    return ContextualRelevancyMetric(
        threshold=0.25,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def hallucination_metric(judge_model):
    """Secondary hallucination check — critical for political claims."""
    return HallucinationMetric(
        threshold=0.7,
        model=judge_model,
    )


# ---------------------------------------------------------------------------
# Tier 3 — Domain-specific custom metrics (GEval)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def political_neutrality_metric(judge_model):
    """Ensures responses don't favor one party over another."""
    return GEval(
        name="Political Neutrality",
        criteria="""Determine if the actual output maintains political neutrality when
        presenting party positions. The response should:
        1. Present each party's position factually without editorial commentary
        2. Not use loaded language that favors or disfavors any party
        3. Give roughly equal treatment to each party mentioned
        4. Not express a preference or recommendation for any party
        5. Use neutral framing when comparing positions""",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        threshold=0.8,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def source_attribution_metric(judge_model):
    """Ensures responses cite source documents properly."""
    threshold = 0.7 if os.environ.get("DEEPEVAL_JUDGE") == "gemini" else 0.3
    return GEval(
        name="Source Attribution",
        criteria="""Evaluate whether the actual output properly attributes information
        to specific source documents. The response should:
        1. Reference which party manifesto or document each claim comes from
        2. Not present information without indicating its source
        3. Distinguish between direct quotes and paraphrased positions
        4. Include document or section references when available in the context""",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        threshold=threshold,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def multiparty_completeness_metric(judge_model):
    """Ensures all relevant parties are covered when comparing."""
    threshold = 0.9 if os.environ.get("DEEPEVAL_JUDGE") == "gemini" else 0.5
    return GEval(
        name="Multi-party Completeness",
        criteria="""When the user's question asks about multiple parties' positions,
        evaluate whether the response covers all relevant parties. The response should:
        1. Address each party that was included in the retrieval context
        2. Not skip any party for which relevant information was retrieved
        3. Clearly state when a party has no position on the topic
        4. Give each party a substantive response, not just a token mention""",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        threshold=threshold,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def french_quality_metric(judge_model):
    """Evaluates French language quality of responses."""
    # Lower threshold for Ollama (small models are stricter on French eval)
    threshold = 0.7 if os.environ.get("DEEPEVAL_JUDGE") == "gemini" else 0.5
    return GEval(
        name="French Language Quality",
        criteria="""Evaluate the quality of the French language in the response:
        1. Correct grammar and spelling
        2. Appropriate formal register for civic/political communication
        3. Clear and accessible language for a general audience
        4. Proper use of political terminology in French""",
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
        threshold=threshold,
        model=judge_model,
    )


# ---------------------------------------------------------------------------
# Tier 4 — Metadata quality metrics
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def metadata_source_traceability_metric(judge_model):
    """Ensures retrieval context chunks carry enough metadata for source tracing."""
    return GEval(
        name="Metadata Source Traceability",
        criteria="""Evaluate whether the retrieval context contains rich metadata
        that enables source tracing. Each retrieved chunk should ideally include:
        1. Party or candidate name identifying the author of the content
        2. Document name or type (manifesto, website, parliamentary record)
        3. A URL or page reference allowing the user to verify the claim
        4. Reliability indicator (fiabilite level) distinguishing official vs informal sources
        5. Geographic context (municipality, commune) when relevant to local elections
        Score higher when chunks carry more of these metadata fields.""",
        evaluation_params=[
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        threshold=0.5,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def metadata_geographic_relevance_metric(judge_model):
    """Ensures retrieval filters by geographic context when the question mentions a location."""
    return GEval(
        name="Geographic Relevance",
        criteria="""Evaluate whether the retrieval context is geographically relevant
        to the user's question. When a user asks about a specific commune or region:
        1. Retrieved chunks should reference that commune or nearby areas
        2. National-level content should only appear if no local content exists
        3. Content from unrelated municipalities should not be present
        4. Geographic metadata (commune name, postal code, EPCI) should match the query
        Score lower if chunks from unrelated geographic areas dominate the context.""",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.RETRIEVAL_CONTEXT,
        ],
        threshold=0.5,
        model=judge_model,
    )


# ---------------------------------------------------------------------------
# Bundled metric sets
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def retriever_metrics(
    contextual_recall_metric,
    contextual_precision_metric,
    contextual_relevancy_metric,
):
    """All retriever-side metrics."""
    return [
        contextual_recall_metric,
        contextual_precision_metric,
        contextual_relevancy_metric,
    ]


@pytest.fixture(scope="session")
def generator_metrics(
    faithfulness_metric,
    answer_relevancy_metric,
    hallucination_metric,
):
    """All generator-side metrics."""
    return [
        faithfulness_metric,
        answer_relevancy_metric,
        hallucination_metric,
    ]


@pytest.fixture(scope="session")
def political_metrics(
    political_neutrality_metric,
    source_attribution_metric,
    multiparty_completeness_metric,
    french_quality_metric,
):
    """All domain-specific political metrics."""
    return [
        political_neutrality_metric,
        source_attribution_metric,
        multiparty_completeness_metric,
        french_quality_metric,
    ]


@pytest.fixture(scope="session")
def metadata_metrics(
    metadata_source_traceability_metric,
    metadata_geographic_relevance_metric,
):
    """All metadata quality metrics."""
    return [
        metadata_source_traceability_metric,
        metadata_geographic_relevance_metric,
    ]
