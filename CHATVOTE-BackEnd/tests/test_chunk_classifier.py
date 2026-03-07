import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_classify_chunks_returns_theme_list():
    """classify_chunks_themes returns a list of classifications."""
    from src.services.chunk_classifier import classify_chunks_themes, ChunkThemeClassification

    mock_result = ChunkThemeClassification(theme="economie", sub_theme="budget")

    with patch("src.services.chunk_classifier._classify_single") as mock_cls:
        mock_cls.return_value = mock_result
        results = await classify_chunks_themes(["Chunk about budget and taxes."])

    assert len(results) == 1
    assert results[0].theme == "economie"
    assert results[0].sub_theme == "budget"


@pytest.mark.asyncio
async def test_classify_chunks_handles_failure():
    """If classification fails for a chunk, return None themes (not crash)."""
    from src.services.chunk_classifier import classify_chunks_themes, ChunkThemeClassification

    with patch("src.services.chunk_classifier._classify_single") as mock_cls:
        mock_cls.return_value = ChunkThemeClassification(theme=None, sub_theme=None)
        results = await classify_chunks_themes(["Some text"])

    assert len(results) == 1
    assert results[0].theme is None


@pytest.mark.asyncio
async def test_classify_chunks_multiple():
    """Multiple chunks are all classified."""
    from src.services.chunk_classifier import classify_chunks_themes, ChunkThemeClassification

    mock_result = ChunkThemeClassification(theme="sante", sub_theme=None)

    with patch("src.services.chunk_classifier._classify_single") as mock_cls:
        mock_cls.return_value = mock_result
        results = await classify_chunks_themes(["chunk1", "chunk2", "chunk3"])

    assert len(results) == 3
    assert all(r.theme == "sante" for r in results)


@pytest.mark.asyncio
async def test_classify_respects_concurrency():
    """Semaphore limits concurrent LLM calls."""
    from src.services.chunk_classifier import classify_chunks_themes, ChunkThemeClassification
    import asyncio

    concurrent_count = 0
    max_concurrent = 0

    async def mock_classify(text):
        nonlocal concurrent_count, max_concurrent
        concurrent_count += 1
        max_concurrent = max(max_concurrent, concurrent_count)
        await asyncio.sleep(0.01)
        concurrent_count -= 1
        return ChunkThemeClassification(theme="economie", sub_theme=None)

    with patch("src.services.chunk_classifier._classify_single", side_effect=mock_classify):
        results = await classify_chunks_themes(
            ["chunk"] * 10,
            max_concurrent=3,
        )

    assert len(results) == 10
    assert max_concurrent <= 3
