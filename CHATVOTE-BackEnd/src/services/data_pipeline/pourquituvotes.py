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

import json as _json
import logging
import re
import time as _time
import unicodedata
from datetime import datetime, timezone
from typing import Any

import aiohttp

from src.services.data_pipeline.url_cache import cached_fetch_text
from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    register_node,
    save_checkpoint,
)
from src.services.data_pipeline.population import get_all_communes, get_top_communes

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

        # Use ALL communes for matching — pourquituvotes.fr only covers ~135
        # cities so there's no performance concern, and we want to capture all
        # available data regardless of the communes_to_scrap setting.
        all_communes = get_all_communes()
        if not all_communes:
            raise RuntimeError(
                "Population node must run first (get_all_communes() returned None)"
            )

        # Build commune name → INSEE code mapping for matching
        communes_by_name: dict[str, str] = {}
        for code, info in all_communes.items():
            communes_by_name[_norm(info["nom"])] = code

        async with aiohttp.ClientSession() as session:
            # 1. Fetch all ville slugs
            _t_villes = _time.monotonic()
            villes_text = await cached_fetch_text(session, VILLES_URL)
            if villes_text is None:
                raise RuntimeError(f"Failed to fetch {VILLES_URL}")
            villes = _json.loads(villes_text)
            logger.info("[node:timing] [pourquituvotes:timing] villes_fetch took %.2fs, %d villes", _time.monotonic() - _t_villes, len(villes))

            logger.info("[pourquituvotes] fetched %d villes", len(villes))

            result_map: dict[tuple[str, str], str] = {}
            villes_matched = 0
            urls_found = 0
            villes_skipped = 0

            # 2. For each ville, fetch election data
            _t_all_villes = _time.monotonic()
            for ville in villes:
                slug = ville.get("id", "")
                ville_name = ville.get("nom", "")
                if not slug:
                    continue

                # Match ville to our commune list
                # Strip parenthesized suffix like "(La Réunion)" before matching
                clean_name = re.sub(r"\s*\(.*\)\s*$", "", ville_name).strip()
                norm_name = _norm(clean_name)
                code = communes_by_name.get(norm_name)
                if not code:
                    villes_skipped += 1
                    logger.warning(
                        "[pourquituvotes] no commune match for ville %r (norm=%r, slug=%s)",
                        ville_name, norm_name, slug,
                    )
                    continue

                url = ELECTION_URL_TPL.format(slug=slug)
                try:
                    _t_ville_fetch = _time.monotonic()
                    ville_text = await cached_fetch_text(session, url)
                    if ville_text is None:
                        logger.debug(
                            "[pourquituvotes] %s returned non-200", slug
                        )
                        continue
                    data = _json.loads(ville_text)
                    _ville_fetch_elapsed = _time.monotonic() - _t_ville_fetch
                    if _ville_fetch_elapsed > 1.0:
                        logger.info("[node:timing] [pourquituvotes:timing] ville %s fetch took %.2fs", slug, _ville_fetch_elapsed)
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

        logger.info("[node:timing] [pourquituvotes:timing] all_villes_processed took %.2fs, %d matched", _time.monotonic() - _t_all_villes, villes_matched)
        _cached_urls = result_map

        # Merge into the websites cache if available
        from src.services.data_pipeline.websites import get_websites

        _t_merge = _time.monotonic()
        websites = get_websites()
        if websites is not None:
            merged = 0
            for key, url in result_map.items():
                if key not in websites:
                    websites[key] = url
                    merged += 1
            logger.info("[node:timing] [pourquituvotes:timing] cache_merge took %.2fs, %d new", _time.monotonic() - _t_merge, merged)
            logger.info(
                "[pourquituvotes] merged %d new URLs into websites cache", merged
            )

        cfg.checkpoints["cached_at"] = datetime.now(timezone.utc).isoformat()
        await save_checkpoint(cfg.node_id, cfg.checkpoints)

        # Show coverage relative to top communes target
        top_communes = get_top_communes()
        communes_target = len(top_communes) if top_communes else 0

        cfg.counts = {
            "communes_target": communes_target,
            "villes_total": len(villes),
            "villes_matched": villes_matched,
            "villes_skipped": villes_skipped,
            "campaign_urls_found": urls_found,
        }

        logger.info(
            "[pourquituvotes] done — %d villes matched, %d campaign URLs found",
            villes_matched,
            urls_found,
        )

        return cfg


register_node(PourQuiTuVotesNode())
