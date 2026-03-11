"""Pipeline node: download professions de foi PDFs from the French interior ministry.

Target: https://programme-candidats.interieur.gouv.fr/elections-municipales-2026/
PDF URL pattern: {BASE_URL}/data-pdf/{tour}-{commune_code}-{panneau}.pdf

The node uses candidatures data (from the candidatures node) to know which
commune codes and panneau numbers exist, then tries to download each PDF.
Only communes >= 2,500 inhabitants have professions de foi online.

Incremental strategy:
    - Checkpoint stores ``{commune_code: last_scraped_at}`` so re-runs only
      process communes that haven't been scraped yet.
    - ``force=True`` clears all per-commune checkpoints and re-scrapes everything.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    register_node,
    save_checkpoint,
    update_status,
    NodeStatus,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://programme-candidats.interieur.gouv.fr/elections-municipales-2026"
PDF_URL_TPL = f"{BASE_URL}/data-pdf/{{tour}}-{{commune_code}}-{{panneau}}.pdf"

# Directory to store downloaded PDFs locally
_PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "chatvote_professions_pdfs"

# Request headers
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
    "Referer": f"{BASE_URL}/",
}

# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------
_cached_pdfs: dict[str, list[dict]] | None = None


def get_professions() -> dict[str, list[dict]] | None:
    """Return {commune_code: [{panneau, list_name, pdf_url, ...}]} or ``None``."""
    return _cached_pdfs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _download_pdf(
    session: aiohttp.ClientSession,
    commune_code: str,
    panneau: str,
    tour: int = 1,
) -> dict | None:
    """Try to download a single PDF. Returns metadata dict or None if 404/error."""
    url = PDF_URL_TPL.format(tour=tour, commune_code=commune_code, panneau=panneau)
    try:
        async with session.get(url) as resp:
            if resp.status in (404, 403):
                return None
            if resp.status != 200:
                logger.debug("[professions] %d for %s", resp.status, url)
                return None

            content = await resp.read()
            if not content[:4] == b"%PDF":
                return None

            # Save locally
            pdf_dir = _PDF_CACHE_DIR / commune_code
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = pdf_dir / f"{tour}-{commune_code}-{panneau}.pdf"
            pdf_path.write_bytes(content)

            return {
                "panneau": panneau,
                "pdf_url": url,
                "pdf_local_path": str(pdf_path),
                "pdf_size_bytes": len(content),
            }
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.debug("[professions] download error for %s: %s", url, exc)
        return None


async def _scrape_commune(
    session: aiohttp.ClientSession,
    commune_code: str,
    panneaux: list[str],
    tour: int = 1,
) -> list[dict]:
    """Download all PDFs for a commune using known panneau numbers."""
    results = []
    tasks = [
        _download_pdf(session, commune_code, p, tour)
        for p in panneaux
    ]
    downloaded = await asyncio.gather(*tasks, return_exceptions=True)
    for item in downloaded:
        if isinstance(item, dict) and item is not None:
            results.append(item)
    return results


# ---------------------------------------------------------------------------
# Node implementation
# ---------------------------------------------------------------------------
class ProfessionsNode(DataSourceNode):
    node_id = "professions"
    label = "Professions de foi"
    default_settings: dict[str, Any] = {
        "top_communes": 287,
        "max_pdfs_per_commune": 50,
        "tour": 1,
        "concurrency": 10,
    }

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        global _cached_pdfs

        top_n: int = int(cfg.settings.get("top_communes", 287))
        max_pdfs: int = int(cfg.settings.get("max_pdfs_per_commune", 50))
        tour: int = int(cfg.settings.get("tour", 1))
        concurrency: int = int(cfg.settings.get("concurrency", 10))

        # ------------------------------------------------------------------
        # 1. Get target communes from population node
        # ------------------------------------------------------------------
        from src.services.data_pipeline.population import get_top_communes

        communes = get_top_communes()
        if not communes:
            raise RuntimeError(
                "Population node must run first — no communes data available"
            )

        target_codes = list(communes.keys())[:top_n]
        logger.info(
            "[professions] targeting %d communes (tour=%d, max_pdfs=%d)",
            len(target_codes), tour, max_pdfs,
        )

        # ------------------------------------------------------------------
        # 2. Get panneau numbers from candidatures node
        # ------------------------------------------------------------------
        from src.services.data_pipeline.candidatures import get_candidatures

        candidatures = get_candidatures()
        if not candidatures:
            logger.warning(
                "[professions] candidatures not available — will try panneau 1-20 for each commune"
            )

        # ------------------------------------------------------------------
        # 3. Clear checkpoints if forced
        # ------------------------------------------------------------------
        if force:
            cfg.checkpoints = {}
            logger.info("[professions] force=True, cleared all commune checkpoints")

        # ------------------------------------------------------------------
        # 4. Download PDFs for each commune
        # ------------------------------------------------------------------
        all_pdfs: dict[str, list[dict]] = {}
        communes_scraped = 0
        communes_skipped = 0
        communes_with_pdfs = 0
        communes_no_pdfs = 0
        total_pdfs_found = 0
        total_bytes = 0

        now_iso = datetime.now(timezone.utc).isoformat()
        started_at = datetime.now(timezone.utc).isoformat()
        import time as _time
        t0 = _time.monotonic()
        sem = asyncio.Semaphore(concurrency)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
            for code in target_codes:
                commune_info = communes.get(code, {})
                commune_name = commune_info.get("nom", code)

                # Check per-commune checkpoint (skip if already done)
                last_scraped = cfg.checkpoints.get(code)
                if last_scraped and not force:
                    communes_skipped += 1
                    continue

                # Determine panneau numbers to try
                if candidatures and code in candidatures:
                    panneaux = list(candidatures[code].get("lists", {}).keys())
                else:
                    panneaux = [str(i) for i in range(1, 21)]

                # Download PDFs
                async with sem:
                    try:
                        pdfs = await _scrape_commune(session, code, panneaux, tour)
                        pdfs = pdfs[:max_pdfs]
                    except Exception as exc:
                        logger.warning(
                            "[professions] failed to scrape %s (%s): %s",
                            code, commune_name, exc,
                        )
                        continue

                # Enrich with candidatures metadata
                if candidatures and code in candidatures:
                    lists_data = candidatures[code].get("lists", {})
                    for pdf in pdfs:
                        p = pdf.get("panneau", "")
                        if p in lists_data:
                            lst = lists_data[p]
                            pdf["list_name"] = lst.get("list_label", "")
                            pdf["list_short"] = lst.get("list_short_label", "")
                            pdf["nuance_code"] = lst.get("nuance_code", "")
                            pdf["tete_de_liste"] = (
                                f"{lst.get('head_last_name', '')} {lst.get('head_first_name', '')}"
                            ).strip()

                if pdfs:
                    all_pdfs[code] = pdfs
                    total_pdfs_found += len(pdfs)
                    total_bytes += sum(p.get("pdf_size_bytes", 0) for p in pdfs)
                    communes_with_pdfs += 1

                    # Persist has_manifesto to Firestore candidates immediately
                    from src.firebase_service import async_db
                    for pdf in pdfs:
                        panneau = pdf.get("panneau", "")
                        cand_id = f"cand-{code}-{panneau}"
                        try:
                            ref = async_db.collection("candidates").document(cand_id)
                            await ref.set({
                                "has_manifesto": True,
                                "manifesto_pdf_url": pdf.get("pdf_url", ""),
                            }, merge=True)
                        except Exception:
                            pass  # candidate doc may not exist yet
                else:
                    communes_no_pdfs += 1

                communes_scraped += 1
                cfg.checkpoints[code] = now_iso

                # Periodic checkpoint + live progress update
                if communes_scraped % 10 == 0:
                    elapsed = _time.monotonic() - t0
                    rate = communes_scraped / elapsed if elapsed > 0 else 0
                    remaining = (len(target_codes) - communes_scraped - communes_skipped) / rate if rate > 0 else 0
                    await save_checkpoint(cfg.node_id, cfg.checkpoints)
                    await update_status(
                        cfg.node_id,
                        NodeStatus.RUNNING,
                        counts={
                            "communes_scraped": communes_scraped,
                            "communes_total": len(target_codes),
                            "communes_skipped": communes_skipped,
                            "communes_with_pdfs": communes_with_pdfs,
                            "communes_no_pdfs": communes_no_pdfs,
                            "pdfs_found": total_pdfs_found,
                            "total_size_mb": round(total_bytes / (1024 * 1024), 1),
                            "rate_communes_per_sec": round(rate, 1),
                            "elapsed_s": round(elapsed, 1),
                            "eta_s": round(remaining, 0),
                            "started_at": started_at,
                        },
                    )
                    logger.info(
                        "[professions] progress %d/%d — %d PDFs (%.1f MB) — %.1f/s — ETA %.0fs",
                        communes_scraped, len(target_codes), total_pdfs_found,
                        total_bytes / (1024 * 1024), rate, remaining,
                    )

        # ------------------------------------------------------------------
        # 5. Update cache and save
        # ------------------------------------------------------------------
        _cached_pdfs = all_pdfs
        await save_checkpoint(cfg.node_id, cfg.checkpoints)

        elapsed = _time.monotonic() - t0
        cfg.counts = {
            "communes_scraped": communes_scraped,
            "communes_skipped": communes_skipped,
            "communes_with_pdfs": communes_with_pdfs,
            "communes_no_pdfs": communes_no_pdfs,
            "pdfs_found": total_pdfs_found,
            "total_size_mb": round(total_bytes / (1024 * 1024), 1),
            "elapsed_s": round(elapsed, 1),
        }

        logger.info(
            "[professions] done — scraped=%d  skipped=%d  pdfs_found=%d",
            communes_scraped, communes_skipped, total_pdfs_found,
        )

        return cfg


register_node(ProfessionsNode())
