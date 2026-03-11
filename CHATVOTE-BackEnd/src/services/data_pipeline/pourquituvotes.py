"""Pipeline node: scrape campaign website URLs from pourquituvotes.fr JSON API.

pourquituvotes.fr is a non-partisan French municipal election comparison tool.
It provides a JSON API with structured candidate data including campaign URLs
(``programmeUrl``).  No HTML parsing needed — pure JSON endpoints.

Endpoints:
    - ``/data/villes.json`` → list of all covered communes (144 as of 2026)
    - ``/data/elections/{slug}-2026.json`` → per-commune candidate data

The extracted campaign URLs are merged into the websites module cache so the
indexer node can scrape and index them alongside the Google Sheet URLs.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

import aiohttp

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    register_node,
    save_checkpoint,
)
from src.services.data_pipeline.population import get_top_communes

logger = logging.getLogger(__name__)

VILLES_URL = "https://pourquituvotes.fr/data/villes.json"
ELECTION_URL_TPL = "https://pourquituvotes.fr/data/elections/{slug}-2026.json"

# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------
_cached_urls: dict[tuple[str, str], str] | None = None


def get_pourquituvotes_urls() -> dict[tuple[str, str], str] | None:
    """Return {(commune_code, norm_name): url} or None."""
    return _cached_urls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    """Normalize for fuzzy matching (strip accents, lowercase, alpha only)."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", s.lower())


def _is_valid_campaign_url(url: str | None) -> bool:
    """Filter out placeholders and non-campaign URLs."""
    if not url or url.strip() in ("#", "", "null"):
        return False
    # Must be a real URL
    if not url.startswith(("http://", "https://")):
        return False
    # Skip news outlet URLs (not actual campaign sites)
    news_domains = (
        "francebleu.fr", "francetvinfo.fr", "lemonde.fr", "lefigaro.fr",
        "liberation.fr", "20minutes.fr", "bfmtv.com", "lci.fr",
        "ouest-france.fr", "laprovence.com", "tribunedelyon.fr",
    )
    for domain in news_domains:
        if domain in url:
            return False
    return True


# ---------------------------------------------------------------------------
# Node implementation
# ---------------------------------------------------------------------------
class PourQuiTuVotesNode(DataSourceNode):
    node_id = "pourquituvotes"
    label = "PourQuiTuVotes.fr"
    default_settings: dict[str, Any] = {}

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        global _cached_urls

        top_communes = get_top_communes()
        if not top_communes:
            raise RuntimeError(
                "Population node must run first (get_top_communes() returned None)"
            )

        # Build commune name → INSEE code mapping for matching
        communes_by_name: dict[str, str] = {}
        for code, info in top_communes.items():
            communes_by_name[_norm(info["nom"])] = code

        async with aiohttp.ClientSession() as session:
            # 1. Fetch all ville slugs
            async with session.get(VILLES_URL) as resp:
                resp.raise_for_status()
                villes = await resp.json()

            logger.info("[pourquituvotes] fetched %d villes", len(villes))

            result_map: dict[tuple[str, str], str] = {}
            villes_matched = 0
            urls_found = 0
            villes_skipped = 0

            # 2. For each ville, fetch election data
            for ville in villes:
                slug = ville.get("id", "")
                ville_name = ville.get("nom", "")
                if not slug:
                    continue

                # Match ville to our commune list
                norm_name = _norm(ville_name)
                code = communes_by_name.get(norm_name)
                if not code:
                    villes_skipped += 1
                    continue

                url = ELECTION_URL_TPL.format(slug=slug)
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            logger.debug(
                                "[pourquituvotes] %s returned %d", slug, resp.status
                            )
                            continue
                        data = await resp.json()
                except Exception as exc:
                    logger.warning("[pourquituvotes] failed to fetch %s: %s", slug, exc)
                    continue

                villes_matched += 1
                candidats = data.get("candidats", [])

                for candidat in candidats:
                    programme_url = candidat.get("programmeUrl")
                    if not _is_valid_campaign_url(programme_url):
                        continue

                    nom = candidat.get("nom", "")
                    candidat_id = candidat.get("id", "")
                    if nom:
                        norm_last = _norm(nom)
                        result_map[(code, norm_last)] = programme_url
                    if candidat_id:
                        result_map[(code, _norm(candidat_id))] = programme_url
                    urls_found += 1

        _cached_urls = result_map

        # Merge into the websites cache if available
        from src.services.data_pipeline.websites import get_websites

        websites = get_websites()
        if websites is not None:
            merged = 0
            for key, url in result_map.items():
                if key not in websites:
                    websites[key] = url
                    merged += 1
            logger.info(
                "[pourquituvotes] merged %d new URLs into websites cache", merged
            )

        await save_checkpoint(cfg.node_id, cfg.checkpoints)

        cfg.counts = {
            "villes_total": len(villes),
            "villes_matched": villes_matched,
            "villes_skipped": villes_skipped,
            "campaign_urls_found": urls_found,
            "unique_entries": len(result_map),
        }

        logger.info(
            "[pourquituvotes] done — %d villes matched, %d campaign URLs found",
            villes_matched,
            urls_found,
        )

        return cfg


register_node(PourQuiTuVotesNode())
