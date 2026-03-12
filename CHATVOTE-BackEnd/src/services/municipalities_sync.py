# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Service to sync French municipalities from geo.api.gouv.fr

This script fetches all French communes and saves them to a JSON file
that can be imported to Firestore.

Usage:
    python -m src.services.municipalities_sync
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# API endpoint
GEO_API_URL = "https://geo.api.gouv.fr/communes"
GEO_API_PARAMS = {
    "fields": "code,nom,epci,zone,population,surface,codesPostaux,codeRegion,departement,codeDepartement,siren,region,codeEpci"
}

# Output path
OUTPUT_DIR = Path(__file__).parent.parent.parent / "firebase" / "firestore_data" / "dev"
OUTPUT_FILE = OUTPUT_DIR / "municipalities.json"


async def fetch_municipalities() -> list[dict[str, Any]]:
    """Fetch all French municipalities from geo.api.gouv.fr."""
    logger.info(f"Fetching municipalities from {GEO_API_URL}")

    async with aiohttp.ClientSession() as session:
        async with session.get(GEO_API_URL, params=GEO_API_PARAMS) as response:
            if response.status != 200:
                raise Exception(
                    f"Failed to fetch municipalities: {response.status} {await response.text()}"
                )

            data = await response.json()
            logger.info(f"Fetched {len(data)} municipalities")
            return data


def transform_to_firestore_format(
    municipalities: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Transform the API response to Firestore format.

    Uses the commune code (INSEE code) as the document ID.
    """
    result = {}

    for commune in municipalities:
        code = commune.get("code")
        if not code:
            logger.warning(f"Skipping municipality without code: {commune}")
            continue

        # Add metadata
        commune["_syncedAt"] = datetime.utcnow().isoformat()

        result[code] = commune

    logger.info(f"Prepared {len(result)} municipalities for Firestore import")
    return result


def save_to_file(data: dict[str, Any], filepath: Path) -> None:
    """Save data to a JSON file."""
    # Ensure directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(data)} municipalities to {filepath}")


async def sync_municipalities() -> int:
    """
    Main sync function.

    Fetches municipalities from the API and saves them to the output file.
    Returns the number of municipalities synced.
    """
    logger.info("Starting municipalities sync...")

    # Fetch from API
    municipalities = await fetch_municipalities()

    # Transform to Firestore format
    data = transform_to_firestore_format(municipalities)

    # Save to file
    save_to_file(data, OUTPUT_FILE)

    logger.info(f"Sync complete: {len(data)} municipalities")
    return len(data)


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        count = asyncio.run(sync_municipalities())
        print(f"✅ Successfully synced {count} municipalities to {OUTPUT_FILE}")
    except Exception as e:
        logger.error(f"Failed to sync municipalities: {e}", exc_info=True)
        print(f"❌ Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
