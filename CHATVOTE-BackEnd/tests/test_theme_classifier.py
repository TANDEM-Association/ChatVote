"""Tests for the unified theme classifier (src/services/theme_classifier.py).

Architecture: LLM-primary with keyword fast-path for obvious cases.

Covers:
- ThemeResult dataclass.
- classify_theme_keywords: keyword-only classification (requires 3+ hits).
- _keyword_scores: internal keyword scoring.
- classify_chunks: LLM-primary batch with keyword fast-path.
- apply_themes_to_documents: in-place metadata mutation.
- Word-boundary regression: no false positives from substring matches.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.theme_classifier import (
    ThemeResult,
    _keyword_scores,
    apply_themes_to_documents,
    classify_chunks,
    classify_theme_keywords,
)


# ---------------------------------------------------------------------------
# ThemeResult dataclass
# ---------------------------------------------------------------------------

class TestThemeResult:
    def test_defaults(self):
        r = ThemeResult()
        assert r.theme is None
        assert r.sub_theme is None
        assert r.method == "none"

    def test_keyword_method(self):
        r = ThemeResult(theme="economie", method="keyword", confidence=0.5)
        assert r.theme == "economie"
        assert r.method == "keyword"
        assert r.confidence == 0.5

    def test_confidence_default(self):
        r = ThemeResult()
        assert r.confidence == 0.0

    def test_llm_method_with_sub_theme(self):
        r = ThemeResult(theme="sante", sub_theme="hopitaux", method="llm")
        assert r.sub_theme == "hopitaux"
        assert r.method == "llm"


# ---------------------------------------------------------------------------
# _keyword_scores — internal keyword scoring
# ---------------------------------------------------------------------------

class TestKeywordScores:
    """Test the internal keyword scoring function."""

    def test_returns_scores_for_matching_themes(self):
        scores = _keyword_scores("Le budget fiscal et la dette publique")
        assert "economie" in scores
        assert scores["economie"] >= 3

    def test_returns_empty_for_no_match(self):
        scores = _keyword_scores("Lorem ipsum dolor sit amet")
        assert scores == {}

    def test_handles_french_plurals(self):
        """Word-boundary patterns should match plurals (écoles, médecins)."""
        scores = _keyword_scores("Les écoles et les médecins")
        assert "education" in scores
        assert "sante" in scores

    @pytest.mark.parametrize(
        "text, expected_theme",
        [
            ("Le budget de la dette publique emploi fiscal", "economie"),
            ("Les enseignants de l'école scolaire formation", "education"),
            ("Lutte contre la pollution, le climat et le recyclage", "environnement"),
            ("L'hôpital, les médecins et les soins", "sante"),
            ("La police, la délinquance et la vidéoprotection", "securite"),
            ("Régularisation des migrants à la frontière", "immigration"),
            ("Le musée, le théâtre et le patrimoine", "culture"),
            ("Logement social HLM et rénovation", "logement"),
            ("Le tramway, le vélo et le stationnement", "transport"),
            ("Fibre, cybersécurité et intelligence artificielle", "numerique"),
            ("Les agriculteurs, le circuit court et l'élevage", "agriculture"),
            ("Le tribunal, les magistrats et la prison", "justice"),
            ("L'OTAN, la diplomatie et la défense", "international"),
            ("Référendum, budget participatif et citoyen", "institutions"),
        ],
    )
    def test_each_theme_has_keywords(self, text, expected_theme):
        """Each theme must be reachable via keywords (3+ hits for fast-path)."""
        scores = _keyword_scores(text)
        assert expected_theme in scores
        assert scores[expected_theme] >= 3


# ---------------------------------------------------------------------------
# classify_theme_keywords — keyword-only classification
# ---------------------------------------------------------------------------

class TestClassifyThemeKeywords:
    """Keyword fast-path requires 3+ hits with clear margin."""

    def test_strong_signal_classified(self):
        """3+ keyword hits for one theme → classified."""
        text = "Le budget fiscal, la dette publique et l'emploi"
        result = classify_theme_keywords(text)
        assert result.theme == "economie"
        assert result.method == "keyword"
        assert result.confidence > 0

    def test_weak_signal_returns_none(self):
        """1-2 keyword hits → not enough for fast-path, returns none."""
        text = "Le budget de la commune"  # only 1 hit for economie
        result = classify_theme_keywords(text)
        assert result.theme is None
        assert result.method == "none"

    def test_no_match_returns_none(self):
        result = classify_theme_keywords("Ceci est un texte neutre sans mot-clé")
        assert result.theme is None
        assert result.method == "none"

    def test_empty_string(self):
        result = classify_theme_keywords("")
        assert result.theme is None
        assert result.method == "none"

    def test_ambiguous_multi_theme_returns_none(self):
        """When two themes are close in score, returns none for LLM."""
        # 3 hits economie + 2 hits education → margin not 2x → none
        text = "Le budget, la dette et l'emploi dans l'école et l'université"
        result = classify_theme_keywords(text)
        # Winner doesn't have 2x the runner-up, so should go to LLM
        assert result.theme is None


# ---------------------------------------------------------------------------
# Word-boundary regression tests
# ---------------------------------------------------------------------------

class TestWordBoundaryRegression:
    """Verify word-boundary matching prevents false positives."""

    @pytest.mark.parametrize(
        "text, wrong_theme",
        [
            # "vert" in "ouverture" must NOT match environnement
            ("L'ouverture du nouveau centre commercial", "environnement"),
            # "bus" in "business" must NOT match transport
            ("Le business plan de l'entreprise", "transport"),
            # "art" in "article" must NOT match culture
            ("L'article 49.3 de la Constitution", "culture"),
            # "bio" in "biodiversité" must NOT match agriculture
            ("La biodiversité marine en danger", "agriculture"),
            # "droit" in "droite" must NOT match justice
            ("Le parti de droite a gagné les élections", "justice"),
        ],
    )
    def test_false_positive_avoided(self, text, wrong_theme):
        scores = _keyword_scores(text)
        assert wrong_theme not in scores, (
            f"Text '{text}' should NOT score for '{wrong_theme}', "
            f"but got {scores.get(wrong_theme)} hits"
        )


# ---------------------------------------------------------------------------
# classify_chunks — LLM-primary batch classification
# ---------------------------------------------------------------------------

class TestClassifyChunks:
    @pytest.mark.asyncio
    async def test_obvious_chunks_skip_llm(self):
        """Chunks with 3+ keyword hits should skip LLM (fast-path)."""
        chunks = [
            # 5+ keyword hits → fast-path
            "Le budget fiscal de la dette, l'emploi et le chômage",
        ]
        with patch(
            "src.services.theme_classifier._llm_classify_single"
        ) as mock_llm:
            results = await classify_chunks(chunks)

        mock_llm.assert_not_called()
        assert results[0].theme == "economie"
        assert results[0].method == "keyword"

    @pytest.mark.asyncio
    async def test_all_chunks_go_to_llm_when_no_fast_path(self):
        """Chunks without strong keyword signal go to LLM."""
        chunks = [
            "Blah blah random neutral text",
            "Un simple texte sur la commune",
        ]
        mock_llm = AsyncMock(
            return_value=ThemeResult(theme="securite", sub_theme="police", method="llm")
        )
        with patch(
            "src.services.theme_classifier._llm_classify_single", mock_llm
        ):
            results = await classify_chunks(chunks)

        assert mock_llm.call_count == 2
        assert all(r.method == "llm" for r in results)

    @pytest.mark.asyncio
    async def test_mixed_fast_path_and_llm(self):
        """Mix of obvious (fast-path) and ambiguous (LLM) chunks."""
        chunks = [
            # obvious → keyword fast-path
            "Le budget fiscal, la dette publique, l'emploi et le chômage",
            # not obvious → LLM
            "Un texte sans thème clair",
        ]
        mock_llm = AsyncMock(
            return_value=ThemeResult(theme="culture", sub_theme="patrimoine", method="llm")
        )
        with patch(
            "src.services.theme_classifier._llm_classify_single", mock_llm
        ):
            results = await classify_chunks(chunks)

        assert results[0].theme == "economie"
        assert results[0].method == "keyword"
        assert results[1].theme == "culture"
        assert results[1].method == "llm"
        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_use_llm_false_keyword_only(self):
        """When use_llm=False, only keyword classification is used."""
        chunks = [
            "Le budget fiscal, la dette publique et l'emploi",
            "Texte neutre",
        ]
        with patch(
            "src.services.theme_classifier._llm_classify_single"
        ) as mock_llm:
            results = await classify_chunks(chunks, use_llm=False)

        mock_llm.assert_not_called()
        assert results[0].theme == "economie"
        assert results[1].theme is None

    @pytest.mark.asyncio
    async def test_llm_returns_none_keeps_unclassified(self):
        """If LLM also fails, the result stays as method='none'."""
        chunks = ["totally random gibberish"]
        mock_llm = AsyncMock(return_value=ThemeResult(method="none"))
        with patch(
            "src.services.theme_classifier._llm_classify_single", mock_llm
        ):
            results = await classify_chunks(chunks)

        assert results[0].theme is None

    @pytest.mark.asyncio
    async def test_concurrency_semaphore_respected(self):
        """Verify that the semaphore limits concurrent LLM calls."""
        max_concurrent = 2
        concurrent_count = 0
        peak_concurrent = 0

        async def _tracked_llm(text: str) -> ThemeResult:
            nonlocal concurrent_count, peak_concurrent
            concurrent_count += 1
            peak_concurrent = max(peak_concurrent, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return ThemeResult(theme="economie", method="llm")

        chunks = [f"neutral text {i}" for i in range(5)]
        with patch(
            "src.services.theme_classifier._llm_classify_single",
            side_effect=_tracked_llm,
        ):
            results = await classify_chunks(
                chunks, max_concurrent_llm=max_concurrent
            )

        assert peak_concurrent <= max_concurrent
        assert all(r.theme == "economie" for r in results)

    @pytest.mark.asyncio
    async def test_empty_chunks_list(self):
        results = await classify_chunks([])
        assert results == []

    @pytest.mark.asyncio
    async def test_keyword_fast_path_disabled(self):
        """When keyword_fast_path=False, ALL chunks go to LLM."""
        chunks = [
            "Le budget fiscal, la dette publique, l'emploi et le chômage",
        ]
        mock_llm = AsyncMock(
            return_value=ThemeResult(theme="economie", method="llm", confidence=1.0)
        )
        with patch(
            "src.services.theme_classifier._llm_classify_single", mock_llm
        ):
            results = await classify_chunks(chunks, keyword_fast_path=False)

        mock_llm.assert_called_once()
        assert results[0].method == "llm"


# ---------------------------------------------------------------------------
# apply_themes_to_documents
# ---------------------------------------------------------------------------

class TestApplyThemesToDocuments:
    @staticmethod
    def _make_doc(**metadata):
        """Create a lightweight document-like object with metadata dict."""
        return SimpleNamespace(metadata=dict(metadata))

    def test_applies_theme_and_sub_theme(self):
        docs = [self._make_doc(source="test")]
        theme_results = [
            ThemeResult(theme="transport", sub_theme="velo", method="keyword")
        ]
        apply_themes_to_documents(docs, theme_results)
        assert docs[0].metadata["theme"] == "transport"
        assert docs[0].metadata["sub_theme"] == "velo"

    def test_skips_none_theme(self):
        docs = [self._make_doc(source="test")]
        theme_results = [ThemeResult(method="none")]
        apply_themes_to_documents(docs, theme_results)
        assert "theme" not in docs[0].metadata
        assert "sub_theme" not in docs[0].metadata

    def test_skips_none_sub_theme(self):
        docs = [self._make_doc(source="test")]
        theme_results = [ThemeResult(theme="logement", method="keyword")]
        apply_themes_to_documents(docs, theme_results)
        assert docs[0].metadata["theme"] == "logement"
        assert "sub_theme" not in docs[0].metadata

    def test_multiple_documents(self):
        docs = [
            self._make_doc(source="a"),
            self._make_doc(source="b"),
            self._make_doc(source="c"),
        ]
        theme_results = [
            ThemeResult(theme="culture", method="keyword"),
            ThemeResult(method="none"),
            ThemeResult(theme="sante", sub_theme="hopitaux", method="llm"),
        ]
        apply_themes_to_documents(docs, theme_results)

        assert docs[0].metadata["theme"] == "culture"
        assert "theme" not in docs[1].metadata
        assert docs[2].metadata["theme"] == "sante"
        assert docs[2].metadata["sub_theme"] == "hopitaux"

    def test_length_mismatch_raises(self):
        docs = [self._make_doc()]
        theme_results = [ThemeResult(), ThemeResult()]
        with pytest.raises(ValueError):
            apply_themes_to_documents(docs, theme_results)
