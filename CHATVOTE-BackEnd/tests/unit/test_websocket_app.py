# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Unit tests for src/websocket_app.py.

Focuses on testable pure/semi-pure functions and the payload-validation paths of
Socket.IO event handlers.  The actual Socket.IO server is replaced with an
AsyncMock so no network I/O occurs.

Tested areas:
  1. _sanitize_source_url        — pure helper
  2. _log_timing                 — pure helper (side-effect: logging)
  3. _emit_debug_llm_call        — only fires in local/dev, gated by ENV
  4. InitChatSessionDto / ChatUserMessageDto / ProConPerspectiveRequestDto /
     VotingBehaviorRequestDto / RequestSummaryDto — DTO validation
  5. chat_session_init handler   — valid payload, missing fields, ValidationError path
  6. chat_summary_request handler — valid payload, missing fields, generation error
  7. pro_con_perspective_request  — valid payload, missing fields, party-not-found
  8. chat_answer_request          — valid payload, message-too-long guardrail,
                                   missing session_id, missing fields
  9. voting_behavior_request      — valid payload, missing required fields
 10. home event                  — locale normalisation
"""

import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# Force this entire file into a single xdist worker so module-level stubs
# don't collide with real imports loaded by other test files.
pytestmark = pytest.mark.xdist_group("websocket")

# ---------------------------------------------------------------------------
# Environment — must be set before any src imports
# ---------------------------------------------------------------------------
os.environ.setdefault("API_NAME", "chatvote-api")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")
os.environ.setdefault("GOOGLE_API_KEY", "fake-key-for-testing")

# ---------------------------------------------------------------------------
# Stub heavy external dependencies before importing src.websocket_app.
#
# Strategy: temporarily force-install mocks into sys.modules, import the
# module under test, then restore the originals so other test files in the
# same xdist worker (or collection phase) are unaffected.
# ---------------------------------------------------------------------------

_STUBBED_MODULES: dict[str, object] = {}  # name → mock

def _install(name: str, mock: object) -> None:
    """Force-install *mock* into sys.modules, remembering the original."""
    _STUBBED_MODULES[name] = mock

# --- firebase_admin ---
_stub_admin = MagicMock()
_stub_admin._apps = {}
_stub_firestore_mod = MagicMock()
_stub_firestore_mod.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"
_stub_credentials = MagicMock()
_stub_firestore_async = MagicMock()
_install("firebase_admin", _stub_admin)
_install("firebase_admin.firestore", _stub_firestore_mod)
_install("firebase_admin.credentials", _stub_credentials)
_install("firebase_admin.firestore_async", _stub_firestore_async)

# --- google.cloud ---
_stub_gcf = MagicMock()
_stub_gcf.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"
_install("google", MagicMock())
_install("google.cloud", MagicMock())
_install("google.cloud.firestore_v1", _stub_gcf)
_install("google.auth", MagicMock())
_install("google.oauth2", MagicMock())
_install("google.oauth2.credentials", MagicMock())

# --- firebase_service ---
_mock_async_db = MagicMock()
_default_doc = MagicMock()
_default_doc.exists = True
_default_doc.to_dict.return_value = {"session_id": "test", "messages": []}
_mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
    return_value=_default_doc
)
_mock_async_db.collection.return_value.document.return_value.set = AsyncMock()
_mock_async_db.collection.return_value.document.return_value.update = AsyncMock()

_mock_firebase_service = MagicMock()
_mock_firebase_service.async_db = _mock_async_db
_mock_firebase_service.aget_party_by_id = AsyncMock(return_value=None)
_mock_firebase_service.aget_parties = AsyncMock(return_value=[])
_mock_firebase_service.aget_candidates_by_municipality = AsyncMock(return_value=[])
_mock_firebase_service.aget_candidate_by_id = AsyncMock(return_value=None)
_mock_firebase_service.aget_cached_answers_for_party = AsyncMock(return_value=None)
_mock_firebase_service.aget_proposed_questions_for_party = AsyncMock(return_value=[])
_mock_firebase_service.awrite_cached_answer_for_party = AsyncMock()
_install("src.firebase_service", _mock_firebase_service)

# --- chatbot_async ---
_mock_chatbot = MagicMock()
_mock_chatbot.generate_chat_title_and_chick_replies = AsyncMock(
    return_value=("Test Title", ["Q1", "Q2"])
)
_mock_chatbot.get_improved_rag_query_voting_behavior = AsyncMock(
    return_value="improved query"
)
_mock_chatbot.get_question_targets_and_type = AsyncMock(
    return_value=(["lfi"], False, False)
)
_mock_chatbot.generate_pro_con_perspective = AsyncMock(
    return_value=MagicMock(role="assistant", content="Pro/Con analysis")
)
_mock_chatbot.generate_pro_con_perspective_candidate = AsyncMock(
    return_value=MagicMock(role="assistant", content="Candidate Pro/Con")
)
_mock_chatbot.generate_streaming_chatbot_response = AsyncMock(return_value=iter([]))
_mock_chatbot.generate_chat_summary = AsyncMock(return_value="Résumé du chat.")
_mock_chatbot.generate_streaming_chatbot_comparing_response = AsyncMock(
    return_value=iter([])
)
_mock_chatbot.generate_party_vote_behavior_summary = AsyncMock(return_value=iter([]))
_mock_chatbot.generate_streaming_global_combined_response = AsyncMock(
    return_value=iter([])
)
_mock_chatbot.generate_improvement_rag_query = AsyncMock(return_value="better query")
_mock_chatbot.Responder = MagicMock()
_install("src.chatbot_async", _mock_chatbot)

# --- llms ---
_mock_llms = MagicMock()
_mock_llms.StreamResetMarker = object  # sentinel type
_install("src.llms", _mock_llms)

# --- vector_store_helper ---
_mock_vsh = MagicMock()
_mock_vsh.identify_relevant_votes = AsyncMock(return_value=[])
_mock_vsh.identify_relevant_docs_with_llm_based_reranking = AsyncMock(
    return_value=([], "query")
)
_mock_vsh.identify_relevant_docs_combined = AsyncMock(return_value=([], []))
_install("src.vector_store_helper", _mock_vsh)

# --- src.utils ---
_mock_utils = MagicMock()
_mock_utils.get_cors_allowed_origins = MagicMock(return_value=["*"])
_mock_utils.build_chat_history_string = MagicMock(return_value="")
_mock_utils.get_chat_history_hash_key = MagicMock(return_value="hash123")
_mock_utils.sanitize_references = MagicMock(side_effect=lambda x: x)
_install("src.utils", _mock_utils)

# --- src.i18n ---
_mock_i18n = MagicMock()
_mock_i18n.normalize_locale = MagicMock(return_value="fr")
_mock_i18n.get_text = MagicMock(return_value="Texte localise")
_mock_i18n.Locale = str
_install("src.i18n", _mock_i18n)

# --- src.models.assistant ---
_mock_assistant = MagicMock()
_mock_assistant.ASSISTANT_ID = "chat-vote"
_mock_assistant.CHATVOTE_ASSISTANT = MagicMock()
_install("src.models.assistant", _mock_assistant)

# --- socketio (replace with a lightweight async mock) ---
_mock_sio_instance = MagicMock()
_mock_sio_instance.emit = AsyncMock()
_mock_sio_instance.session = MagicMock()
_mock_sio_instance.reason = MagicMock()
_mock_sio_instance.reason.CLIENT_DISCONNECT = "transport close"
_mock_sio_instance.reason.SERVER_DISCONNECT = "server namespace disconnect"

_mock_socketio = MagicMock()
_mock_socketio.AsyncServer = MagicMock(return_value=_mock_sio_instance)

# Decorators must be no-ops
def _event_decorator(fn):
    return fn

def _on_decorator(event_name):
    return lambda fn: fn

_mock_sio_instance.event = _event_decorator
_mock_sio_instance.on = _on_decorator

_install("socketio", _mock_socketio)

# --- openai ---
_mock_openai = MagicMock()
_mock_openai.BadRequestError = type("BadRequestError", (Exception,), {})
_install("openai", _mock_openai)

# aiohttp
_install("aiohttp", MagicMock())

# ---------------------------------------------------------------------------
# NOW: swap in mocks, import the module under test, then restore originals
# so other test files collected in the same process are unaffected.
# ---------------------------------------------------------------------------
_saved: dict[str, object] = {}
_SENTINEL = object()

for _name, _mock in _STUBBED_MODULES.items():
    _saved[_name] = sys.modules.get(_name, _SENTINEL)
    sys.modules[_name] = _mock

# Remove any cached import of the module under test
sys.modules.pop("src.websocket_app", None)

import src.websocket_app as ws_app  # noqa: E402

# Restore original sys.modules so other test files are not affected
for _name, _orig in _saved.items():
    if _orig is _SENTINEL:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _orig

# Inject our controlled sio mock into the loaded module
ws_app.sio = _mock_sio_instance
ws_app.async_db = _mock_async_db
ws_app.aget_party_by_id = _mock_firebase_service.aget_party_by_id
ws_app.aget_parties = _mock_firebase_service.aget_parties
ws_app.aget_candidate_by_id = _mock_firebase_service.aget_candidate_by_id
ws_app.generate_chat_summary = _mock_chatbot.generate_chat_summary
ws_app.generate_pro_con_perspective = _mock_chatbot.generate_pro_con_perspective
ws_app.generate_pro_con_perspective_candidate = (
    _mock_chatbot.generate_pro_con_perspective_candidate
)
ws_app.get_improved_rag_query_voting_behavior = (
    _mock_chatbot.get_improved_rag_query_voting_behavior
)
ws_app.identify_relevant_votes = _mock_vsh.identify_relevant_votes
ws_app.build_chat_history_string = _mock_utils.build_chat_history_string
ws_app.get_text = _mock_i18n.get_text
ws_app.normalize_locale = _mock_i18n.normalize_locale
ws_app.ASSISTANT_ID = "chat-vote"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_sio_emit():
    """Clear recorded emit calls between tests."""
    _mock_sio_instance.emit.reset_mock()


def _make_session_ctx(chat_sessions: dict):
    """Return an async context manager that yields a dict mimicking sio.session()."""
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx(sid):
        yield chat_sessions

    return _ctx


def _make_group_chat_session(session_id: str = "sess-001"):
    from src.models.chat import GroupChatSession
    from src.models.general import LLMSize

    return GroupChatSession(
        session_id=session_id,
        chat_history=[],
        title="Test",
        scope="national",
        chat_response_llm_size=LLMSize.LARGE,
    )


# ---------------------------------------------------------------------------
# 1. _sanitize_source_url
# ---------------------------------------------------------------------------


class TestSanitizeSourceUrl:
    def test_valid_https_url_returned_unchanged(self):
        url = "https://example.com/page"
        assert ws_app._sanitize_source_url(url) == url

    def test_valid_http_url_returned_unchanged(self):
        url = "http://example.com/page"
        assert ws_app._sanitize_source_url(url) == url

    def test_none_returns_none(self):
        assert ws_app._sanitize_source_url(None) is None

    def test_relative_path_returns_none(self):
        assert ws_app._sanitize_source_url("/relative/path") is None

    def test_ftp_scheme_returns_none(self):
        assert ws_app._sanitize_source_url("ftp://example.com/file") is None

    def test_empty_string_returns_none(self):
        assert ws_app._sanitize_source_url("") is None


# ---------------------------------------------------------------------------
# 2. _log_timing
# ---------------------------------------------------------------------------


class TestLogTiming:
    def test_returns_elapsed_time(self):
        start = time.perf_counter() - 0.5  # simulate 500ms ago
        elapsed = ws_app._log_timing("test_stage", start, "sid-123")
        assert elapsed >= 0.4  # at least 400ms

    def test_logs_json_with_stage_and_sid(self, caplog):
        import logging

        start = time.perf_counter()
        with caplog.at_level(logging.INFO, logger="src.websocket_app"):
            ws_app._log_timing("my_stage", start, "abc")
        assert any("my_stage" in r.message for r in caplog.records)

    def test_extra_dict_merged_into_log(self, caplog):
        import logging

        start = time.perf_counter()
        with caplog.at_level(logging.INFO, logger="src.websocket_app"):
            ws_app._log_timing("stage", start, "sid", extra={"party": "lfi"})
        assert any("lfi" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 3. _emit_debug_llm_call — ENV-gated
# ---------------------------------------------------------------------------


class TestEmitDebugLlmCall:
    @pytest.mark.asyncio
    async def test_does_not_emit_in_prod(self, monkeypatch):
        monkeypatch.setenv("ENV", "prod")
        _reset_sio_emit()
        await ws_app._emit_debug_llm_call("sid", "sess", "stage", {"k": "v"})
        _mock_sio_instance.emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_emits_in_local(self, monkeypatch):
        monkeypatch.setenv("ENV", "local")
        _reset_sio_emit()
        await ws_app._emit_debug_llm_call("sid-x", "sess-y", "stage-z", {"foo": "bar"})
        _mock_sio_instance.emit.assert_called_once()
        args = _mock_sio_instance.emit.call_args
        assert args[0][0] == "debug_llm_call"
        payload = args[0][1]
        assert payload["stage"] == "stage-z"
        assert payload["foo"] == "bar"

    @pytest.mark.asyncio
    async def test_swallows_emit_exceptions(self, monkeypatch):
        monkeypatch.setenv("ENV", "local")
        _mock_sio_instance.emit.side_effect = Exception("network error")
        # Should NOT raise
        await ws_app._emit_debug_llm_call("sid", "sess", "stage", {})
        _mock_sio_instance.emit.side_effect = None


# ---------------------------------------------------------------------------
# 4. DTO validation (pure Pydantic — no I/O)
# ---------------------------------------------------------------------------


class TestInitChatSessionDtoValidation:
    def test_valid_minimal_payload(self):
        from src.models.dtos import InitChatSessionDto

        dto = InitChatSessionDto(
            session_id="s1",
            chat_history=[],
            current_title="My Chat",
        )
        assert dto.session_id == "s1"
        assert dto.scope.value == "national"

    def test_missing_session_id_raises(self):
        from pydantic import ValidationError
        from src.models.dtos import InitChatSessionDto

        with pytest.raises(ValidationError):
            InitChatSessionDto(chat_history=[], current_title="T")

    def test_invalid_locale_raises(self):
        from pydantic import ValidationError
        from src.models.dtos import InitChatSessionDto

        with pytest.raises(ValidationError):
            InitChatSessionDto(
                session_id="s1",
                chat_history=[],
                current_title="T",
                locale="de",  # unsupported
            )


class TestChatUserMessageDtoValidation:
    def test_valid_payload(self):
        from src.models.dtos import ChatUserMessageDto

        dto = ChatUserMessageDto(
            session_id="s1",
            user_message="Bonjour",
            party_ids=["lfi", "rn"],
        )
        assert dto.user_message == "Bonjour"
        assert dto.user_is_logged_in is False

    def test_empty_session_id_raises(self):
        from pydantic import ValidationError
        from src.models.dtos import ChatUserMessageDto

        with pytest.raises(ValidationError):
            ChatUserMessageDto(
                session_id="   ",  # whitespace only
                user_message="Hello",
                party_ids=["lfi"],
            )

    def test_missing_party_ids_raises(self):
        from pydantic import ValidationError
        from src.models.dtos import ChatUserMessageDto

        with pytest.raises(ValidationError):
            ChatUserMessageDto(session_id="s1", user_message="Hi")


class TestProConPerspectiveRequestDtoValidation:
    def test_valid_payload(self):
        from src.models.dtos import ProConPerspectiveRequestDto

        dto = ProConPerspectiveRequestDto(
            request_id="req-1",
            party_id="lfi",
            last_user_message="Question?",
            last_assistant_message="Answer.",
        )
        assert dto.party_id == "lfi"

    def test_missing_party_id_raises(self):
        from pydantic import ValidationError
        from src.models.dtos import ProConPerspectiveRequestDto

        with pytest.raises(ValidationError):
            ProConPerspectiveRequestDto(
                request_id="req-1",
                last_user_message="Q",
                last_assistant_message="A",
            )


class TestVotingBehaviorRequestDtoValidation:
    def test_valid_payload(self):
        from src.models.dtos import VotingBehaviorRequestDto

        dto = VotingBehaviorRequestDto(
            request_id="req-1",
            party_id="ps",
            last_user_message="Q",
            last_assistant_message="A",
        )
        assert dto.user_is_logged_in is False

    def test_missing_request_id_raises(self):
        from pydantic import ValidationError
        from src.models.dtos import VotingBehaviorRequestDto

        with pytest.raises(ValidationError):
            VotingBehaviorRequestDto(
                party_id="ps",
                last_user_message="Q",
                last_assistant_message="A",
            )


# ---------------------------------------------------------------------------
# 5. init_chat_session handler
# ---------------------------------------------------------------------------


class TestInitChatSession:
    @pytest.mark.asyncio
    async def test_valid_payload_emits_success(self):
        _reset_sio_emit()
        sessions: dict = {}
        _mock_sio_instance.session = _make_session_ctx(sessions)

        await ws_app.init_chat_session(
            "sid-1",
            {
                "session_id": "sess-abc",
                "chat_history": [],
                "current_title": "My Title",
            },
        )

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "chat_session_initialized"
        assert payload["session_id"] == "sess-abc"
        assert payload["status"]["indicator"] == "success"

    @pytest.mark.asyncio
    async def test_invalid_payload_emits_error(self):
        _reset_sio_emit()
        # Missing session_id — should emit error
        await ws_app.init_chat_session(
            "sid-2",
            {"chat_history": [], "current_title": "T"},
        )

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "chat_session_initialized"
        assert payload["status"]["indicator"] == "error"
        assert payload["session_id"] is None

    @pytest.mark.asyncio
    async def test_session_stored_in_sio_session(self):
        _reset_sio_emit()
        sessions: dict = {}
        _mock_sio_instance.session = _make_session_ctx(sessions)

        await ws_app.init_chat_session(
            "sid-3",
            {
                "session_id": "sess-xyz",
                "chat_history": [],
                "current_title": "Chat",
            },
        )

        assert "sess-xyz" in sessions.get("chat_sessions", {})


# ---------------------------------------------------------------------------
# 6. chat_summary_request handler
# ---------------------------------------------------------------------------


class TestChatSummaryRequest:
    @pytest.mark.asyncio
    async def test_valid_payload_emits_summary(self):
        _reset_sio_emit()
        ws_app.generate_chat_summary = AsyncMock(return_value="Mon résumé")

        await ws_app.chat_summary_request(
            "sid-10",
            {"chat_history": [], "session_id": "sess-1"},
        )

        _mock_sio_instance.emit.assert_called()
        last_call = _mock_sio_instance.emit.call_args_list[-1]
        event, payload = last_call[0][:2]
        assert event == "chat_summary_complete"
        assert payload["status"]["indicator"] == "success"

    @pytest.mark.asyncio
    async def test_generation_error_emits_error_status(self):
        _reset_sio_emit()
        ws_app.generate_chat_summary = AsyncMock(side_effect=Exception("LLM down"))

        await ws_app.chat_summary_request(
            "sid-11",
            {"chat_history": [], "session_id": "sess-2"},
        )

        last_call = _mock_sio_instance.emit.call_args_list[-1]
        event, payload = last_call[0][:2]
        assert event == "chat_summary_complete"
        assert payload["status"]["indicator"] == "error"

    @pytest.mark.asyncio
    async def test_missing_chat_history_emits_error(self):
        _reset_sio_emit()
        # chat_history is required by RequestSummaryDto
        await ws_app.chat_summary_request("sid-12", {})

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "chat_summary_complete"
        assert payload["status"]["indicator"] == "error"


# ---------------------------------------------------------------------------
# 7. pro_con_perspective_request handler
# ---------------------------------------------------------------------------


class TestGetProConPerspective:
    @pytest.mark.asyncio
    async def test_missing_fields_emits_error(self):
        _reset_sio_emit()
        # party_id missing
        await ws_app.get_pro_con_perspective(
            "sid-20",
            {
                "request_id": "req-1",
                "last_user_message": "Q",
                "last_assistant_message": "A",
            },
        )

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "pro_con_perspective_complete"
        assert payload["status"]["indicator"] == "error"
        assert payload["request_id"] is None

    @pytest.mark.asyncio
    async def test_party_not_found_emits_error(self):
        _reset_sio_emit()
        ws_app.aget_party_by_id = AsyncMock(return_value=None)

        await ws_app.get_pro_con_perspective(
            "sid-21",
            {
                "request_id": "req-2",
                "party_id": "unknown-party",
                "last_user_message": "Q",
                "last_assistant_message": "A",
            },
        )

        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "pro_con_perspective_complete"
        assert payload["status"]["indicator"] == "error"

    @pytest.mark.asyncio
    async def test_valid_request_emits_success(self):
        _reset_sio_emit()
        from src.models.chat import Message, Role

        fake_party = MagicMock()
        fake_party.party_id = "lfi"
        ws_app.aget_party_by_id = AsyncMock(return_value=fake_party)
        ws_app.generate_pro_con_perspective = AsyncMock(
            return_value=Message(role=Role.ASSISTANT, content="Pro/Con analysis")
        )

        await ws_app.get_pro_con_perspective(
            "sid-22",
            {
                "request_id": "req-3",
                "party_id": "lfi",
                "last_user_message": "Question?",
                "last_assistant_message": "Answer.",
            },
        )

        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "pro_con_perspective_complete"
        assert payload["request_id"] == "req-3"
        assert payload["status"]["indicator"] == "success"


# ---------------------------------------------------------------------------
# 8. chat_answer_request handler — validation and guardrail paths
# ---------------------------------------------------------------------------


class TestChatAnswerRequest:
    @pytest.mark.asyncio
    async def test_missing_session_id_emits_error(self):
        _reset_sio_emit()
        # session_id is required; omit it
        await ws_app.chat_answer_request(
            "sid-30",
            {"user_message": "Hello", "party_ids": ["lfi"]},
        )

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "chat_response_complete"
        assert payload["status"]["indicator"] == "error"

    @pytest.mark.asyncio
    async def test_message_too_long_emits_error(self):
        """ChatUserMessageDto enforces max_length=500; exceeding it is a validation error
        that emits chat_response_complete with indicator=error."""
        _reset_sio_emit()
        # 501 chars exceeds the DTO's max_length=500 and triggers a validation error
        long_msg = "x" * 501
        sessions: dict = {"chat_sessions": {"sess-99": _make_group_chat_session("sess-99")}}
        _mock_sio_instance.session = _make_session_ctx(sessions)

        await ws_app.chat_answer_request(
            "sid-31",
            {
                "session_id": "sess-99",
                "user_message": long_msg,
                "party_ids": ["lfi"],
            },
        )

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "chat_response_complete"
        assert payload["status"]["indicator"] == "error"

    @pytest.mark.asyncio
    async def test_session_not_found_emits_error(self):
        _reset_sio_emit()
        # session store is empty — session_id won't be found
        empty_sessions: dict = {"chat_sessions": {}}
        _mock_sio_instance.session = _make_session_ctx(empty_sessions)
        ws_app.aget_parties = AsyncMock(return_value=[])

        await ws_app.chat_answer_request(
            "sid-32",
            {
                "session_id": "nonexistent-sess",
                "user_message": "Hello",
                "party_ids": ["lfi"],
            },
        )

        # Should emit chat_response_complete with error
        emitted_events = [c[0][0] for c in _mock_sio_instance.emit.call_args_list]
        assert "chat_response_complete" in emitted_events
        for c in _mock_sio_instance.emit.call_args_list:
            if c[0][0] == "chat_response_complete":
                assert c[0][1]["status"]["indicator"] == "error"
                break

    @pytest.mark.asyncio
    async def test_valid_payload_passes_validation(self):
        """Ensure that a structurally correct payload does NOT emit an early validation error."""
        _reset_sio_emit()
        # Provide a real chat session in the store
        group_session = _make_group_chat_session("sess-valid")
        sessions: dict = {"chat_sessions": {"sess-valid": group_session}}
        _mock_sio_instance.session = _make_session_ctx(sessions)
        ws_app.aget_parties = AsyncMock(return_value=[])

        # handle_combined_answer_request is the deep handler; mock it to avoid
        # full pipeline execution
        with patch.object(ws_app, "handle_combined_answer_request", new=AsyncMock()):
            await ws_app.chat_answer_request(
                "sid-33",
                {
                    "session_id": "sess-valid",
                    "user_message": "Question courte",
                    "party_ids": ["lfi"],
                },
            )

        # No early error emit for chat_response_complete with indicator=error
        for c in _mock_sio_instance.emit.call_args_list:
            if c[0][0] == "chat_response_complete":
                assert c[0][1]["status"]["indicator"] != "error", (
                    "Unexpected validation error on valid payload"
                )


# ---------------------------------------------------------------------------
# 9. voting_behavior_request handler — validation path
# ---------------------------------------------------------------------------


class TestGetVotingBehavior:
    @pytest.mark.asyncio
    async def test_missing_required_fields_emits_error(self):
        _reset_sio_emit()
        # request_id is required; omit it
        await ws_app.get_voting_behavior(
            "sid-40",
            {
                "party_id": "lfi",
                "last_user_message": "Q",
                "last_assistant_message": "A",
            },
        )

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "voting_behavior_complete"
        assert payload["status"]["indicator"] == "error"

    @pytest.mark.asyncio
    async def test_party_not_found_emits_error(self):
        _reset_sio_emit()
        ws_app.aget_party_by_id = AsyncMock(return_value=None)

        await ws_app.get_voting_behavior(
            "sid-41",
            {
                "request_id": "req-v1",
                "party_id": "unknown",
                "last_user_message": "Q",
                "last_assistant_message": "A",
            },
        )

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "voting_behavior_complete"
        assert payload["status"]["indicator"] == "error"


# ---------------------------------------------------------------------------
# 10. home event — locale normalisation
# ---------------------------------------------------------------------------


class TestHomeEvent:
    @pytest.mark.asyncio
    async def test_emits_home_response_with_message(self):
        _reset_sio_emit()
        _mock_i18n.get_text.return_value = "Bienvenue"

        await ws_app.home("sid-50", {"locale": "fr"})

        _mock_sio_instance.emit.assert_called_once()
        event, payload = _mock_sio_instance.emit.call_args[0][:2]
        assert event == "home_response"
        assert "message" in payload

    @pytest.mark.asyncio
    async def test_locale_normalised_before_text_lookup(self):
        _reset_sio_emit()
        _mock_i18n.normalize_locale.reset_mock()

        await ws_app.home("sid-51", {"locale": "EN"})  # non-normalised

        _mock_i18n.normalize_locale.assert_called_once_with("EN")
