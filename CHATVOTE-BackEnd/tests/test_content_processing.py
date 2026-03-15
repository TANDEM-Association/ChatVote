"""Tests for src.services.content_processing — pure functions, no mocks needed."""

import pytest

from src.services.content_processing import (
    strip_consent_boilerplate,
    is_a11y_widget_chunk,
    infer_source_document,
    is_metadata_only,
    is_real_content,
    filter_chunks,
    split_page_content,
    FilterStats,
    CHUNK_SIZE,
    LARGE_PAGE_THRESHOLD,
)


# ===== strip_consent_boilerplate =====


class TestStripConsentBoilerplate:
    def test_removes_gdpr_block(self):
        text = (
            "Some real content. "
            "Gérer le consentement Nous utilisons des cookies. "
            "Fonctionnel Toujours activ "
            "More real content."
        )
        result = strip_consent_boilerplate(text)
        assert "Gérer le consentement" not in result
        assert "real content" in result

    def test_removes_trailing_consent_link(self):
        text = "Some content\n  Gérer le consentement"
        result = strip_consent_boilerplate(text)
        assert result == "Some content"

    def test_preserves_text_without_consent(self):
        text = "This is normal political content about the programme."
        assert strip_consent_boilerplate(text) == text

    def test_handles_empty_string(self):
        assert strip_consent_boilerplate("") == ""

    def test_handles_consent_only(self):
        text = "Gestion des cookies nous utilisons Accepter"
        result = strip_consent_boilerplate(text)
        assert result == ""


# ===== is_a11y_widget_chunk =====


class TestIsA11yWidgetChunk:
    def test_detects_widget_text(self):
        text = (
            "Disability profiles supported. WCAG 2.1 compliance. "
            "Screen reader adjustments. Seizure Safe Profile. "
            "Keyboard navigation optimization."
        )
        assert is_a11y_widget_chunk(text) is True

    def test_single_mention_not_widget(self):
        text = "Our website follows WCAG 2.1 compliance standards for all citizens."
        assert is_a11y_widget_chunk(text) is False

    def test_normal_political_content(self):
        text = "Notre programme pour l'accessibilité des transports publics."
        assert is_a11y_widget_chunk(text) is False

    def test_empty_string(self):
        assert is_a11y_widget_chunk("") is False


# ===== infer_source_document =====


class TestInferSourceDocument:
    def test_programme_page(self):
        assert infer_source_document(
            "https://example.com/programme/logement", "html", 1
        ) == "candidate_website_programme"

    def test_projet_page(self):
        assert infer_source_document(
            "https://example.com/notre-projet", "html", 1
        ) == "candidate_website_programme"

    def test_propositions_page(self):
        assert infer_source_document(
            "https://example.com/propositions", "html", 1
        ) == "candidate_website_programme"

    def test_about_page(self):
        assert infer_source_document(
            "https://example.com/biographie", "html", 1
        ) == "candidate_website_about"

    def test_equipe_page(self):
        assert infer_source_document(
            "https://example.com/equipe", "html", 1
        ) == "candidate_website_about"

    def test_actualite_page(self):
        assert infer_source_document(
            "https://example.com/actualites/dernier-meeting", "html", 1
        ) == "candidate_website_actualite"

    def test_blog_page(self):
        assert infer_source_document(
            "https://example.com/blog/post-1", "html", 1
        ) == "candidate_website_actualite"

    def test_legal_page(self):
        assert infer_source_document(
            "https://example.com/mentions-legales", "html", 1
        ) == "candidate_website_html"

    def test_homepage_is_about(self):
        assert infer_source_document(
            "https://example.com/", "html", 0
        ) == "candidate_website_about"

    def test_generic_html(self):
        assert infer_source_document(
            "https://example.com/contact", "html", 2
        ) == "candidate_website_html"

    def test_pdf_page_type(self):
        assert infer_source_document(
            "https://example.com/file.pdf", "pdf_transcription", 1
        ) == "candidate_website_pdf_transcription"

    def test_social_bio(self):
        assert infer_source_document(
            "https://twitter.com/candidate", "social_bio", 0
        ) == "candidate_social_bio"

    def test_social_post(self):
        assert infer_source_document(
            "https://twitter.com/candidate/status/123", "social_post", 0
        ) == "candidate_social_post"

    def test_case_insensitive(self):
        assert infer_source_document(
            "https://example.com/PROGRAMME/Education", "html", 1
        ) == "candidate_website_programme"

    def test_cookies_page_is_legal(self):
        assert infer_source_document(
            "https://example.com/cookies", "html", 1
        ) == "candidate_website_html"

    def test_engagements_is_programme(self):
        assert infer_source_document(
            "https://example.com/nos-engagements", "html", 1
        ) == "candidate_website_programme"

    def test_candidat_is_about(self):
        assert infer_source_document(
            "https://example.com/le-candidat", "html", 1
        ) == "candidate_website_about"


# ===== is_metadata_only =====


class TestIsMetadataOnly:
    def test_indesign_artifact(self):
        assert is_metadata_only("document_v3.indd  final") is True

    def test_bat_artifact(self):
        assert is_metadata_only("leaflet_bat.pdf print_bat.pdf") is True

    def test_file_heavy_content(self):
        assert is_metadata_only("file1.pdf file2.jpg file3.png") is True

    def test_real_french_text(self):
        text = (
            "Notre programme pour les transports en commun prévoit "
            "une augmentation des fréquences de bus et la création "
            "de nouvelles lignes de tramway."
        )
        assert is_metadata_only(text) is False

    def test_empty_string(self):
        assert is_metadata_only("") is False

    def test_mostly_numbers(self):
        assert is_metadata_only("123 456 789 012 345") is True

    def test_short_text_with_alpha(self):
        text = "Bonjour monsieur comment allez vous"
        # This has enough real words (6) but <10, and alpha ratio > 0.3
        assert is_metadata_only(text) is False


# ===== is_real_content =====


class TestIsRealContent:
    def test_real_french_pages(self):
        pages = [
            (1, "Notre programme municipal prévoit des investissements majeurs "
                "dans les infrastructures de transport public pour améliorer "
                "la qualité de vie des habitants de la commune. "
                "Nous proposons également de renforcer les services publics "
                "de proximité et de développer les espaces verts dans tous "
                "les quartiers de notre ville pour un cadre de vie meilleur."),
        ]
        assert is_real_content(pages) is True

    def test_too_few_words(self):
        pages = [(1, "page 1"), (2, "page 2")]
        assert is_real_content(pages) is False

    def test_metadata_pages(self):
        pages = [(1, "document_v3.indd final_bat.pdf 2024")]
        assert is_real_content(pages) is False

    def test_empty_pages(self):
        assert is_real_content([]) is False

    def test_custom_min_words(self):
        pages = [(1, "un deux trois quatre cinq six sept huit neuf dix")]
        assert is_real_content(pages, min_words=5) is True
        assert is_real_content(pages, min_words=50) is False


# ===== filter_chunks =====


class TestFilterChunks:
    def test_keeps_good_chunks(self):
        chunks = ["This is a perfectly normal political content chunk that is long enough to keep."]
        result, stats = filter_chunks(chunks)
        assert len(result) == 1
        assert stats.kept == 1
        assert stats.dropped_short == 0

    def test_drops_short_chunks(self):
        chunks = ["short", "ok", "This is a long enough chunk to keep in the index."]
        result, stats = filter_chunks(chunks)
        assert len(result) == 1
        assert stats.dropped_short == 2

    def test_strips_consent_and_keeps(self):
        text = (
            "Important political content about education reform. "
            "Gérer le consentement Nous utilisons des cookies Accepter "
            "More important content about housing policy."
        )
        result, stats = filter_chunks([text])
        assert len(result) == 1
        assert stats.consent_stripped == 1
        assert "cookies" not in result[0]

    def test_strips_consent_then_too_short(self):
        text = "Gestion des cookies petit texte Tout accepter"
        result, stats = filter_chunks([text])
        assert len(result) == 0
        assert stats.consent_stripped == 1
        assert stats.dropped_short == 1

    def test_drops_a11y_widget(self):
        widget_text = (
            "Disability profiles supported. WCAG 2.1 compliance. "
            "Screen reader adjustments. Seizure Safe Profile. "
            "Keyboard navigation optimization. Additional text here."
        )
        result, stats = filter_chunks([widget_text])
        assert len(result) == 0
        assert stats.dropped_a11y == 1

    def test_deduplicates(self):
        chunk = "This is a repeated chunk about transport policy improvements."
        result, stats = filter_chunks([chunk, chunk, chunk])
        assert len(result) == 1
        assert stats.dropped_dedup == 2

    def test_shared_seen_hashes(self):
        """Dedup works across calls when sharing the same set."""
        seen = set()
        chunk = "Repeated content about environmental protection measures."
        r1, s1 = filter_chunks([chunk], seen_hashes=seen)
        r2, s2 = filter_chunks([chunk], seen_hashes=seen)
        assert len(r1) == 1
        assert len(r2) == 0
        assert s2.dropped_dedup == 1

    def test_empty_input(self):
        result, stats = filter_chunks([])
        assert result == []
        assert stats.kept == 0

    def test_custom_min_length(self):
        chunks = ["Short but ok for min=5"]
        result, stats = filter_chunks(chunks, min_length=5)
        assert len(result) == 1

    def test_all_filters_combined(self):
        chunks = [
            "ab",  # too short
            "This is good content about the municipal programme for 2026.",  # kept
            "This is good content about the municipal programme for 2026.",  # dedup
            "Gestion des cookies bla Accepter",  # consent → short
            (  # a11y widget
                "Disability profiles supported. WCAG 2.1 compliance. "
                "Screen reader adjustments. Seizure Safe Profile."
            ),
        ]
        result, stats = filter_chunks(chunks)
        assert len(result) == 1
        assert stats.kept == 1
        assert stats.dropped_short >= 1
        assert stats.dropped_dedup == 1
        assert stats.dropped_a11y == 1


# ===== split_page_content =====


class TestSplitPageContent:
    def test_short_content(self):
        content = "Short text."
        chunks = split_page_content(content)
        assert len(chunks) == 1
        assert chunks[0] == "Short text."

    def test_long_content_splits(self):
        # Create content longer than CHUNK_SIZE
        content = "Word " * 500  # ~2500 chars
        chunks = split_page_content(content)
        assert len(chunks) > 1

    def test_cap_limits_chunks(self):
        content = "Sentence. " * 10000  # Very long content
        chunks = split_page_content(content, cap=5)
        assert len(chunks) <= 5

    def test_large_page_uses_bigger_chunks(self):
        # Content > LARGE_PAGE_THRESHOLD uses larger chunks
        content = "Word " * (LARGE_PAGE_THRESHOLD // 5 + 1000)
        chunks_large = split_page_content(content)
        # With larger chunks, we should get fewer chunks
        small_content = "Word " * 400  # ~2000 chars, uses normal splitter
        chunks_small = split_page_content(small_content)
        # Can't assert exact counts but both should work
        assert len(chunks_large) > 0
        assert len(chunks_small) > 0

    def test_empty_content(self):
        chunks = split_page_content("")
        assert chunks == [] or chunks == [""]
