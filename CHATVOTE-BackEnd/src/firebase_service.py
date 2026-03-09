# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import base64
import json
import os
import time
from typing import Any, List, Optional
import firebase_admin
from firebase_admin import firestore, credentials, firestore_async
from pathlib import Path

from src.models.candidate import Candidate
from src.models.chat import CachedResponse
from src.models.party import Party
from src.utils import load_env

import logging as _logging

_fb_logger = _logging.getLogger(__name__)

load_env()

env = os.getenv("ENV", "dev")

_fb_logger.info(f"firebase_service: initializing (ENV={env})")

if env == "local":
    os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": "chat-vote-dev"})
else:
    credentials_path = (
        "chat-vote-firebase-adminsdk.json"
        if env == "prod"
        else "chat-vote-dev-firebase-adminsdk-fbsvc-5357066618.json"
    )

    cred = None
    if Path(credentials_path).exists():
        _fb_logger.info(f"firebase_service: using credentials file {credentials_path}")
        cred = credentials.Certificate(credentials_path)
    elif os.getenv("FIREBASE_CREDENTIALS_BASE64"):
        _fb_logger.info("firebase_service: using FIREBASE_CREDENTIALS_BASE64 env var")
        cred_data = json.loads(base64.b64decode(os.environ["FIREBASE_CREDENTIALS_BASE64"]))
        cred = credentials.Certificate(cred_data)
    else:
        _fb_logger.warning("firebase_service: no credentials found, using default init")

    if cred:
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()

_fb_logger.info("firebase_service: creating Firestore clients...")
db = firestore.client()
_fb_logger.info("firebase_service: sync client OK")

async_db = firestore_async.client()
_fb_logger.info("firebase_service: async client OK")

# ---------------------------------------------------------------------------
# In-memory TTL cache for static Firestore data (parties rarely change)
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))

_cache: dict[str, Any] = {}
_cache_expiry: dict[str, float] = {}


async def _cached_get(key: str, fetch_fn: Any) -> Any:
    """Return cached value if fresh, else call fetch_fn() and cache the result."""
    now = time.time()
    if key in _cache and _cache_expiry.get(key, 0.0) > now:
        return _cache[key]
    result = await fetch_fn()
    _cache[key] = result
    _cache_expiry[key] = now + CACHE_TTL_SECONDS
    return result


async def aget_parties() -> list[Party]:
    import asyncio

    async def _fetch() -> list[Party]:
        def _sync():
            return [Party(**p.to_dict()) for p in db.collection("parties").stream()]
        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    return await _cached_get("parties", _fetch)


async def aget_party_by_id(party_id: str) -> Optional[Party]:
    import asyncio

    async def _fetch() -> Optional[Party]:
        def _sync():
            doc = db.collection("parties").document(party_id).get()
            return Party(**doc.to_dict()) if doc.exists else None
        return await asyncio.get_event_loop().run_in_executor(None, _sync)

    return await _cached_get(f"party:{party_id}", _fetch)


async def aget_proposed_questions_for_party(party_id: str) -> list[str]:
    async def _fetch() -> list[str]:
        questions = async_db.collection(
            f"proposed_questions/{party_id}/questions"
        ).stream()
        return [question.get("content") async for question in questions]

    return await _cached_get(f"proposed_questions:{party_id}", _fetch)


async def aget_cached_answers_for_party(
    party_id: str, cache_key: str
) -> list[CachedResponse]:
    cached_answers = async_db.collection(
        f"cached_answers/{party_id}/{cache_key}"
    ).stream()
    return [
        CachedResponse(**cached_answer.to_dict())
        async for cached_answer in cached_answers
    ]


async def awrite_cached_answer_for_party(
    party_id: str, cache_key: str, cached_answer: CachedResponse
) -> None:
    cached_answer_ref = async_db.collection(
        f"cached_answers/{party_id}/{cache_key}"
    ).document()
    await cached_answer_ref.set(cached_answer.model_dump())


async def awrite_llm_status(is_at_rate_limit: bool) -> None:
    llm_status_ref = async_db.collection("system_status").document("llm_status")
    await llm_status_ref.set({"is_at_rate_limit": is_at_rate_limit})


# ==================== Candidate Functions ====================


async def aget_candidates() -> List[Candidate]:
    """Get all candidates from Firestore (cached)."""
    async def _fetch() -> List[Candidate]:
        candidates = async_db.collection("candidates").stream()
        return [Candidate(**candidate.to_dict()) async for candidate in candidates]

    return await _cached_get("candidates", _fetch)


async def aget_candidates_by_municipality(municipality_code: str) -> List[Candidate]:
    """Get all candidates for a specific municipality by its INSEE code."""
    candidates = (
        async_db.collection("candidates")
        .where("municipality_code", "==", municipality_code)
        .stream()
    )
    return [Candidate(**candidate.to_dict()) async for candidate in candidates]


async def aget_candidate_by_id(candidate_id: str) -> Optional[Candidate]:
    """Get a specific candidate by their ID."""
    candidate_ref = async_db.collection("candidates").document(candidate_id)
    candidate = await candidate_ref.get()
    if candidate.exists:
        return Candidate(**candidate.to_dict())
    return None


async def aget_candidates_with_website() -> List[Candidate]:
    """Get all candidates that have a website URL defined."""
    import asyncio

    def _sync():
        result = []
        for candidate in db.collection("candidates").stream():
            candidate_data = candidate.to_dict()
            if candidate_data.get("website_url"):
                result.append(Candidate(**candidate_data))
        return result

    return await asyncio.get_event_loop().run_in_executor(None, _sync)


async def aget_candidates_by_election_type(election_type_id: str) -> List[Candidate]:
    """Get all candidates for a specific election type."""
    candidates = (
        async_db.collection("candidates")
        .where("election_type_id", "==", election_type_id)
        .stream()
    )
    return [Candidate(**candidate.to_dict()) async for candidate in candidates]
