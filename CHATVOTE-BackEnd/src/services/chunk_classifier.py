# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
LLM-based theme classification for chunks at ingestion time.

Uses the LLM failover chain to classify each chunk into the 14-theme taxonomy.
Gracefully degrades on failure — never blocks indexing.
"""

import asyncio
import logging

from src.models.structured_outputs import ChunkThemeClassification

logger = logging.getLogger(__name__)

_CLASSIFICATION_PROMPT = """Classify the following text excerpt from a French political document.
Determine its primary political theme and a specific sub-theme.

Text:
---
{chunk_text}
---
"""


async def _classify_single(chunk_text: str) -> ChunkThemeClassification:
    """Classify a single chunk. Returns None-theme fields on failure."""
    try:
        from langchain_core.messages import HumanMessage
        from src.llms import DETERMINISTIC_LLMS, get_structured_output_from_llms

        messages = [HumanMessage(content=_CLASSIFICATION_PROMPT.format(chunk_text=chunk_text[:500]))]
        result = await get_structured_output_from_llms(
            DETERMINISTIC_LLMS,
            messages,
            ChunkThemeClassification,
        )
        if isinstance(result, ChunkThemeClassification):
            return result
        # Fallback if result is a dict
        return ChunkThemeClassification(**result) if isinstance(result, dict) else ChunkThemeClassification(theme=None, sub_theme=None)
    except Exception as e:
        logger.warning(f"Theme classification failed: {e}")
        return ChunkThemeClassification(theme=None, sub_theme=None)


async def classify_chunks_themes(
    chunks: list[str],
    max_concurrent: int = 5,
) -> list[ChunkThemeClassification]:
    """
    Classify a list of chunks into themes.

    Args:
        chunks: Text chunks to classify.
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
