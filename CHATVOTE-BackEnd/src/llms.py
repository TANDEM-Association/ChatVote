# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import asyncio
import logging
import os
import time
from collections import deque
from typing import AsyncIterator
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.messages.base import BaseMessage, BaseMessageChunk
from pydantic import BaseModel
from src.firebase_service import awrite_llm_status
from src.model_config import (
    GEMINI_2_FLASH,
    GPT_4O,
    GPT_4O_MINI,
    AZURE_GPT_4O_DEPLOYMENT,
    AZURE_GPT_4O_MINI_DEPLOYMENT,
    CLAUDE_SONNET,
    CLAUDE_HAIKU,
    OLLAMA_CHAT_MODEL,
    CAPACITY_GEMINI_2_FLASH,
    CAPACITY_GPT_4O_OPENAI_TIER_5,
    CAPACITY_GPT_4O_AZURE,
    CAPACITY_GPT_4O_MINI_OPENAI_TIER_5,
    CAPACITY_GPT_4O_MINI_AZURE,
    CAPACITY_CLAUDE_SONNET,
    CAPACITY_CLAUDE_HAIKU,
)
from src.models.general import LLM, LLMSize
from src.utils import load_env, safe_load_api_key

load_env()

# Ollama configuration (conditionally initialized)
_ollama_base_url = os.getenv("OLLAMA_BASE_URL")
_ollama_model_name = OLLAMA_CHAT_MODEL
_is_local = os.getenv("ENV") == "local"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cost guardrails — configurable via env vars
# ---------------------------------------------------------------------------
LLM_RATE_LIMIT_RPM = int(os.getenv("LLM_RATE_LIMIT_RPM", "100"))
LLM_COST_WARNING_THRESHOLD = int(os.getenv("LLM_COST_WARNING_THRESHOLD", "500"))

_request_timestamps: deque = deque()  # sliding-window timestamps (last 60 s)
_total_requests: int = 0              # cumulative LLM request counter


def _track_llm_request() -> None:
    """Record one LLM request; warn if RPM or cumulative threshold is exceeded."""
    global _total_requests
    now = time.monotonic()
    _request_timestamps.append(now)
    _total_requests += 1

    # Evict timestamps older than 60 seconds
    cutoff = now - 60.0
    while _request_timestamps and _request_timestamps[0] < cutoff:
        _request_timestamps.popleft()

    rpm = len(_request_timestamps)
    if rpm > LLM_RATE_LIMIT_RPM:
        logger.warning(
            "LLM_RATE_LIMIT_RPM exceeded: %d requests in last 60 s (threshold: %d)",
            rpm,
            LLM_RATE_LIMIT_RPM,
        )
    if _total_requests >= LLM_COST_WARNING_THRESHOLD and _total_requests % LLM_COST_WARNING_THRESHOLD == 0:
        logger.warning(
            "LLM_COST_WARNING_THRESHOLD reached: %d total LLM requests (threshold: %d)",
            _total_requests,
            LLM_COST_WARNING_THRESHOLD,
        )


# Capacity constants imported from model_config

# Load API keys (conditionally)
_azure_api_key = safe_load_api_key("AZURE_OPENAI_API_KEY")
_azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
_azure_api_version = os.getenv("OPENAI_API_VERSION")
_google_api_key = safe_load_api_key("GOOGLE_API_KEY")
_openai_api_key = safe_load_api_key("OPENAI_API_KEY")
_anthropic_api_key = safe_load_api_key("ANTHROPIC_API_KEY")

# Azure OpenAI models (conditionally initialized)
azure_gpt_4o = (
    AzureChatOpenAI(
        azure_endpoint=_azure_endpoint,
        deployment_name=AZURE_GPT_4O_DEPLOYMENT,
        openai_api_version=_azure_api_version,
        api_key=_azure_api_key,
        max_retries=0,
    )
    if _azure_api_key and _azure_endpoint
    else None
)

azure_gpt_4o_mini = (
    AzureChatOpenAI(
        azure_endpoint=_azure_endpoint,
        deployment_name=AZURE_GPT_4O_MINI_DEPLOYMENT,
        openai_api_version=_azure_api_version,
        api_key=_azure_api_key,
        max_retries=0,
    )
    if _azure_api_key and _azure_endpoint
    else None
)

# Google Gemini models (conditionally initialized)
google_gemini_2_flash = (
    ChatGoogleGenerativeAI(
        model=GEMINI_2_FLASH,
        api_key=_google_api_key,
        max_retries=0,
    )
    if _google_api_key
    else None
)

# OpenAI models (conditionally initialized)
openai_gpt_4o = (
    ChatOpenAI(
        model=GPT_4O,
        api_key=_openai_api_key,
        max_retries=0,
    )
    if _openai_api_key
    else None
)

openai_gpt_4o_mini = (
    ChatOpenAI(
        model=GPT_4O_MINI,
        api_key=_openai_api_key,
        max_retries=0,
    )
    if _openai_api_key
    else None
)

# Anthropic Claude models (conditionally initialized)
anthropic_claude_sonnet = (
    ChatAnthropic(
        model=CLAUDE_SONNET,
        api_key=_anthropic_api_key,
        max_retries=0,
    )
    if _anthropic_api_key
    else None
)

anthropic_claude_haiku = (
    ChatAnthropic(
        model=CLAUDE_HAIKU,
        api_key=_anthropic_api_key,
        max_retries=0,
    )
    if _anthropic_api_key
    else None
)

# Scaleway Generative API (OpenAI-compatible)
_scaleway_api_key = safe_load_api_key("SCALEWAY_EMBED_API_KEY")
_scaleway_llm_model = os.getenv("SCALEWAY_LLM_MODEL", "qwen3-235b-a22b-instruct-2507")
scaleway_chat = (
    ChatOpenAI(
        model=_scaleway_llm_model,
        api_key=_scaleway_api_key,
        base_url="https://api.scaleway.ai/v1",
        max_retries=0,
        request_timeout=30,
    )
    if _scaleway_api_key
    else None
)

# Ollama local model (conditionally initialized)
ollama_chat = (
    ChatOllama(
        model=_ollama_model_name,
        base_url=_ollama_base_url,
        max_retries=0,
    )
    if _ollama_base_url
    else None
)

# Build non-deterministic LLMs list dynamically based on available API keys
_base_non_deterministic_llms: list[LLM] = []

if google_gemini_2_flash is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name="google-gemini-2.5-flash",
            model=google_gemini_2_flash,
            sizes=[LLMSize.SMALL, LLMSize.LARGE],
            priority=90,
            user_capacity_per_minute=CAPACITY_GEMINI_2_FLASH,
            is_at_rate_limit=False,
        )
    )

if azure_gpt_4o is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name="azure-gpt-4o",
            model=azure_gpt_4o,
            sizes=[LLMSize.LARGE],
            priority=90,
            user_capacity_per_minute=CAPACITY_GPT_4O_AZURE,
            is_at_rate_limit=False,
            premium_only=True,
        )
    )

if openai_gpt_4o is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name="openai-gpt-4o",
            model=openai_gpt_4o,
            sizes=[LLMSize.LARGE],
            priority=98,
            user_capacity_per_minute=CAPACITY_GPT_4O_OPENAI_TIER_5,
            is_at_rate_limit=False,
            premium_only=False,
        )
    )

if azure_gpt_4o_mini is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name="azure-gpt-4o-mini",
            model=azure_gpt_4o_mini,
            sizes=[LLMSize.SMALL],
            priority=50,
            user_capacity_per_minute=CAPACITY_GPT_4O_MINI_AZURE,
            is_at_rate_limit=False,
        )
    )

if openai_gpt_4o_mini is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name="openai-gpt-4o-mini",
            model=openai_gpt_4o_mini,
            sizes=[LLMSize.SMALL],
            priority=40,
            user_capacity_per_minute=CAPACITY_GPT_4O_MINI_OPENAI_TIER_5,
            is_at_rate_limit=False,
        )
    )

if anthropic_claude_sonnet is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name="anthropic-claude-sonnet",
            model=anthropic_claude_sonnet,
            sizes=[LLMSize.LARGE],
            priority=95,
            user_capacity_per_minute=CAPACITY_CLAUDE_SONNET,
            is_at_rate_limit=False,
        )
    )

if anthropic_claude_haiku is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name="anthropic-claude-haiku",
            model=anthropic_claude_haiku,
            sizes=[LLMSize.SMALL],
            priority=45,
            user_capacity_per_minute=CAPACITY_CLAUDE_HAIKU,
            is_at_rate_limit=False,
        )
    )

if scaleway_chat is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name=f"scaleway-{_scaleway_llm_model}",
            model=scaleway_chat,
            sizes=[LLMSize.SMALL, LLMSize.LARGE],
            priority=100,
            user_capacity_per_minute=60,
            is_at_rate_limit=False,
        )
    )

if ollama_chat is not None:
    _base_non_deterministic_llms.append(
        LLM(
            name=f"ollama-{_ollama_model_name}",
            model=ollama_chat,
            sizes=[LLMSize.SMALL, LLMSize.LARGE],
            priority=100 if _is_local else 10,
            user_capacity_per_minute=999,
            is_at_rate_limit=False,
        )
    )

NON_DETERMINISTIC_LLMS: list[LLM] = _base_non_deterministic_llms

# Log available LLMs at startup
logger.info(
    f"Loaded {len(NON_DETERMINISTIC_LLMS)} non-deterministic LLMs: {[llm.name for llm in NON_DETERMINISTIC_LLMS]}"
)

# Deterministic models (conditionally initialized)
azure_gpt_4o_mini_det = (
    AzureChatOpenAI(
        azure_endpoint=_azure_endpoint,
        deployment_name=AZURE_GPT_4O_MINI_DEPLOYMENT,
        openai_api_version=_azure_api_version,
        api_key=_azure_api_key,
        temperature=0.0,
        max_retries=0,
    )
    if _azure_api_key and _azure_endpoint
    else None
)

google_gemini_2_flash_det = (
    ChatGoogleGenerativeAI(
        model=GEMINI_2_FLASH,
        api_key=_google_api_key,
        temperature=0.0,
        max_retries=0,
    )
    if _google_api_key
    else None
)

openai_gpt_4o_mini_det = (
    ChatOpenAI(
        model=GPT_4O_MINI,
        api_key=_openai_api_key,
        temperature=0.0,
        max_retries=0,
    )
    if _openai_api_key
    else None
)

# Anthropic Claude deterministic models (conditionally initialized)
anthropic_claude_sonnet_det = (
    ChatAnthropic(
        model=CLAUDE_SONNET,
        api_key=_anthropic_api_key,
        temperature=0.0,
        max_retries=0,
    )
    if _anthropic_api_key
    else None
)

anthropic_claude_haiku_det = (
    ChatAnthropic(
        model=CLAUDE_HAIKU,
        api_key=_anthropic_api_key,
        temperature=0.0,
        max_retries=0,
    )
    if _anthropic_api_key
    else None
)

scaleway_chat_det = (
    ChatOpenAI(
        model=_scaleway_llm_model,
        api_key=_scaleway_api_key,
        base_url="https://api.scaleway.ai/v1",
        temperature=0.0,
        max_retries=0,
        request_timeout=15,
    )
    if _scaleway_api_key
    else None
)

ollama_chat_det = (
    ChatOllama(
        model=_ollama_model_name,
        base_url=_ollama_base_url,
        temperature=0.0,
        max_retries=0,
    )
    if _ollama_base_url
    else None
)

# Build deterministic LLMs list dynamically based on available API keys
_base_deterministic_llms: list[LLM] = []

if google_gemini_2_flash_det is not None:
    _base_deterministic_llms.append(
        LLM(
            name="google-gemini-2.5-flash-det",
            model=google_gemini_2_flash_det,
            sizes=[LLMSize.SMALL, LLMSize.LARGE],
            priority=90,
            user_capacity_per_minute=CAPACITY_GEMINI_2_FLASH,
            is_at_rate_limit=False,
        )
    )

if azure_gpt_4o_mini_det is not None:
    _base_deterministic_llms.append(
        LLM(
            name="azure-gpt-4o-mini-det",
            model=azure_gpt_4o_mini_det,
            sizes=[LLMSize.SMALL],
            priority=90,
            user_capacity_per_minute=CAPACITY_GPT_4O_MINI_AZURE,
            is_at_rate_limit=False,
        )
    )

if openai_gpt_4o_mini_det is not None:
    _base_deterministic_llms.append(
        LLM(
            name="openai-gpt-4o-mini-det",
            model=openai_gpt_4o_mini_det,
            sizes=[LLMSize.SMALL],
            priority=80,
            user_capacity_per_minute=CAPACITY_GPT_4O_MINI_OPENAI_TIER_5,
            is_at_rate_limit=False,
        )
    )

if anthropic_claude_sonnet_det is not None:
    _base_deterministic_llms.append(
        LLM(
            name="anthropic-claude-sonnet-det",
            model=anthropic_claude_sonnet_det,
            sizes=[LLMSize.LARGE],
            priority=95,
            user_capacity_per_minute=CAPACITY_CLAUDE_SONNET,
            is_at_rate_limit=False,
        )
    )

if anthropic_claude_haiku_det is not None:
    _base_deterministic_llms.append(
        LLM(
            name="anthropic-claude-haiku-det",
            model=anthropic_claude_haiku_det,
            sizes=[LLMSize.SMALL],
            priority=85,
            user_capacity_per_minute=CAPACITY_CLAUDE_HAIKU,
            is_at_rate_limit=False,
        )
    )

if scaleway_chat_det is not None:
    _base_deterministic_llms.append(
        LLM(
            name=f"scaleway-{_scaleway_llm_model}-det",
            model=scaleway_chat_det,
            sizes=[LLMSize.SMALL, LLMSize.LARGE],
            priority=100,
            user_capacity_per_minute=60,
            is_at_rate_limit=False,
        )
    )

if ollama_chat_det is not None:
    _base_deterministic_llms.append(
        LLM(
            name=f"ollama-{_ollama_model_name}-det",
            model=ollama_chat_det,
            sizes=[LLMSize.SMALL, LLMSize.LARGE],
            priority=100 if _is_local else 10,
            user_capacity_per_minute=999,
            is_at_rate_limit=False,
        )
    )

DETERMINISTIC_LLMS: list[LLM] = _base_deterministic_llms

# Log available deterministic LLMs at startup
logger.info(
    f"Loaded {len(DETERMINISTIC_LLMS)} deterministic LLMs: {[llm.name for llm in DETERMINISTIC_LLMS]}"
)


RATE_LIMIT_AUTO_RESET_SECONDS = int(
    os.getenv("RATE_LIMIT_AUTO_RESET_SECONDS", "60")
)
_rate_limit_reset_task: asyncio.Task | None = None


async def _auto_reset_rate_limits():
    """Background task that waits, then auto-resets all rate limit flags."""
    try:
        await asyncio.sleep(RATE_LIMIT_AUTO_RESET_SECONDS)
        logger.info(
            f"Auto-resetting LLM rate limits after {RATE_LIMIT_AUTO_RESET_SECONDS}s TTL"
        )
        await reset_all_rate_limits()
    except asyncio.CancelledError:
        pass


async def handle_rate_limit_hit_for_all_llms():
    """Called when all LLMs have failed - notify Firestore and schedule auto-reset."""
    global _rate_limit_reset_task
    await awrite_llm_status(is_at_rate_limit=True)
    # Schedule auto-reset to break the deadlock (cancel any previous timer)
    if _rate_limit_reset_task and not _rate_limit_reset_task.done():
        _rate_limit_reset_task.cancel()
    _rate_limit_reset_task = asyncio.create_task(_auto_reset_rate_limits())


async def handle_llm_success():
    """Called when an LLM succeeds - reset the Firestore flag."""
    global _rate_limit_reset_task
    if _rate_limit_reset_task and not _rate_limit_reset_task.done():
        _rate_limit_reset_task.cancel()
        _rate_limit_reset_task = None
    await awrite_llm_status(is_at_rate_limit=False)


async def reset_all_rate_limits():
    """Reset rate limit flags for all LLMs (both in memory and Firestore)."""
    global _rate_limit_reset_task
    if _rate_limit_reset_task and not _rate_limit_reset_task.done():
        _rate_limit_reset_task.cancel()
        _rate_limit_reset_task = None
    for llm in NON_DETERMINISTIC_LLMS:
        llm.is_at_rate_limit = False
    for llm in DETERMINISTIC_LLMS:
        llm.is_at_rate_limit = False
    await awrite_llm_status(is_at_rate_limit=False)
    logger.info("Reset rate limit flags for all LLMs")


async def get_answer_from_llms(
    llms: list[LLM], messages: list[BaseMessage]
) -> BaseMessage:
    llms = sorted(llms, key=lambda x: x.priority, reverse=True)
    back_up_llms = [llm for llm in llms if llm.back_up_only]
    llms = [llm for llm in llms if not llm.back_up_only]

    logger.debug(f"Available LLMs for answer: {[item.name for item in llms]}")
    _track_llm_request()

    for i, llm in enumerate(llms):
        if llm.is_at_rate_limit:
            continue
        try:
            logger.debug(f"Invoking LLM {llm.name}...")
            response = await llm.model.ainvoke(messages)
            llm.is_at_rate_limit = False
            await handle_llm_success()  # Reset Firestore flag on success
            return response
        except Exception as e:
            logger.warning(f"Error invoking LLM {llm.name}: {e}")
            llm.is_at_rate_limit = True
            remaining = [item.name for item in llms[i + 1 :] if not item.is_at_rate_limit]
            if remaining:
                logger.info(f"Falling back to next LLM. Remaining: {remaining}")
            continue

    await handle_rate_limit_hit_for_all_llms()

    logger.info(
        f"All primary LLMs failed, trying backup LLMs: {[item.name for item in back_up_llms]}"
    )
    for llm in back_up_llms:
        try:
            logger.debug(f"Invoking backup LLM {llm.name}...")
            response = await llm.model.ainvoke(messages)
            llm.is_at_rate_limit = False
            await handle_llm_success()  # Reset Firestore flag on success
            return response
        except Exception as e:
            logger.warning(f"Error invoking backup LLM {llm.name}: {e}")
            llm.is_at_rate_limit = True
    raise Exception("All LLMs are at rate limit.")


async def get_structured_output_from_llms(
    llms: list[LLM], messages: list[BaseMessage], schema: dict | type
) -> dict | BaseModel:
    llms = sorted(llms, key=lambda x: x.priority, reverse=True)
    back_up_llms = [llm for llm in llms if llm.back_up_only]
    llms = [llm for llm in llms if not llm.back_up_only]

    logger.debug(
        f"Available LLMs for structured output: {[item.name for item in llms]}"
    )

    for i, llm in enumerate(llms):
        if llm.is_at_rate_limit:
            continue
        try:
            logger.debug(f"Invoking LLM {llm.name} for structured output...")
            prepared_model = llm.model.with_structured_output(schema)
            response = await prepared_model.ainvoke(messages)
            llm.is_at_rate_limit = False
            await handle_llm_success()  # Reset Firestore flag on success
            return response
        except Exception as e:
            logger.warning(f"Error invoking LLM {llm.name}: {e}")
            llm.is_at_rate_limit = True
            remaining = [item.name for item in llms[i + 1 :] if not item.is_at_rate_limit]
            if remaining:
                logger.info(f"Falling back to next LLM. Remaining: {remaining}")
            continue

    # All primary LLMs rate-limited — retry them once (rate limit may have expired)
    for llm in llms:
        try:
            prepared_model = llm.model.with_structured_output(schema)
            response = await prepared_model.ainvoke(messages)
            llm.is_at_rate_limit = False
            await handle_llm_success()
            return response
        except Exception:
            llm.is_at_rate_limit = True

    await handle_rate_limit_hit_for_all_llms()

    logger.info(
        f"All primary LLMs failed, trying backup LLMs: {[item.name for item in back_up_llms]}"
    )
    for llm in back_up_llms:
        try:
            logger.debug(f"Invoking backup LLM {llm.name} for structured output...")
            prepared_model = llm.model.with_structured_output(schema)
            response = await prepared_model.ainvoke(messages)
            llm.is_at_rate_limit = False
            await handle_llm_success()  # Reset Firestore flag on success
            return response
        except Exception as e:
            logger.warning(f"Error invoking backup LLM {llm.name}: {e}")
            llm.is_at_rate_limit = True
    raise Exception("All LLMs are at rate limit.")


def _sort_llms_by_size_preference(
    llms: list[LLM],
    preferred_llm_size: LLMSize,
    use_premium_llms: bool,
) -> list[LLM]:
    """Sort LLMs by size preference and filter premium if needed."""
    if not use_premium_llms:
        llms = [llm for llm in llms if not llm.premium_only]

    if preferred_llm_size == LLMSize.LARGE:
        large_llms = [llm for llm in llms if LLMSize.LARGE in llm.sizes]
        small_llms = [
            llm
            for llm in llms
            if LLMSize.SMALL in llm.sizes and LLMSize.LARGE not in llm.sizes
        ]
        large_llms = sorted(large_llms, key=lambda x: x.priority, reverse=True)
        small_llms = sorted(small_llms, key=lambda x: x.priority, reverse=True)
        return large_llms + small_llms
    elif preferred_llm_size == LLMSize.SMALL:
        small_llms = [llm for llm in llms if LLMSize.SMALL in llm.sizes]
        large_llms = [
            llm
            for llm in llms
            if LLMSize.LARGE in llm.sizes and LLMSize.SMALL not in llm.sizes
        ]
        large_llms = sorted(large_llms, key=lambda x: x.priority, reverse=True)
        small_llms = sorted(small_llms, key=lambda x: x.priority, reverse=True)
        return small_llms + large_llms
    else:
        raise ValueError(f"Invalid preferred LLM size: {preferred_llm_size}")


class StreamResetMarker:
    """
    Special marker yielded by stream_answer_from_llms when a mid-stream fallback occurs.
    Callers should check for this marker and reset their state (clear accumulated response).
    """

    def __init__(self, reason: str, new_llm_name: str):
        self.reason = reason
        self.new_llm_name = new_llm_name


async def stream_answer_from_llms(
    llms: list[LLM],
    messages: list[BaseMessage],
    preferred_llm_size: LLMSize = LLMSize.LARGE,
    use_premium_llms: bool = False,
) -> AsyncIterator[BaseMessageChunk | StreamResetMarker]:
    """
    Stream answer from LLMs with automatic fallback on rate limit errors.

    This function handles errors that occur DURING streaming (mid-stream),
    not just at initialization. If a rate limit error occurs while streaming,
    it automatically switches to the next available LLM and continues.

    IMPORTANT: When a mid-stream fallback occurs, a StreamResetMarker is yielded
    BEFORE the new LLM starts streaming. Callers should check for this marker
    and reset their accumulated response state.
    """
    logger.debug(f"Preferred LLM size: {preferred_llm_size}")
    sorted_llms = _sort_llms_by_size_preference(
        llms, preferred_llm_size, use_premium_llms
    )

    async def resilient_stream() -> AsyncIterator[BaseMessageChunk | StreamResetMarker]:
        """Generator that handles mid-stream errors and falls back to next LLM."""
        _track_llm_request()
        llm_index = 0
        chunks_yielded = 0

        while llm_index < len(sorted_llms):
            llm = sorted_llms[llm_index]
            try:
                logger.info(f"Starting stream with LLM {llm.name}...")
                stream = llm.model.astream(messages)

                async for chunk in stream:
                    chunks_yielded += 1
                    yield chunk

                # Stream completed successfully
                llm.is_at_rate_limit = False
                await handle_llm_success()
                logger.info(
                    f"Stream completed successfully with {llm.name} ({chunks_yielded} chunks)"
                )
                return

            except Exception as e:
                llm.is_at_rate_limit = True
                llm_index += 1

                if llm_index < len(sorted_llms):
                    next_llm = sorted_llms[llm_index]
                    logger.warning(
                        f"Error with LLM {llm.name} after {chunks_yielded} chunks: {e}. "
                        f"Falling back to {next_llm.name}..."
                    )

                    # Yield a reset marker if we had already yielded chunks
                    # This signals the caller to clear accumulated response
                    if chunks_yielded > 0:
                        logger.info(
                            f"Yielding reset marker (had {chunks_yielded} chunks from {llm.name})"
                        )
                        yield StreamResetMarker(
                            reason=f"Rate limit on {llm.name}",
                            new_llm_name=next_llm.name,
                        )

                    # Reset chunk counter for new LLM (we restart the full response)
                    chunks_yielded = 0
                else:
                    logger.error(
                        f"Error with LLM {llm.name}: {e}. No more LLMs to try."
                    )
                    await handle_rate_limit_hit_for_all_llms()
                    raise Exception(f"All LLMs failed. Last error: {e}")

    return resilient_stream()
