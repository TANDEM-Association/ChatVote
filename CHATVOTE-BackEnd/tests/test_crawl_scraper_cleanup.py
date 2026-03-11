"""Tests for crawl_scraper content cleanup logic.

Validates junk detection and OCR visual description filtering using
real examples from the crawl service's Google Drive output.

Run:
    poetry run pytest tests/test_crawl_scraper_cleanup.py -v
"""
from __future__ import annotations

import pytest

from src.services.data_pipeline.crawl_scraper import (
    _clean_scraped_pages,
    _is_junk_content,
    _is_ocr_visual_description,
)
from src.services.candidate_website_scraper import ScrapedPage


# ---------------------------------------------------------------------------
# _is_junk_content
# ---------------------------------------------------------------------------

class TestIsJunkContent:
    """Test the basic junk content filter."""

    @pytest.mark.parametrize("text", [
        "",
        "   ",
        "email",
        "  Email  ",
        "e-mail",
        "E - mail",
        "contact",
        "menu",
        "nav",
        "footer",
        "cookie",
        "RGPD",
        "Loading...",
        "chargement...",
        "Veuillez patienter",
        "accueil",
        "Home",
        "bienvenue",
        "suivez-nous",
        "Follow us",
        "lire la suite",
        "Read more",
        "En savoir plus",
        "https://example.com/some-page",
        "short text",  # < 80 chars
        "hi there",
        "a map pin icon.",
        "'Beno'\n'AIVR'",
        "White arrow pointing to the right.",
        "an orange arrow pointing to the right.",
        "Years: 2026, 2032\nNo additional text or data present",
        "AVEC Michèle Picard\nUNIR RÉSISTER AGIR\nEnsemble pour Vénissieux",
        "Handwritten signature with the name \"Gina\" and a dash below it.",
        "the following text:\n\"ense\"\n\"ble\"\n\"pour\"\n\"M\"\n\"oulins\"",
        'Text: "l\'Sauvons Europe"',
    ])
    def test_junk_detected(self, text: str):
        assert _is_junk_content(text) is True, f"Should be junk: {text!r}"

    @pytest.mark.parametrize("text", [
        # Real political content from markdown pages
        "Notre programme pour la ville de Paris inclut des mesures concrètes pour améliorer le transport en commun et réduire la pollution.",
        "# ZFE : Serge Grouard à nouveau à contre-temps - OSE, L'alliance des collectifs citoyens de Gauche",
        "ÉLECTIONS MUNICIPALES ET INTERCOMMUNALES 15 ET 22 MARS 2026 - L'INTERVIEW DE NICOLAS DARAGON - QUELS PROJETS POUR VALENCE",
        "Questionnaire européen à destination des candidats aux élections municipales. Le Mouvement Européen-France, réseau pro-européen.",
        # Real PDF transcription content
        "GRAND MEETING DE CAMPAGNE MARDI 10 MARS 19h - Salle des fêtes de Moulins. Venez nombreux découvrir notre programme.",
        # OCR text that contains actual useful text (with quotes from the image)
        'LES TÊTES DE LISTE ayant signé ces engagements pourront opposer sur leur communication le label "Engagés pour l\'Union européenne"',
    ])
    def test_real_content_kept(self, text: str):
        assert _is_junk_content(text) is False, f"Should keep: {text!r}"


# ---------------------------------------------------------------------------
# _is_ocr_visual_description
# ---------------------------------------------------------------------------

class TestIsOcrVisualDescription:
    """Test the OCR visual description filter.

    The crawl service OCR sometimes describes what an image looks like
    instead of extracting text — these are useless for RAG.
    """

    @pytest.mark.parametrize("text", [
        # Arrow descriptions
        "White arrow pointing to the right on a dark background.",
        "Orange arrow pointing to the right. No other visible text or data.",
        "The image features a white arrow pointing to the right on a blue background.",
        # Image/photo descriptions
        "The image features a logo consisting of a circular design with a central element.",
        "Portrait of a man wearing glasses and a dark jacket.",
        "Group photo of approximately 20 individuals standing close together.",
        "Children playing in a water park area with water features.",
        "People standing outdoors in a grassy, wooded area.",
        "Man with beard and dark hair, wearing a suit and light-colored shirt.",
        # Social media icon descriptions
        "Social media icons: Facebook, Twitter, YouTube, and another icon.",
        "Instagram logo\nNo additional text or data",
        "Facebook logo with a red circle and white lowercase f in the center.",
        # Urban/building descriptions
        "Skyline with various buildings of different heights and architectural styles.",
        "Urban industrial area with multiple buildings and streetlights.",
        # Icon descriptions
        "Icon of three people interconnected in a circular pattern.",
    ])
    def test_visual_description_detected(self, text: str):
        assert _is_ocr_visual_description(text) is True, f"Should be visual: {text!r}"

    @pytest.mark.parametrize("text", [
        # Real text extracted from images
        'LES TÊTES DE LISTE ayant signé ces engagements pourront opposer sur leur communication le label "Engagés pour l\'Union européenne"',
        "Nicolas Daragon candidat pour être maire de Valence. Les résultats depuis 2020: 98% des promesses ont été tenues.",
        "ÉLECTIONS MUNICIPALES 15 & 22 MARS 2026 - Programme de Michèle Picard pour Vénissieux",
        "Benoît FAIVRE - Programme condensé pour les élections municipales de Moulins",
        "Concarneau Citoyenne et Participative - Réponse aux associations et collectifs",
        # OCR that contains real text with some visual context
        'Text: "Valence, ville accueillante pour toutes les générations"',
        'URL: https://www.ose2020.org\nContact: contactez-nous au 06 09 40 67 73',
    ])
    def test_real_ocr_text_kept(self, text: str):
        assert _is_ocr_visual_description(text) is False, f"Should keep: {text!r}"


# ---------------------------------------------------------------------------
# _clean_scraped_pages
# ---------------------------------------------------------------------------

class TestCleanScrapedPages:
    """Test the full cleanup pipeline on ScrapedPage lists."""

    def _page(self, url: str, content: str, page_type: str = "html") -> ScrapedPage:
        return ScrapedPage(url=url, title=url, content=content, page_type=page_type)

    def test_keeps_real_markdown_pages(self):
        pages = [
            self._page("programme.md", "Notre programme pour la ville de Paris inclut des mesures concrètes pour améliorer le transport en commun et réduire la pollution."),
            self._page("candidat.md", "ÉLECTIONS MUNICIPALES ET INTERCOMMUNALES 15 ET 22 MARS 2026 - L'INTERVIEW DE NICOLAS DARAGON - QUELS PROJETS POUR VALENCE"),
        ]
        cleaned = _clean_scraped_pages(pages)
        assert len(cleaned) == 2

    def test_drops_junk_pages(self):
        pages = [
            self._page("good.md", "Notre programme pour la ville de Paris inclut des mesures concrètes pour améliorer le transport en commun."),
            self._page("email.md", "email"),
            self._page("short.md", "hi"),
            self._page("loading.md", "chargement..."),
            self._page("url.md", "https://example.com/page"),
        ]
        cleaned = _clean_scraped_pages(pages)
        assert len(cleaned) == 1
        assert cleaned[0].url == "good.md"

    def test_drops_empty_pages(self):
        pages = [
            self._page("empty.md", ""),
            self._page("whitespace.md", "   \n\n  "),
        ]
        cleaned = _clean_scraped_pages(pages)
        assert len(cleaned) == 0

    def test_keeps_long_pdf_transcriptions(self):
        pages = [
            self._page(
                "programme.md",
                "ÉLECTIONS MUNICIPALES 15 & 22 MARS 2026 " * 50,
                page_type="pdf_transcription",
            ),
        ]
        cleaned = _clean_scraped_pages(pages)
        assert len(cleaned) == 1

    def test_mixed_content(self):
        """Realistic mix of good content and junk from a real crawl."""
        pages = [
            self._page("programme.md", "Notre programme pour la ville inclut des mesures concrètes pour le transport et la pollution." * 3),
            self._page("contact.md", "contact"),
            self._page("nav.md", "menu"),
            self._page("real-article.md", "Le conseil municipal a voté à l'unanimité la mise en place d'une zone à faibles émissions. " * 2),
            self._page("footer.md", "suivez-nous"),
        ]
        cleaned = _clean_scraped_pages(pages)
        assert len(cleaned) == 2
        urls = {p.url for p in cleaned}
        assert urls == {"programme.md", "real-article.md"}
