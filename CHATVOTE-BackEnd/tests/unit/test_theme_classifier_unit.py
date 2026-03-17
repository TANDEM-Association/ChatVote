# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Unit tests for src/services/theme_classifier.py.

All tests run without external services (no LLM APIs, no Qdrant, no Firebase).
LLM-dependent tests use unittest.mock to patch get_structured_output_from_llms.
"""

import sys

# Evict mocks set by other test files (e.g. test_aiohttp_app.py) so real modules load
sys.modules.pop("src.models.chunk_metadata", None)

import pytest  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from langchain_core.documents import Document  # noqa: E402

from src.services.theme_classifier import (  # noqa: E402
    ThemeResult,
    _keyword_scores,
    _keyword_fast_path,
    apply_themes_to_documents,
    classify_chunks,
    classify_theme_keywords,
    _llm_classify_single,
)
from src.models.chunk_metadata import THEME_TAXONOMY  # noqa: E402


# ---------------------------------------------------------------------------
# Sample French political texts
# ---------------------------------------------------------------------------

ENV_TEXT = (
    "La transition énergétique passe par les énergies renouvelables, le solaire "
    "et l'éolien pour réduire la pollution et les émissions de carbone."
)

EDU_TEXT = (
    "L'école publique doit garantir l'accès à l'éducation pour tous les étudiants, "
    "du collège au lycée et à l'université."
)

# Budget text — just 1-2 weak keyword hits, no dominant theme
AMBIGUOUS_TEXT = "Le budget de la commune alloue 5 millions d'euros."

# Strong security text with many keyword hits
SEC_TEXT = (
    "La sécurité est une priorité : la police municipale renforcera la lutte "
    "contre la délinquance et la criminalité grâce à la vidéoprotection et aux "
    "caméras de surveillance pour prévenir les agressions et les cambriolages."
)

# Logement text with strong clear signal
LOG_TEXT = (
    "Nous construirons 500 logements sociaux HLM pour les locataires en difficulté. "
    "La rénovation des appartements et des immeubles insalubres sera une priorité. "
    "Le loyer des habitations sera encadré."
)


# ---------------------------------------------------------------------------
# ThemeResult dataclass
# ---------------------------------------------------------------------------


class TestThemeResult:
    def test_default_values(self):
        result = ThemeResult()
        assert result.theme is None
        assert result.sub_theme is None
        assert result.method == "none"
        assert result.confidence == 0.0

    def test_custom_values(self):
        result = ThemeResult(
            theme="environnement",
            sub_theme="transition énergétique",
            method="llm",
            confidence=1.0,
        )
        assert result.theme == "environnement"
        assert result.sub_theme == "transition énergétique"
        assert result.method == "llm"
        assert result.confidence == 1.0

    def test_partial_custom_values(self):
        result = ThemeResult(theme="sante", method="keyword", confidence=0.75)
        assert result.theme == "sante"
        assert result.sub_theme is None
        assert result.method == "keyword"
        assert result.confidence == 0.75


# ---------------------------------------------------------------------------
# _keyword_scores()
# ---------------------------------------------------------------------------


class TestKeywordScores:
    def test_returns_dict_with_counts_for_matching_text(self):
        scores = _keyword_scores(ENV_TEXT)
        assert "environnement" in scores
        assert (
            scores["environnement"] >= 3
        )  # transition énergétique, solaire, éolien, pollution, carbone, renouvelable

    def test_returns_empty_dict_for_no_keywords(self):
        scores = _keyword_scores("Il fait beau aujourd'hui.")
        assert scores == {}

    def test_case_insensitive_matching(self):
        scores_lower = _keyword_scores("école publique")
        scores_upper = _keyword_scores("ÉCOLE PUBLIQUE")
        assert scores_lower == scores_upper
        assert "education" in scores_lower

    def test_french_plural_handling_ecoles(self):
        """écoles (plural) should match the keyword école."""
        scores_singular = _keyword_scores("une école dans le quartier")
        scores_plural = _keyword_scores("plusieurs écoles dans le quartier")
        assert "education" in scores_singular
        assert "education" in scores_plural

    def test_french_plural_handling_aux_suffix(self):
        """animaux, journaux, etc. — aux suffix handled."""
        scores = _keyword_scores("les logements sociaux et les appartements")
        assert "logement" in scores

    def test_only_counts_distinct_keyword_matches(self):
        """Each keyword pattern counts once even if the word appears multiple times."""
        text = "école école école"
        scores = _keyword_scores(text)
        # Only one keyword pattern matched (école), so count should be 1
        assert scores.get("education", 0) == 1

    def test_multiple_themes_detected_in_mixed_text(self):
        text = "L'école publique améliore la santé des étudiants grâce à la cantine."
        scores = _keyword_scores(text)
        assert "education" in scores
        assert "sante" in scores

    def test_returns_only_themes_with_hits(self):
        scores = _keyword_scores(ENV_TEXT)
        # All returned themes must have at least 1 hit
        assert all(count > 0 for count in scores.values())


# ---------------------------------------------------------------------------
# classify_theme_keywords()
# ---------------------------------------------------------------------------


class TestClassifyThemeKeywords:
    def test_returns_theme_with_clear_winner_and_3plus_hits(self):
        result = classify_theme_keywords(ENV_TEXT)
        assert result.theme == "environnement"
        assert result.method == "keyword"
        assert result.confidence > 0

    def test_returns_none_method_when_less_than_3_hits(self):
        # Budget text has weak/mixed signal — not enough hits for fast-path
        result = classify_theme_keywords(AMBIGUOUS_TEXT)
        assert result.method == "none"
        assert result.theme is None

    def test_returns_none_method_for_text_with_no_keywords(self):
        result = classify_theme_keywords("Il fait beau aujourd'hui.")
        assert result.method == "none"
        assert result.theme is None

    def test_returns_none_method_when_no_clear_margin(self):
        """Two themes tied → no clear 2x margin → method='none'."""
        # Construct text with equal hits for two themes
        tied_text = (
            "L'école et l'université et les étudiants et les enseignants "  # education
            "et la police et la sécurité et la délinquance et la criminalité "  # securite
        )
        result = classify_theme_keywords(tied_text)
        # Either method=none (tied) or a winner with 2x margin — depends on keyword counts
        # If there IS a winner, it must have 2x the runner-up
        if result.method == "keyword":
            scores = _keyword_scores(tied_text)
            sorted_scores = sorted(scores.values(), reverse=True)
            if len(sorted_scores) >= 2:
                assert sorted_scores[0] >= 2 * sorted_scores[1]

    def test_returns_method_keyword_for_clear_winner(self):
        result = classify_theme_keywords(SEC_TEXT)
        assert result.method == "keyword"
        assert result.theme == "securite"

    def test_confidence_calculation(self):
        """confidence = best_count / (best_count + 2)."""
        result = classify_theme_keywords(ENV_TEXT)
        assert result.method == "keyword"
        # Verify the formula: confidence = best_count / (best_count + 2)
        scores = _keyword_scores(ENV_TEXT)
        best_count = max(scores.values())
        expected_confidence = best_count / (best_count + 2)
        assert abs(result.confidence - expected_confidence) < 1e-9

    def test_confidence_is_between_0_and_1(self):
        result = classify_theme_keywords(LOG_TEXT)
        if result.method == "keyword":
            assert 0.0 < result.confidence <= 1.0

    def test_education_text_classified_correctly(self):
        result = classify_theme_keywords(EDU_TEXT)
        assert result.theme == "education"
        assert result.method == "keyword"

    def test_logement_text_classified_correctly(self):
        result = classify_theme_keywords(LOG_TEXT)
        assert result.theme == "logement"
        assert result.method == "keyword"

    def test_sub_theme_is_none_for_keyword_classification(self):
        """Keyword classification never sets a sub_theme."""
        result = classify_theme_keywords(ENV_TEXT)
        assert result.sub_theme is None


# ---------------------------------------------------------------------------
# _keyword_fast_path()
# ---------------------------------------------------------------------------


class TestKeywordFastPath:
    def test_returns_theme_result_for_high_confidence_match(self):
        result = _keyword_fast_path(ENV_TEXT)
        assert result is not None
        assert isinstance(result, ThemeResult)
        assert result.theme == "environnement"
        assert result.method == "keyword"

    def test_returns_none_for_ambiguous_text(self):
        result = _keyword_fast_path(AMBIGUOUS_TEXT)
        assert result is None

    def test_returns_none_for_text_with_no_keywords(self):
        result = _keyword_fast_path("Il fait beau aujourd'hui.")
        assert result is None

    def test_returns_theme_result_instance_when_match_found(self):
        result = _keyword_fast_path(SEC_TEXT)
        assert result is not None
        assert isinstance(result, ThemeResult)

    def test_consistent_with_classify_theme_keywords(self):
        """_keyword_fast_path should agree with classify_theme_keywords on the theme."""
        keyword_result = classify_theme_keywords(ENV_TEXT)
        fast_result = _keyword_fast_path(ENV_TEXT)
        assert fast_result is not None
        assert fast_result.theme == keyword_result.theme


# ---------------------------------------------------------------------------
# apply_themes_to_documents()
# ---------------------------------------------------------------------------


class TestApplyThemesToDocuments:
    def _make_doc(self, content="Texte", **metadata) -> Document:
        return Document(page_content=content, metadata=metadata)

    def test_adds_theme_to_metadata_when_theme_is_not_none(self):
        docs = [self._make_doc("Texte sur l'environnement")]
        results = [ThemeResult(theme="environnement", method="keyword")]
        apply_themes_to_documents(docs, results)
        assert docs[0].metadata["theme"] == "environnement"

    def test_adds_sub_theme_to_metadata_when_not_none(self):
        docs = [self._make_doc("Texte")]
        results = [
            ThemeResult(
                theme="environnement", sub_theme="transition énergétique", method="llm"
            )
        ]
        apply_themes_to_documents(docs, results)
        assert docs[0].metadata["sub_theme"] == "transition énergétique"

    def test_does_not_add_theme_key_when_theme_is_none(self):
        docs = [self._make_doc("Texte ambigu")]
        results = [ThemeResult(method="none")]
        apply_themes_to_documents(docs, results)
        assert "theme" not in docs[0].metadata

    def test_does_not_add_sub_theme_key_when_sub_theme_is_none(self):
        docs = [self._make_doc("Texte")]
        results = [ThemeResult(theme="sante", sub_theme=None, method="keyword")]
        apply_themes_to_documents(docs, results)
        assert "theme" in docs[0].metadata
        assert "sub_theme" not in docs[0].metadata

    def test_modifies_documents_in_place(self):
        docs = [self._make_doc("Texte")]
        original_docs = docs
        results = [ThemeResult(theme="transport", method="llm", confidence=1.0)]
        apply_themes_to_documents(docs, results)
        # Same list object, mutated in place
        assert docs is original_docs
        assert docs[0].metadata["theme"] == "transport"

    def test_handles_multiple_documents(self):
        docs = [
            self._make_doc("Texte 1"),
            self._make_doc("Texte 2"),
            self._make_doc("Texte 3"),
        ]
        results = [
            ThemeResult(theme="environnement", method="keyword"),
            ThemeResult(method="none"),
            ThemeResult(
                theme="education", sub_theme="enseignement primaire", method="llm"
            ),
        ]
        apply_themes_to_documents(docs, results)
        assert docs[0].metadata["theme"] == "environnement"
        assert "theme" not in docs[1].metadata
        assert docs[2].metadata["theme"] == "education"
        assert docs[2].metadata["sub_theme"] == "enseignement primaire"

    def test_preserves_existing_metadata(self):
        docs = [self._make_doc("Texte", namespace="cand-001", page=3)]
        results = [ThemeResult(theme="logement", method="keyword")]
        apply_themes_to_documents(docs, results)
        assert docs[0].metadata["namespace"] == "cand-001"
        assert docs[0].metadata["page"] == 3
        assert docs[0].metadata["theme"] == "logement"

    def test_raises_on_length_mismatch(self):
        docs = [self._make_doc("Texte 1"), self._make_doc("Texte 2")]
        results = [ThemeResult(theme="sante", method="keyword")]
        with pytest.raises(ValueError):
            apply_themes_to_documents(docs, results)


# ---------------------------------------------------------------------------
# classify_chunks() — keyword-only mode (use_llm=False)
# ---------------------------------------------------------------------------


class TestClassifyChunksKeywordOnly:
    @pytest.mark.asyncio
    async def test_use_llm_false_returns_keyword_results_only(self):
        chunks = [ENV_TEXT, EDU_TEXT, AMBIGUOUS_TEXT]
        results = await classify_chunks(chunks, use_llm=False)
        assert len(results) == len(chunks)
        # No result should have method="llm"
        assert all(r.method != "llm" for r in results)

    @pytest.mark.asyncio
    async def test_use_llm_false_classifies_obvious_chunks(self):
        results = await classify_chunks([ENV_TEXT], use_llm=False)
        # ENV_TEXT has clear keyword signal
        assert results[0].theme == "environnement"
        assert results[0].method == "keyword"

    @pytest.mark.asyncio
    async def test_use_llm_false_returns_none_for_ambiguous(self):
        results = await classify_chunks([AMBIGUOUS_TEXT], use_llm=False)
        # Not enough keyword hits → method=none
        assert results[0].method == "none"
        assert results[0].theme is None

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_empty_list(self):
        results = await classify_chunks([], use_llm=False)
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_one_result_per_chunk(self):
        chunks = [ENV_TEXT, EDU_TEXT, SEC_TEXT, AMBIGUOUS_TEXT]
        results = await classify_chunks(chunks, use_llm=False)
        assert len(results) == len(chunks)

    @pytest.mark.asyncio
    async def test_keyword_fast_path_false_sends_all_to_none_without_llm(self):
        """keyword_fast_path=False + use_llm=False → all method=none (no LLM, no keywords)."""
        results = await classify_chunks(
            [ENV_TEXT, EDU_TEXT],
            use_llm=False,
            keyword_fast_path=False,
        )
        # All should be "none" since keywords are skipped and LLM disabled
        assert all(r.method == "none" for r in results)


# ---------------------------------------------------------------------------
# classify_chunks() — LLM path (mocked)
# ---------------------------------------------------------------------------


class TestClassifyChunksWithLLM:
    @pytest.mark.asyncio
    async def test_keyword_fast_path_true_skips_llm_for_obvious_chunks(self):
        """ENV_TEXT has clear keyword signal → should be classified via keyword, not LLM."""
        from src.models.structured_outputs import ChunkThemeClassification

        llm_result = ChunkThemeClassification(
            theme="environnement", sub_theme="transition énergétique"
        )

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_result,
        ) as mock_llm:
            results = await classify_chunks([ENV_TEXT], keyword_fast_path=True)
            # LLM should NOT have been called — keyword fast-path handled it
            mock_llm.assert_not_called()
            assert results[0].method == "keyword"

    @pytest.mark.asyncio
    async def test_ambiguous_chunk_goes_to_llm(self):
        """AMBIGUOUS_TEXT has no clear keyword signal → must go to LLM."""
        from src.models.structured_outputs import BatchChunkThemeClassification, ChunkThemeClassification

        llm_result = BatchChunkThemeClassification(
            classifications=[
                ChunkThemeClassification(theme="institutions", sub_theme="budget participatif")
            ]
        )

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_result,
        ) as mock_llm:
            results = await classify_chunks([AMBIGUOUS_TEXT], keyword_fast_path=True)
            mock_llm.assert_called_once()
            assert results[0].method == "llm"
            assert results[0].theme == "institutions"

    @pytest.mark.asyncio
    async def test_keyword_fast_path_false_sends_all_chunks_to_llm(self):
        """keyword_fast_path=False → every chunk goes to LLM regardless of keyword signal."""
        from src.models.structured_outputs import BatchChunkThemeClassification, ChunkThemeClassification

        # Both chunks go in a single batch (batch_size=20 > 2)
        llm_result = BatchChunkThemeClassification(
            classifications=[
                ChunkThemeClassification(theme="environnement", sub_theme=None),
                ChunkThemeClassification(theme="environnement", sub_theme=None),
            ]
        )

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_result,
        ) as mock_llm:
            chunks = [ENV_TEXT, EDU_TEXT]
            results = await classify_chunks(
                chunks, keyword_fast_path=False, use_llm=True
            )
            # Both chunks sent in one batch call
            assert mock_llm.call_count == 1
            assert all(r.method == "llm" for r in results)

    @pytest.mark.asyncio
    async def test_returns_one_result_per_chunk_with_llm(self):
        from src.models.structured_outputs import BatchChunkThemeClassification, ChunkThemeClassification

        llm_result = BatchChunkThemeClassification(
            classifications=[
                ChunkThemeClassification(theme="sante", sub_theme="accès aux soins"),
                ChunkThemeClassification(theme="sante", sub_theme="accès aux soins"),
            ]
        )

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            chunks = [
                AMBIGUOUS_TEXT,
                "Un autre texte ambigu sans mots-clés politiques.",
            ]
            results = await classify_chunks(chunks, keyword_fast_path=True)
            assert len(results) == len(chunks)

    @pytest.mark.asyncio
    async def test_empty_chunks_list_with_llm_enabled_returns_empty(self):
        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
        ) as mock_llm:
            results = await classify_chunks([], use_llm=True)
            assert results == []
            mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# _llm_classify_single() — mocked
# ---------------------------------------------------------------------------


class TestLlmClassifySingle:
    @pytest.mark.asyncio
    async def test_returns_theme_result_from_llm_structured_output(self):
        from src.models.structured_outputs import ChunkThemeClassification

        llm_result = ChunkThemeClassification(
            theme="environnement", sub_theme="transition énergétique"
        )

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await _llm_classify_single(ENV_TEXT)

        assert isinstance(result, ThemeResult)
        assert result.theme == "environnement"
        assert result.sub_theme == "transition énergétique"
        assert result.method == "llm"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(self):
        """When LLM raises an exception, returns ThemeResult with method='none'."""
        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM unavailable"),
        ):
            result = await _llm_classify_single(AMBIGUOUS_TEXT)

        assert result.method == "none"
        assert result.theme is None

    @pytest.mark.asyncio
    async def test_invalidates_theme_not_in_taxonomy(self):
        """LLM returns an unknown theme → should be nulled out."""
        from src.models.structured_outputs import ChunkThemeClassification

        llm_result = ChunkThemeClassification(theme="unknown_theme_xyz", sub_theme=None)

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await _llm_classify_single("Some text.")

        assert result.theme is None
        assert result.method == "llm"

    @pytest.mark.asyncio
    async def test_all_taxonomy_themes_are_valid(self):
        """Every theme in THEME_TAXONOMY should pass validation."""
        for theme in THEME_TAXONOMY:
            from src.models.structured_outputs import ChunkThemeClassification

            llm_result = ChunkThemeClassification(
                theme=theme, sub_theme="sous-thème test"
            )

            with patch(
                "src.llms.get_structured_output_from_llms",
                new_callable=AsyncMock,
                return_value=llm_result,
            ):
                result = await _llm_classify_single("Texte de test.")

            assert result.theme == theme, f"Theme {theme!r} from taxonomy was rejected"

    @pytest.mark.asyncio
    async def test_handles_dict_return_from_llm(self):
        """LLM occasionally returns dict instead of ChunkThemeClassification."""
        dict_result = {"theme": "logement", "sub_theme": "logement social"}

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=dict_result,
        ):
            result = await _llm_classify_single("Texte logement.")

        assert result.theme == "logement"
        assert result.sub_theme == "logement social"
        assert result.method == "llm"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_handles_dict_return_with_invalid_theme(self):
        """Dict return with invalid theme → theme nulled out."""
        dict_result = {"theme": "not_a_valid_theme", "sub_theme": None}

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=dict_result,
        ):
            result = await _llm_classify_single("Texte ambigu.")

        assert result.theme is None

    @pytest.mark.asyncio
    async def test_handles_unexpected_return_type(self):
        """Non-dict, non-ChunkThemeClassification → method='none'."""
        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value="raw string response",
        ):
            result = await _llm_classify_single("Texte.")

        assert result.method == "none"
        assert result.theme is None

    @pytest.mark.asyncio
    async def test_none_theme_from_llm_returns_none_theme_result(self):
        """LLM returns theme=None (non-political text) → ThemeResult with theme=None."""
        from src.models.structured_outputs import ChunkThemeClassification

        llm_result = ChunkThemeClassification(theme=None, sub_theme=None)

        with patch(
            "src.llms.get_structured_output_from_llms",
            new_callable=AsyncMock,
            return_value=llm_result,
        ):
            result = await _llm_classify_single(
                "Mentions légales - Tous droits réservés."
            )

        assert result.theme is None
        assert result.method == "llm"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_truncates_text_to_800_chars(self):
        """_llm_classify_single should send at most 800 chars of the chunk to the LLM."""
        from src.models.structured_outputs import ChunkThemeClassification

        long_text = "environnement " * 200  # >800 chars

        llm_result = ChunkThemeClassification(theme="environnement", sub_theme=None)
        captured_messages = []

        async def _capture(*args, **kwargs):
            captured_messages.extend(args[1])
            return llm_result

        with patch(
            "src.llms.get_structured_output_from_llms",
            side_effect=_capture,
        ):
            await _llm_classify_single(long_text)

        assert captured_messages, "LLM was not called"
        prompt_text = captured_messages[0].content
        # The chunk embedded in the prompt must be at most 800 chars of original text
        assert long_text[:800] in prompt_text
        assert long_text[801:] not in prompt_text
