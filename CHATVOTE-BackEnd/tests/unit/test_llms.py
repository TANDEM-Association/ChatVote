# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Unit tests for the LLM failover system in src/llms.py.

All tests run WITHOUT external services (no LLM APIs, no Firebase, no Qdrant).
Firebase and LLM provider imports are mocked at the module level before import.
"""

import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Environment setup — must happen before any src imports
# ---------------------------------------------------------------------------
os.environ.setdefault("API_NAME", "chatvote-api")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")

# ---------------------------------------------------------------------------
# Mock heavy module-level imports BEFORE importing src.llms
# ---------------------------------------------------------------------------
_mock_firebase_service = MagicMock()
_mock_firebase_service.awrite_llm_status = AsyncMock()
sys.modules.setdefault("src.firebase_service", _mock_firebase_service)

# Unset API keys so src.llms skips constructing real LLM instances at module level
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("AZURE_OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OLLAMA_BASE_URL", None)

# Mock LLM provider packages with callables that return FakeListChatModel instances
# so that LLM Pydantic validation passes if any branch constructs an instance at import
from langchain_core.language_models.fake_chat_models import (  # noqa: E402
    FakeListChatModel as _FakeChat,
)


def _make_fake_chat(*args, **kwargs):
    return _FakeChat(responses=["mocked response"])


_mock_google = MagicMock()
_mock_google.ChatGoogleGenerativeAI = _make_fake_chat

_mock_openai = MagicMock()
_mock_openai.ChatOpenAI = _make_fake_chat
_mock_openai.AzureChatOpenAI = _make_fake_chat

_mock_anthropic = MagicMock()
_mock_anthropic.ChatAnthropic = _make_fake_chat

_mock_ollama = MagicMock()
_mock_ollama.ChatOllama = _make_fake_chat

for _mod_name, _mock_mod in [
    ("langchain_google_genai", _mock_google),
    ("langchain_openai", _mock_openai),
    ("langchain_anthropic", _mock_anthropic),
    ("langchain_ollama", _mock_ollama),
]:
    sys.modules[_mod_name] = _mock_mod

# Mock model_config constants so llms.py can resolve them
_mock_model_config = MagicMock()
_mock_model_config.GEMINI_2_FLASH = "gemini-2.0-flash"
_mock_model_config.GPT_4O = "gpt-4o"
_mock_model_config.GPT_4O_MINI = "gpt-4o-mini"
_mock_model_config.AZURE_GPT_4O_DEPLOYMENT = "gpt-4o"
_mock_model_config.AZURE_GPT_4O_MINI_DEPLOYMENT = "gpt-4o-mini"
_mock_model_config.CLAUDE_SONNET = "claude-sonnet-4-5"
_mock_model_config.CLAUDE_HAIKU = "claude-haiku-3-5"
_mock_model_config.OLLAMA_CHAT_MODEL = "llama3.2"
_mock_model_config.CAPACITY_GEMINI_2_FLASH = 200
_mock_model_config.CAPACITY_GPT_4O_OPENAI_TIER_5 = 50
_mock_model_config.CAPACITY_GPT_4O_AZURE = 50
_mock_model_config.CAPACITY_GPT_4O_MINI_OPENAI_TIER_5 = 200
_mock_model_config.CAPACITY_GPT_4O_MINI_AZURE = 200
_mock_model_config.CAPACITY_CLAUDE_SONNET = 50
_mock_model_config.CAPACITY_CLAUDE_HAIKU = 200
sys.modules.setdefault("src.model_config", _mock_model_config)

# Now it is safe to import from src.llms
from langchain_core.language_models.fake_chat_models import FakeListChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from src.models.general import LLM, LLMSize  # noqa: E402
import src.llms as llms_module  # noqa: E402
from src.llms import (  # noqa: E402
    _sort_llms_by_size_preference,
    _track_llm_request,
    StreamResetMarker,
    get_answer_from_llms,
    get_structured_output_from_llms,
    stream_answer_from_llms,
    handle_llm_success,
    handle_rate_limit_hit_for_all_llms,
    reset_all_rate_limits,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_llm(
    name: str,
    priority: int = 100,
    sizes: list[LLMSize] | None = None,
    back_up_only: bool = False,
    premium_only: bool = False,
    responses: list[str] | None = None,
    fail: bool = False,
) -> LLM:
    """Create an LLM instance backed by a FakeListChatModel."""
    model = FakeListChatModel(responses=responses or ["default response"])
    if fail:
        object.__setattr__(
            model, "ainvoke", AsyncMock(side_effect=Exception(f"{name} failed"))
        )

        # Also make astream raise so streaming tests work correctly
        async def _failing_stream(messages, **kwargs):
            raise Exception(f"{name} stream failed")
            # unreachable but makes it an async generator
            yield  # type: ignore[misc]

        object.__setattr__(model, "astream", _failing_stream)
    return LLM(
        name=name,
        model=model,
        sizes=sizes or [LLMSize.LARGE],
        priority=priority,
        user_capacity_per_minute=100,
        is_at_rate_limit=False,
        back_up_only=back_up_only,
        premium_only=premium_only,
    )


def make_streaming_llm(
    name: str,
    priority: int = 100,
    sizes: list[LLMSize] | None = None,
    chunks: list[str] | None = None,
    fail_after: int | None = None,
) -> LLM:
    """
    Create an LLM that streams chunks.
    If fail_after is set, raises after that many chunks.
    """
    _chunks = chunks or ["hello", " world"]

    async def _stream(messages, **kwargs):
        for i, chunk in enumerate(_chunks):
            if fail_after is not None and i >= fail_after:
                raise Exception(f"{name} rate limited mid-stream")
            yield AIMessage(content=chunk)
        if fail_after is not None and len(_chunks) <= fail_after:
            raise Exception(f"{name} rate limited mid-stream")

    model = FakeListChatModel(responses=["hello world"])
    object.__setattr__(model, "astream", _stream)

    return LLM(
        name=name,
        model=model,
        sizes=sizes or [LLMSize.LARGE],
        priority=priority,
        user_capacity_per_minute=100,
        is_at_rate_limit=False,
    )


MESSAGES = [HumanMessage(content="Test question")]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_module_state():
    """
    Reset all module-level mutable state in src.llms between tests.
    This prevents state leakage between tests for _request_timestamps,
    _total_requests, and _rate_limit_reset_task.
    """
    # Clear sliding-window timestamps and cumulative counter
    llms_module._request_timestamps.clear()
    llms_module._total_requests = 0
    # Cancel and clear any pending reset task
    if llms_module._rate_limit_reset_task is not None:
        try:
            llms_module._rate_limit_reset_task.cancel()
        except RuntimeError:
            pass
        llms_module._rate_limit_reset_task = None
    # Patch awrite_llm_status in src.llms so tests never call the real Firestore.
    # This is needed because sys.modules.setdefault may not have replaced the real
    # firebase_service module when other test files load it first.
    with patch("src.llms.awrite_llm_status", new_callable=AsyncMock):
        yield
    # Cleanup after test too
    llms_module._request_timestamps.clear()
    llms_module._total_requests = 0
    if llms_module._rate_limit_reset_task is not None:
        try:
            llms_module._rate_limit_reset_task.cancel()
        except RuntimeError:
            pass
        llms_module._rate_limit_reset_task = None


# ---------------------------------------------------------------------------
# Tests: _track_llm_request
# ---------------------------------------------------------------------------


class TestTrackLlmRequest:
    def test_increments_total_requests(self):
        _track_llm_request()
        assert llms_module._total_requests == 1

    def test_appends_timestamp_to_deque(self):
        before = time.monotonic()
        _track_llm_request()
        after = time.monotonic()
        assert len(llms_module._request_timestamps) == 1
        ts = llms_module._request_timestamps[0]
        assert before <= ts <= after

    def test_multiple_calls_accumulate(self):
        for _ in range(5):
            _track_llm_request()
        assert llms_module._total_requests == 5
        assert len(llms_module._request_timestamps) == 5

    def test_evicts_timestamps_older_than_60s(self):
        # Manually insert a timestamp older than 60 seconds
        old_ts = time.monotonic() - 61.0
        llms_module._request_timestamps.append(old_ts)
        assert len(llms_module._request_timestamps) == 1

        # This call should evict the old timestamp and add its own
        _track_llm_request()
        assert len(llms_module._request_timestamps) == 1
        # The remaining timestamp must be recent (not the old one)
        assert llms_module._request_timestamps[0] > old_ts

    def test_does_not_evict_recent_timestamps(self):
        # Insert a recent timestamp (30 seconds ago — still within window)
        recent_ts = time.monotonic() - 30.0
        llms_module._request_timestamps.append(recent_ts)
        _track_llm_request()
        # Both should survive: the 30s-old one and the new one
        assert len(llms_module._request_timestamps) == 2

    def test_warns_when_rpm_exceeds_threshold(self, caplog):
        original_limit = llms_module.LLM_RATE_LIMIT_RPM
        try:
            llms_module.LLM_RATE_LIMIT_RPM = 3
            import logging

            with caplog.at_level(logging.WARNING, logger="src.llms"):
                for _ in range(4):
                    _track_llm_request()
            assert any(
                "LLM_RATE_LIMIT_RPM exceeded" in r.message for r in caplog.records
            )
        finally:
            llms_module.LLM_RATE_LIMIT_RPM = original_limit

    def test_no_warning_below_rpm_threshold(self, caplog):
        original_limit = llms_module.LLM_RATE_LIMIT_RPM
        try:
            llms_module.LLM_RATE_LIMIT_RPM = 100
            import logging

            with caplog.at_level(logging.WARNING, logger="src.llms"):
                _track_llm_request()
            rpm_warnings = [
                r for r in caplog.records if "LLM_RATE_LIMIT_RPM exceeded" in r.message
            ]
            assert len(rpm_warnings) == 0
        finally:
            llms_module.LLM_RATE_LIMIT_RPM = original_limit

    def test_warns_at_cumulative_threshold(self, caplog):
        original_threshold = llms_module.LLM_COST_WARNING_THRESHOLD
        try:
            llms_module.LLM_COST_WARNING_THRESHOLD = 5
            # Pre-fill total requests to one below threshold
            llms_module._total_requests = 4
            import logging

            with caplog.at_level(logging.WARNING, logger="src.llms"):
                _track_llm_request()  # This brings total to 5 (== threshold)
            assert any(
                "LLM_COST_WARNING_THRESHOLD reached" in r.message
                for r in caplog.records
            )
        finally:
            llms_module.LLM_COST_WARNING_THRESHOLD = original_threshold

    def test_warns_at_multiples_of_cumulative_threshold(self, caplog):
        original_threshold = llms_module.LLM_COST_WARNING_THRESHOLD
        try:
            llms_module.LLM_COST_WARNING_THRESHOLD = 5
            llms_module._total_requests = 9
            import logging

            with caplog.at_level(logging.WARNING, logger="src.llms"):
                _track_llm_request()  # total becomes 10 == 2 * 5
            assert any(
                "LLM_COST_WARNING_THRESHOLD reached" in r.message
                for r in caplog.records
            )
        finally:
            llms_module.LLM_COST_WARNING_THRESHOLD = original_threshold

    def test_does_not_warn_between_cumulative_thresholds(self, caplog):
        original_threshold = llms_module.LLM_COST_WARNING_THRESHOLD
        try:
            llms_module.LLM_COST_WARNING_THRESHOLD = 10
            llms_module._total_requests = 4  # total will be 5 — not a multiple of 10
            import logging

            with caplog.at_level(logging.WARNING, logger="src.llms"):
                _track_llm_request()
            cost_warnings = [
                r
                for r in caplog.records
                if "LLM_COST_WARNING_THRESHOLD reached" in r.message
            ]
            assert len(cost_warnings) == 0
        finally:
            llms_module.LLM_COST_WARNING_THRESHOLD = original_threshold


# ---------------------------------------------------------------------------
# Tests: _sort_llms_by_size_preference
# ---------------------------------------------------------------------------


class TestSortLlmsBySizePreference:
    def _make_large(self, name, priority=100):
        return make_llm(name, priority=priority, sizes=[LLMSize.LARGE])

    def _make_small(self, name, priority=100):
        return make_llm(name, priority=priority, sizes=[LLMSize.SMALL])

    def _make_both(self, name, priority=100):
        return make_llm(name, priority=priority, sizes=[LLMSize.SMALL, LLMSize.LARGE])

    def test_large_preferred_puts_large_llms_first(self):
        small = self._make_small("small-a")
        large = self._make_large("large-a")
        result = _sort_llms_by_size_preference([small, large], LLMSize.LARGE, True)
        assert result[0].name == "large-a"
        assert result[1].name == "small-a"

    def test_small_preferred_puts_small_llms_first(self):
        small = self._make_small("small-a")
        large = self._make_large("large-a")
        result = _sort_llms_by_size_preference([small, large], LLMSize.SMALL, True)
        assert result[0].name == "small-a"
        assert result[1].name == "large-a"

    def test_large_preferred_sorts_large_by_priority_desc(self):
        large_low = self._make_large("large-low", priority=50)
        large_high = self._make_large("large-high", priority=90)
        result = _sort_llms_by_size_preference(
            [large_low, large_high], LLMSize.LARGE, True
        )
        assert result[0].name == "large-high"
        assert result[1].name == "large-low"

    def test_small_preferred_sorts_small_by_priority_desc(self):
        small_low = self._make_small("small-low", priority=30)
        small_high = self._make_small("small-high", priority=70)
        result = _sort_llms_by_size_preference(
            [small_low, small_high], LLMSize.SMALL, True
        )
        assert result[0].name == "small-high"
        assert result[1].name == "small-low"

    def test_dual_size_llm_treated_as_large_when_large_preferred(self):
        """An LLM supporting both sizes appears in the large group when LARGE preferred."""
        both = self._make_both("both-a", priority=80)
        small_only = self._make_small("small-only", priority=95)
        result = _sort_llms_by_size_preference([both, small_only], LLMSize.LARGE, True)
        # "both-a" has LARGE in sizes → goes into large group
        assert result[0].name == "both-a"
        # "small-only" does NOT have LARGE → goes into small group
        assert result[1].name == "small-only"

    def test_dual_size_llm_treated_as_small_when_small_preferred(self):
        """An LLM supporting both sizes appears in the small group when SMALL preferred."""
        both = self._make_both("both-a", priority=80)
        large_only = self._make_large("large-only", priority=95)
        result = _sort_llms_by_size_preference([both, large_only], LLMSize.SMALL, True)
        # "both-a" has SMALL in sizes → goes into small group
        assert result[0].name == "both-a"
        # "large-only" does NOT have SMALL → goes into large group
        assert result[1].name == "large-only"

    def test_filters_premium_only_when_use_premium_false(self):
        premium = make_llm("premium-a", premium_only=True, sizes=[LLMSize.LARGE])
        regular = self._make_large("regular-a")
        result = _sort_llms_by_size_preference(
            [premium, regular], LLMSize.LARGE, use_premium_llms=False
        )
        names = [llm.name for llm in result]
        assert "premium-a" not in names
        assert "regular-a" in names

    def test_includes_premium_when_use_premium_true(self):
        premium = make_llm("premium-a", premium_only=True, sizes=[LLMSize.LARGE])
        regular = self._make_large("regular-a")
        result = _sort_llms_by_size_preference(
            [premium, regular], LLMSize.LARGE, use_premium_llms=True
        )
        names = [llm.name for llm in result]
        assert "premium-a" in names
        assert "regular-a" in names

    def test_raises_value_error_for_invalid_size(self):
        with pytest.raises(ValueError, match="Invalid preferred LLM size"):
            _sort_llms_by_size_preference([], "invalid_size", True)  # type: ignore[arg-type]

    def test_returns_empty_when_all_filtered_out(self):
        premium = make_llm("premium-a", premium_only=True, sizes=[LLMSize.LARGE])
        result = _sort_llms_by_size_preference(
            [premium], LLMSize.LARGE, use_premium_llms=False
        )
        assert result == []

    def test_large_preferred_large_group_sorted_large_only_then_small_only(self):
        """When LARGE preferred, the tail (small-only LLMs) is also sorted by priority."""
        small_prio_10 = self._make_small("small-10", priority=10)
        small_prio_50 = self._make_small("small-50", priority=50)
        large_prio_80 = self._make_large("large-80", priority=80)
        result = _sort_llms_by_size_preference(
            [small_prio_10, large_prio_80, small_prio_50], LLMSize.LARGE, True
        )
        assert result[0].name == "large-80"
        assert result[1].name == "small-50"
        assert result[2].name == "small-10"


# ---------------------------------------------------------------------------
# Tests: get_answer_from_llms
# ---------------------------------------------------------------------------


class TestGetAnswerFromLlms:
    async def test_returns_response_from_highest_priority_llm(self):
        llm_a = make_llm("llm-a", priority=100, responses=["answer from a"])
        result = await get_answer_from_llms([llm_a], MESSAGES)
        assert result.content == "answer from a"

    async def test_falls_back_to_next_llm_on_failure(self):
        llm_fail = make_llm("llm-fail", priority=200, fail=True)
        llm_ok = make_llm("llm-ok", priority=100, responses=["fallback answer"])
        result = await get_answer_from_llms([llm_fail, llm_ok], MESSAGES)
        assert result.content == "fallback answer"

    async def test_sets_is_at_rate_limit_true_on_failed_llm(self):
        llm_fail = make_llm("llm-fail", priority=200, fail=True)
        llm_ok = make_llm("llm-ok", priority=100, responses=["ok"])
        await get_answer_from_llms([llm_fail, llm_ok], MESSAGES)
        assert llm_fail.is_at_rate_limit is True

    async def test_skips_rate_limited_llm(self):
        """Rate-limited LLMs are skipped; a non-rate-limited fallback succeeds."""
        llm_limited = make_llm("llm-limited", priority=100, responses=["ok"])
        llm_limited.is_at_rate_limit = True
        llm_ok = make_llm("llm-ok", priority=50, responses=["fallback"])
        result = await get_answer_from_llms([llm_limited, llm_ok], MESSAGES)
        assert result.content == "fallback"
        assert llm_limited.is_at_rate_limit is True  # Still marked
        assert llm_ok.is_at_rate_limit is False

    async def test_tries_backup_llms_after_all_primary_fail(self):
        primary = make_llm("primary", priority=100, fail=True)
        backup = make_llm(
            "backup", priority=50, back_up_only=True, responses=["backup answer"]
        )
        result = await get_answer_from_llms([primary, backup], MESSAGES)
        assert result.content == "backup answer"

    async def test_raises_when_all_llms_including_backups_fail(self):
        primary = make_llm("primary", priority=100, fail=True)
        backup = make_llm("backup", priority=50, back_up_only=True, fail=True)
        with pytest.raises(Exception, match="All LLMs are at rate limit"):
            await get_answer_from_llms([primary, backup], MESSAGES)

    async def test_raises_when_no_llms_provided(self):
        """Empty primary list with no backups — should raise after handle_rate_limit."""
        with pytest.raises(Exception):
            await get_answer_from_llms([], MESSAGES)

    async def test_calls_handle_llm_success_on_success(self):
        llm_ok = make_llm("llm-ok", responses=["ok"])
        with patch(
            "src.llms.handle_llm_success", new_callable=AsyncMock
        ) as mock_success:
            await get_answer_from_llms([llm_ok], MESSAGES)
        mock_success.assert_awaited_once()

    async def test_calls_handle_rate_limit_when_all_primary_fail(self):
        primary = make_llm("primary", fail=True)
        with patch(
            "src.llms.handle_rate_limit_hit_for_all_llms", new_callable=AsyncMock
        ) as mock_rl:
            with patch("src.llms.handle_llm_success", new_callable=AsyncMock):
                try:
                    await get_answer_from_llms([primary], MESSAGES)
                except Exception:
                    pass
        mock_rl.assert_awaited_once()

    async def test_sorts_llms_by_priority_descending(self):
        invocation_order: list[str] = []

        async def _record(name, messages):
            invocation_order.append(name)
            return AIMessage(content=f"response from {name}")

        llm_low = make_llm("low-priority", priority=10)
        llm_high = make_llm("high-priority", priority=90)
        object.__setattr__(
            llm_low.model, "ainvoke", lambda msgs, **kw: _record("low-priority", msgs)
        )
        object.__setattr__(
            llm_high.model, "ainvoke", lambda msgs, **kw: _record("high-priority", msgs)
        )

        await get_answer_from_llms([llm_low, llm_high], MESSAGES)
        assert invocation_order[0] == "high-priority"

    async def test_backup_llms_not_tried_when_primary_succeeds(self):
        primary = make_llm("primary", responses=["primary ok"])
        backup = make_llm("backup", back_up_only=True, fail=True)
        # Should not raise even though backup would fail — backup not tried
        result = await get_answer_from_llms([primary, backup], MESSAGES)
        assert result.content == "primary ok"

    async def test_tracks_llm_request(self):
        llm_ok = make_llm("llm-ok", responses=["ok"])
        initial_count = llms_module._total_requests
        await get_answer_from_llms([llm_ok], MESSAGES)
        assert llms_module._total_requests == initial_count + 1


# ---------------------------------------------------------------------------
# Tests: get_structured_output_from_llms
# ---------------------------------------------------------------------------


class TestGetStructuredOutputFromLlms:
    def _make_structured_llm(self, name, priority=100, response=None, fail=False):
        """Create an LLM where with_structured_output().ainvoke() returns response."""
        llm = make_llm(name, priority=priority)
        structured_model = MagicMock()
        if fail:
            structured_model.ainvoke = AsyncMock(
                side_effect=Exception(f"{name} structured failed")
            )
        else:
            structured_model.ainvoke = AsyncMock(
                return_value=response or {"key": "value"}
            )
        object.__setattr__(
            llm.model,
            "with_structured_output",
            MagicMock(return_value=structured_model),
        )
        return llm

    async def test_returns_structured_response(self):
        schema = {"type": "object"}
        expected = {"result": "parsed"}
        llm = self._make_structured_llm("llm-a", response=expected)
        result = await get_structured_output_from_llms([llm], MESSAGES, schema)
        assert result == expected

    async def test_calls_with_structured_output_with_schema(self):
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        llm = self._make_structured_llm("llm-a")
        await get_structured_output_from_llms([llm], MESSAGES, schema)
        llm.model.with_structured_output.assert_called_once_with(schema)

    async def test_falls_back_to_next_llm_on_failure(self):
        schema = {"type": "object"}
        llm_fail = self._make_structured_llm("llm-fail", priority=200, fail=True)
        llm_ok = self._make_structured_llm(
            "llm-ok", priority=100, response={"ok": True}
        )
        result = await get_structured_output_from_llms(
            [llm_fail, llm_ok], MESSAGES, schema
        )
        assert result == {"ok": True}

    async def test_sets_rate_limit_on_failed_llm(self):
        schema = {"type": "object"}
        llm_fail = self._make_structured_llm("llm-fail", priority=200, fail=True)
        llm_ok = self._make_structured_llm(
            "llm-ok", priority=100, response={"ok": True}
        )
        await get_structured_output_from_llms([llm_fail, llm_ok], MESSAGES, schema)
        assert llm_fail.is_at_rate_limit is True

    async def test_tries_backup_after_all_primary_fail(self):
        schema = {"type": "object"}
        primary = self._make_structured_llm("primary", priority=100, fail=True)
        backup = make_llm("backup", back_up_only=True)
        backup_structured = MagicMock()
        backup_structured.ainvoke = AsyncMock(return_value={"backup": True})
        object.__setattr__(
            backup.model,
            "with_structured_output",
            MagicMock(return_value=backup_structured),
        )
        result = await get_structured_output_from_llms(
            [primary, backup], MESSAGES, schema
        )
        assert result == {"backup": True}

    async def test_raises_when_all_llms_fail(self):
        schema = {"type": "object"}
        primary = self._make_structured_llm("primary", priority=100, fail=True)
        backup = make_llm("backup", back_up_only=True)
        backup_structured = MagicMock()
        backup_structured.ainvoke = AsyncMock(
            side_effect=Exception("backup also failed")
        )
        object.__setattr__(
            backup.model,
            "with_structured_output",
            MagicMock(return_value=backup_structured),
        )
        with pytest.raises(Exception, match="All LLMs are at rate limit"):
            await get_structured_output_from_llms([primary, backup], MESSAGES, schema)

    async def test_calls_handle_llm_success_on_success(self):
        schema = {"type": "object"}
        llm = self._make_structured_llm("llm-a", response={"ok": True})
        with patch(
            "src.llms.handle_llm_success", new_callable=AsyncMock
        ) as mock_success:
            await get_structured_output_from_llms([llm], MESSAGES, schema)
        mock_success.assert_awaited_once()

    async def test_calls_handle_rate_limit_when_all_primary_fail(self):
        schema = {"type": "object"}
        primary = self._make_structured_llm("primary", fail=True)
        with patch(
            "src.llms.handle_rate_limit_hit_for_all_llms", new_callable=AsyncMock
        ) as mock_rl:
            with patch("src.llms.handle_llm_success", new_callable=AsyncMock):
                try:
                    await get_structured_output_from_llms([primary], MESSAGES, schema)
                except Exception:
                    pass
        mock_rl.assert_awaited_once()

    async def test_accepts_pydantic_schema(self):
        from pydantic import BaseModel as PydanticBaseModel

        class MySchema(PydanticBaseModel):
            answer: str

        instance = MySchema(answer="hello")
        llm = self._make_structured_llm("llm-a", response=instance)
        result = await get_structured_output_from_llms([llm], MESSAGES, MySchema)
        assert result == instance


# ---------------------------------------------------------------------------
# Tests: StreamResetMarker
# ---------------------------------------------------------------------------


class TestStreamResetMarker:
    def test_has_reason_attribute(self):
        marker = StreamResetMarker(reason="rate limit", new_llm_name="llm-b")
        assert marker.reason == "rate limit"

    def test_has_new_llm_name_attribute(self):
        marker = StreamResetMarker(reason="rate limit", new_llm_name="llm-b")
        assert marker.new_llm_name == "llm-b"

    def test_stores_custom_reason(self):
        marker = StreamResetMarker(reason="connection reset", new_llm_name="llm-c")
        assert marker.reason == "connection reset"

    def test_stores_custom_new_llm_name(self):
        marker = StreamResetMarker(reason="error", new_llm_name="backup-llm")
        assert marker.new_llm_name == "backup-llm"


# ---------------------------------------------------------------------------
# Tests: stream_answer_from_llms
# ---------------------------------------------------------------------------


class TestStreamAnswerFromLlms:
    async def _collect(
        self, llms_list, preferred_size=LLMSize.LARGE, use_premium=False
    ):
        """Collect all items from stream_answer_from_llms into a list."""
        stream = await stream_answer_from_llms(
            llms_list,
            MESSAGES,
            preferred_llm_size=preferred_size,
            use_premium_llms=use_premium,
        )
        items = []
        async for item in stream:
            items.append(item)
        return items

    async def test_streams_chunks_from_first_available_llm(self):
        llm = make_streaming_llm("llm-a", chunks=["hello", " world"])
        items = await self._collect([llm])
        contents = [
            item.content for item in items if not isinstance(item, StreamResetMarker)
        ]
        assert contents == ["hello", " world"]

    async def test_falls_back_on_error_before_any_chunks(self):
        llm_fail = make_streaming_llm("llm-fail", chunks=["never"])

        # Override astream to raise immediately
        async def _raise(messages, **kwargs):
            raise Exception("llm-fail unavailable")
            yield  # make it a generator  # type: ignore[misc]

        object.__setattr__(llm_fail.model, "astream", _raise)

        llm_ok = make_streaming_llm("llm-ok", chunks=["ok chunk"])
        items = await self._collect([llm_fail, llm_ok])
        # No reset marker when 0 chunks were yielded before failure
        markers = [i for i in items if isinstance(i, StreamResetMarker)]
        chunks = [i for i in items if not isinstance(i, StreamResetMarker)]
        assert len(markers) == 0
        assert any(c.content == "ok chunk" for c in chunks)

    async def test_yields_stream_reset_marker_on_mid_stream_failure(self):
        # First LLM yields 1 chunk then fails
        llm_partial = make_streaming_llm(
            "llm-partial", chunks=["partial"], fail_after=1
        )
        llm_fallback = make_streaming_llm("llm-fallback", chunks=["new response"])
        items = await self._collect([llm_partial, llm_fallback])
        markers = [i for i in items if isinstance(i, StreamResetMarker)]
        assert len(markers) == 1
        assert markers[0].new_llm_name == "llm-fallback"

    async def test_reset_marker_contains_reason_and_new_llm_name(self):
        llm_partial = make_streaming_llm("llm-partial", chunks=["chunk"], fail_after=1)
        llm_next = make_streaming_llm("llm-next", chunks=["new"])
        items = await self._collect([llm_partial, llm_next])
        markers = [i for i in items if isinstance(i, StreamResetMarker)]
        assert len(markers) == 1
        assert "llm-partial" in markers[0].reason
        assert markers[0].new_llm_name == "llm-next"

    async def test_no_reset_marker_when_failure_before_any_chunks(self):
        async def _fail_immediately(messages, **kwargs):
            raise Exception("immediate failure")
            yield  # type: ignore[misc]

        llm_fail = make_streaming_llm("llm-fail", chunks=["x"])
        object.__setattr__(llm_fail.model, "astream", _fail_immediately)
        llm_ok = make_streaming_llm("llm-ok", chunks=["good"])
        items = await self._collect([llm_fail, llm_ok])
        markers = [i for i in items if isinstance(i, StreamResetMarker)]
        assert len(markers) == 0

    async def test_raises_when_all_llms_exhausted(self):
        async def _fail(messages, **kwargs):
            raise Exception("always fails")
            yield  # type: ignore[misc]

        llm_a = make_streaming_llm("llm-a")
        llm_b = make_streaming_llm("llm-b")
        object.__setattr__(llm_a.model, "astream", _fail)
        object.__setattr__(llm_b.model, "astream", _fail)

        with pytest.raises(Exception, match="All LLMs failed"):
            await self._collect([llm_a, llm_b])

    async def test_sets_is_at_rate_limit_true_on_failed_streaming_llm(self):
        async def _fail(messages, **kwargs):
            raise Exception("fail")
            yield  # type: ignore[misc]

        llm_fail = make_streaming_llm("llm-fail", priority=200)
        object.__setattr__(llm_fail.model, "astream", _fail)
        llm_ok = make_streaming_llm("llm-ok", priority=100, chunks=["ok"])
        await self._collect([llm_fail, llm_ok])
        assert llm_fail.is_at_rate_limit is True

    async def test_clears_is_at_rate_limit_on_successful_stream(self):
        llm = make_streaming_llm("llm-ok", chunks=["ok"])
        llm.is_at_rate_limit = True  # Simulate previously rate-limited
        await self._collect([llm])
        assert llm.is_at_rate_limit is False

    async def test_uses_sort_by_size_preference(self):
        """LLMs are reordered by size preference before streaming."""
        small_llm = make_streaming_llm("small-llm", priority=100, chunks=["small"])
        # Reattach sizes to the LLM wrapper
        small_llm_wrapped = LLM(
            name="small-llm",
            model=small_llm.model,
            sizes=[LLMSize.SMALL],
            priority=100,
            user_capacity_per_minute=100,
            is_at_rate_limit=False,
        )
        large_llm_wrapped = LLM(
            name="large-llm",
            model=make_streaming_llm("large-llm", chunks=["large"]).model,
            sizes=[LLMSize.LARGE],
            priority=50,
            user_capacity_per_minute=100,
            is_at_rate_limit=False,
        )
        # With LARGE preferred, large_llm should stream first despite lower priority rank
        # (priority is used within same group, but LARGE group goes first)
        items = await self._collect(
            [small_llm_wrapped, large_llm_wrapped],
            preferred_size=LLMSize.LARGE,
        )
        chunks = [i for i in items if not isinstance(i, StreamResetMarker)]
        assert chunks[0].content == "large"

    async def test_tracks_llm_request_once(self):
        llm = make_streaming_llm("llm-a", chunks=["a", "b"])
        initial = llms_module._total_requests
        await self._collect([llm])
        assert llms_module._total_requests == initial + 1

    async def test_calls_handle_llm_success_after_complete_stream(self):
        llm = make_streaming_llm("llm-a", chunks=["done"])
        with patch(
            "src.llms.handle_llm_success", new_callable=AsyncMock
        ) as mock_success:
            await self._collect([llm])
        mock_success.assert_awaited_once()

    async def test_calls_handle_rate_limit_when_all_llms_fail(self):
        async def _fail(messages, **kwargs):
            raise Exception("fail")
            yield  # type: ignore[misc]

        llm = make_streaming_llm("llm-a")
        object.__setattr__(llm.model, "astream", _fail)

        with patch(
            "src.llms.handle_rate_limit_hit_for_all_llms", new_callable=AsyncMock
        ) as mock_rl:
            with pytest.raises(Exception):
                await self._collect([llm])
        mock_rl.assert_awaited_once()

    async def test_fallback_llm_streams_full_response_after_reset(self):
        """After fallback, the fallback LLM's full response is yielded."""
        llm_partial = make_streaming_llm(
            "llm-partial", chunks=["partial"], fail_after=1
        )
        llm_fallback = make_streaming_llm("llm-fallback", chunks=["full", " response"])
        items = await self._collect([llm_partial, llm_fallback])
        # Expect: partial chunk, reset marker, then fallback chunks
        non_marker = [i for i in items if not isinstance(i, StreamResetMarker)]
        fallback_contents = [i.content for i in non_marker]
        assert "full" in fallback_contents
        assert " response" in fallback_contents


# ---------------------------------------------------------------------------
# Tests: handle_rate_limit_hit_for_all_llms / handle_llm_success / reset_all_rate_limits
# ---------------------------------------------------------------------------


class TestRateLimitManagement:
    async def test_handle_rate_limit_writes_firestore_true(self):
        _mock_firebase_service.awrite_llm_status = AsyncMock()
        with patch("src.llms.awrite_llm_status", new_callable=AsyncMock) as mock_write:
            await handle_rate_limit_hit_for_all_llms()
        mock_write.assert_awaited_once_with(is_at_rate_limit=True)

    async def test_handle_llm_success_writes_firestore_false(self):
        with patch("src.llms.awrite_llm_status", new_callable=AsyncMock) as mock_write:
            await handle_llm_success()
        mock_write.assert_awaited_once_with(is_at_rate_limit=False)

    async def test_handle_llm_success_cancels_existing_reset_task(self):
        import asyncio

        # Create a real (but never-resolving) task to simulate an active reset timer
        async def _never_ending():
            await asyncio.sleep(9999)

        task = asyncio.create_task(_never_ending())
        llms_module._rate_limit_reset_task = task

        with patch("src.llms.awrite_llm_status", new_callable=AsyncMock):
            await handle_llm_success()

        # Wait for the cancelled task to fully process the CancelledError
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        assert llms_module._rate_limit_reset_task is None

    async def test_reset_all_rate_limits_clears_non_deterministic_llms(self):
        # Patch module-level lists to contain controlled test LLMs
        llm_a = make_llm("llm-a")
        llm_a.is_at_rate_limit = True
        original = llms_module.NON_DETERMINISTIC_LLMS
        try:
            llms_module.NON_DETERMINISTIC_LLMS = [llm_a]
            with patch("src.llms.awrite_llm_status", new_callable=AsyncMock):
                await reset_all_rate_limits()
            assert llm_a.is_at_rate_limit is False
        finally:
            llms_module.NON_DETERMINISTIC_LLMS = original

    async def test_reset_all_rate_limits_clears_deterministic_llms(self):
        llm_b = make_llm("llm-b")
        llm_b.is_at_rate_limit = True
        original = llms_module.DETERMINISTIC_LLMS
        try:
            llms_module.DETERMINISTIC_LLMS = [llm_b]
            with patch("src.llms.awrite_llm_status", new_callable=AsyncMock):
                await reset_all_rate_limits()
            assert llm_b.is_at_rate_limit is False
        finally:
            llms_module.DETERMINISTIC_LLMS = original

    async def test_reset_all_rate_limits_writes_firestore_false(self):
        with patch("src.llms.awrite_llm_status", new_callable=AsyncMock) as mock_write:
            await reset_all_rate_limits()
        mock_write.assert_awaited_once_with(is_at_rate_limit=False)

    async def test_reset_all_rate_limits_cancels_pending_task(self):
        import asyncio

        async def _never_ending():
            await asyncio.sleep(9999)

        task = asyncio.create_task(_never_ending())
        llms_module._rate_limit_reset_task = task

        with patch("src.llms.awrite_llm_status", new_callable=AsyncMock):
            await reset_all_rate_limits()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        assert llms_module._rate_limit_reset_task is None

    async def test_handle_rate_limit_creates_auto_reset_task(self):
        with patch("src.llms.awrite_llm_status", new_callable=AsyncMock):
            await handle_rate_limit_hit_for_all_llms()
        assert llms_module._rate_limit_reset_task is not None
        assert not llms_module._rate_limit_reset_task.done()

    async def test_handle_rate_limit_cancels_previous_reset_task(self):
        import asyncio

        async def _never_ending():
            await asyncio.sleep(9999)

        old_task = asyncio.create_task(_never_ending())
        llms_module._rate_limit_reset_task = old_task

        with patch("src.llms.awrite_llm_status", new_callable=AsyncMock):
            await handle_rate_limit_hit_for_all_llms()

        with pytest.raises(asyncio.CancelledError):
            await old_task
        assert old_task.cancelled()
        # A new task should have been created
        assert llms_module._rate_limit_reset_task is not None
        assert llms_module._rate_limit_reset_task is not old_task
