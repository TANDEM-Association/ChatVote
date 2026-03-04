# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Firestore listener service.

Listens to changes in the parties and candidates collections and triggers
indexation when documents are added or modified.
"""

import asyncio
import logging
from typing import Optional, Callable

from google.cloud.firestore_v1.base_document import DocumentSnapshot
from google.cloud.firestore_v1.watch import ChangeType

from src.firebase_service import db
from src.models.party import Party
from src.models.candidate import Candidate
from src.services.manifesto_indexer import index_party_manifesto
from src.services.candidate_indexer import index_candidate_website

logger = logging.getLogger(__name__)

# Track which parties have been indexed to avoid duplicate work
_indexed_manifesto_urls: dict[str, str] = {}
_indexed_candidate_urls: dict[str, str] = {}

_parties_listener_unsubscribe: Optional[Callable] = None
_candidates_listener_unsubscribe: Optional[Callable] = None
_is_parties_running = False
_is_candidates_running = False
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None

# Legacy aliases for backward compatibility
_listener_unsubscribe: Optional[Callable] = None
_is_running = False


def _on_parties_snapshot(doc_snapshots, changes, read_time) -> None:
    """
    Callback for Firestore listener on parties collection.

    Triggers indexation when a party is added or modified.
    Note: This runs in a separate thread, not the main asyncio event loop.
    """
    for change in changes:
        doc: DocumentSnapshot = change.document
        party_id = doc.id

        if change.type == ChangeType.REMOVED:
            logger.info(f"Party {party_id} was removed")
            # Optionally: delete from Qdrant
            if party_id in _indexed_manifesto_urls:
                del _indexed_manifesto_urls[party_id]
            continue

        # ADDED or MODIFIED
        try:
            party_data = doc.to_dict()
            if not party_data:
                continue

            # Remove party_id from data if present (we use doc.id as party_id)
            party_data.pop("party_id", None)
            party = Party(party_id=party_id, **party_data)
            manifesto_url = party.election_manifesto_url

            # Check if we need to re-index
            if not manifesto_url:
                logger.debug(f"Party {party_id} has no manifesto URL, skipping")
                continue

            # Only re-index if the manifesto URL changed
            if _indexed_manifesto_urls.get(party_id) == manifesto_url:
                logger.debug(f"Party {party_id} manifesto URL unchanged, skipping")
                continue

            action = "Added" if change.type == ChangeType.ADDED else "Modified"
            logger.info(
                f"{action} party detected: {party_id}, triggering indexation..."
            )

            # Schedule indexation in the main event loop (thread-safe)
            if _main_event_loop is not None:
                asyncio.run_coroutine_threadsafe(
                    _index_party_async(party), _main_event_loop
                )
            else:
                logger.warning(
                    f"No event loop available, skipping indexation for {party_id}"
                )

        except Exception as e:
            logger.error(f"Error processing party change for {party_id}: {e}")


def _on_candidates_snapshot(doc_snapshots, changes, read_time) -> None:
    """
    Callback for Firestore listener on candidates collection.

    Triggers website indexation when a candidate is added or modified.
    Note: This runs in a separate thread, not the main asyncio event loop.
    """
    for change in changes:
        doc: DocumentSnapshot = change.document
        candidate_id = doc.id

        if change.type == ChangeType.REMOVED:
            logger.info(f"Candidate {candidate_id} was removed")
            if candidate_id in _indexed_candidate_urls:
                del _indexed_candidate_urls[candidate_id]
            continue

        # ADDED or MODIFIED
        try:
            candidate_data = doc.to_dict()
            if not candidate_data:
                continue

            # Remove candidate_id from data if present (we use doc.id as candidate_id)
            candidate_data.pop("candidate_id", None)
            candidate = Candidate(candidate_id=candidate_id, **candidate_data)
            website_url = candidate.website_url

            # Check if we need to index
            if not website_url:
                logger.debug(f"Candidate {candidate_id} has no website URL, skipping")
                continue

            # Only re-index if the website URL changed
            if _indexed_candidate_urls.get(candidate_id) == website_url:
                logger.debug(
                    f"Candidate {candidate_id} website URL unchanged, skipping"
                )
                continue

            action = "Added" if change.type == ChangeType.ADDED else "Modified"
            logger.info(
                f"{action} candidate detected: {candidate_id} ({candidate.full_name}), "
                f"triggering website indexation..."
            )

            # Schedule indexation in the main event loop (thread-safe)
            if _main_event_loop is not None:
                asyncio.run_coroutine_threadsafe(
                    _index_candidate_async(candidate), _main_event_loop
                )
            else:
                logger.warning(
                    f"No event loop available, skipping indexation for {candidate_id}"
                )

        except Exception as e:
            logger.error(f"Error processing candidate change for {candidate_id}: {e}")


async def _index_party_async(party: Party) -> None:
    """Index a party's manifesto asynchronously."""
    try:
        count = await index_party_manifesto(party)
        if count > 0:
            _indexed_manifesto_urls[party.party_id] = party.election_manifesto_url
            logger.info(f"Indexed {count} chunks for party {party.party_id}")
        else:
            logger.warning(f"No chunks indexed for party {party.party_id}")
    except Exception as e:
        logger.error(f"Failed to index party {party.party_id}: {e}")


async def _index_candidate_async(candidate: Candidate) -> None:
    """Index a candidate's website asynchronously."""
    try:
        count = await index_candidate_website(candidate)
        if count > 0:
            _indexed_candidate_urls[candidate.candidate_id] = (
                candidate.website_url or ""
            )
            logger.info(
                f"Indexed {count} chunks for candidate {candidate.full_name} "
                f"({candidate.candidate_id})"
            )
        else:
            logger.warning(f"No chunks indexed for candidate {candidate.candidate_id}")
    except Exception as e:
        logger.error(f"Failed to index candidate {candidate.candidate_id}: {e}")


def start_parties_listener(
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    """
    Start listening to the parties collection in Firestore.

    Args:
        event_loop: The main asyncio event loop to use for async tasks.
                   If not provided, will try to get the running loop.

    This should be called once at application startup.
    """
    global _parties_listener_unsubscribe, _is_parties_running, _main_event_loop
    global _listener_unsubscribe, _is_running  # Legacy aliases

    if _is_parties_running:
        logger.warning("Parties listener is already running")
        return

    # Store reference to the event loop for thread-safe async execution
    _main_event_loop = event_loop

    logger.info("Starting Firestore listener for parties collection...")

    try:
        parties_ref = db.collection("parties")
        _parties_listener_unsubscribe = parties_ref.on_snapshot(_on_parties_snapshot)
        _is_parties_running = True
        # Legacy aliases
        _listener_unsubscribe = _parties_listener_unsubscribe
        _is_running = True
        logger.info("Firestore parties listener started successfully")
    except Exception as e:
        logger.error(f"Failed to start Firestore parties listener: {e}")
        raise


def start_candidates_listener(
    event_loop: Optional[asyncio.AbstractEventLoop] = None,
) -> None:
    """
    Start listening to the candidates collection in Firestore.

    Args:
        event_loop: The main asyncio event loop to use for async tasks.
                   If not provided, will try to get the running loop.

    This should be called once at application startup.
    """
    global _candidates_listener_unsubscribe, _is_candidates_running, _main_event_loop

    if _is_candidates_running:
        logger.warning("Candidates listener is already running")
        return

    # Store reference to the event loop for thread-safe async execution
    _main_event_loop = event_loop

    logger.info("Starting Firestore listener for candidates collection...")

    try:
        candidates_ref = db.collection("candidates")
        _candidates_listener_unsubscribe = candidates_ref.on_snapshot(
            _on_candidates_snapshot
        )
        _is_candidates_running = True
        logger.info("Firestore candidates listener started successfully")
    except Exception as e:
        logger.error(f"Failed to start Firestore candidates listener: {e}")
        raise


def stop_parties_listener() -> None:
    """Stop the parties Firestore listener."""
    global _parties_listener_unsubscribe, _is_parties_running
    global _listener_unsubscribe, _is_running  # Legacy aliases

    if _parties_listener_unsubscribe:
        _parties_listener_unsubscribe()
        _parties_listener_unsubscribe = None
        _is_parties_running = False
        # Legacy aliases
        _listener_unsubscribe = None
        _is_running = False
        logger.info("Firestore parties listener stopped")


def stop_candidates_listener() -> None:
    """Stop the candidates Firestore listener."""
    global _candidates_listener_unsubscribe, _is_candidates_running

    if _candidates_listener_unsubscribe:
        _candidates_listener_unsubscribe()
        _candidates_listener_unsubscribe = None
        _is_candidates_running = False
        logger.info("Firestore candidates listener stopped")


def stop_all_listeners() -> None:
    """Stop all Firestore listeners."""
    global _main_event_loop

    stop_parties_listener()
    stop_candidates_listener()
    _main_event_loop = None


def is_listener_running() -> bool:
    """Check if the parties listener is currently running (legacy)."""
    return _is_parties_running


def is_parties_listener_running() -> bool:
    """Check if the parties listener is currently running."""
    return _is_parties_running


def is_candidates_listener_running() -> bool:
    """Check if the candidates listener is currently running."""
    return _is_candidates_running
