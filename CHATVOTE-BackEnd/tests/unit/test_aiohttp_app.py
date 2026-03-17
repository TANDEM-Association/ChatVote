# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Unit tests for src/aiohttp_app.py.

All external dependencies are mocked at the sys.modules level BEFORE any src
imports so that Firebase, Qdrant, LLM providers, and services are never
contacted.  Tests use aiohttp.test_utils.TestServer + TestClient for full
request/response lifecycle testing.

No pytest-aiohttp required — everything uses the stdlib aiohttp test utilities.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

# ---------------------------------------------------------------------------
# Environment variables — must be set before any src imports
# ---------------------------------------------------------------------------
os.environ["API_NAME"] = "chatvote-api"
os.environ["ENV"] = "local"
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")
os.environ["DISABLE_SOCKETIO"] = "1"

# ---------------------------------------------------------------------------
# Stub out all heavy/external dependencies before importing the app module
# ---------------------------------------------------------------------------

# --- Firebase Admin ---
_stub_admin = MagicMock()
_stub_admin._apps = {}
_stub_firestore = MagicMock()
_stub_firestore_async = MagicMock()
_stub_credentials = MagicMock()
_stub_firestore.client.return_value = MagicMock()
_stub_firestore_async.client.return_value = MagicMock()

sys.modules.setdefault("firebase_admin", _stub_admin)
sys.modules.setdefault("firebase_admin.firestore", _stub_firestore)
sys.modules.setdefault("firebase_admin.credentials", _stub_credentials)
sys.modules.setdefault("firebase_admin.firestore_async", _stub_firestore_async)

# google.cloud.firestore_v1 used inside route handlers
_stub_gcf = MagicMock()
_stub_gcf.AsyncQuery = MagicMock()
_stub_gcf.AsyncQuery.DESCENDING = "DESCENDING"
_stub_gcf.AsyncQuery.ASCENDING = "ASCENDING"
_stub_gcf.Query = MagicMock()
_stub_gcf.Query.DESCENDING = "DESCENDING"
_stub_gcf.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"
sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.cloud", MagicMock())
sys.modules.setdefault("google.cloud.firestore_v1", _stub_gcf)
sys.modules.setdefault("google.auth", MagicMock())
sys.modules.setdefault("google.oauth2", MagicMock())
sys.modules.setdefault("google.oauth2.credentials", MagicMock())

# --- firebase_service mock ---
_mock_async_db = MagicMock()
_default_doc = MagicMock()
_default_doc.exists = False
_default_doc.to_dict.return_value = None
_mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
    return_value=_default_doc
)
_mock_async_db.collection.return_value.document.return_value.set = AsyncMock()

_mock_db = MagicMock()

_mock_firebase_service = MagicMock()
_mock_firebase_service.aget_party_by_id = AsyncMock(return_value=None)
_mock_firebase_service.aget_parties = AsyncMock(return_value=[])
_mock_firebase_service.aget_candidates_by_municipality = AsyncMock(return_value=[])
_mock_firebase_service.awrite_llm_status = AsyncMock()
_mock_firebase_service.async_db = _mock_async_db
_mock_firebase_service.db = _mock_db

sys.modules.setdefault("src.firebase_service", _mock_firebase_service)

# --- LLM mock ---
_fake_llm = MagicMock()
_fake_llm.name = "gemini-mock"
_fake_llm.is_at_rate_limit = False

_mock_llms = MagicMock()
_mock_llms.NON_DETERMINISTIC_LLMS = [_fake_llm]
_mock_llms.reset_all_rate_limits = AsyncMock()
sys.modules.setdefault("src.llms", _mock_llms)

# --- vector_store_helper mock ---
_mock_qdrant_client = MagicMock()
_mock_qdrant_client.get_collections.return_value = MagicMock(collections=[])
_mock_qdrant_client.get_collection.return_value = MagicMock(points_count=10)
_mock_qdrant_client.scroll.return_value = ([], None)

_mock_embed = MagicMock()
_mock_embed.aembed_query = AsyncMock(return_value=[0.1] * 10)

_mock_vsh = MagicMock()
_mock_vsh.qdrant_client = _mock_qdrant_client
_mock_vsh.PARTY_INDEX_NAME = "all_parties"
_mock_vsh.CANDIDATES_INDEX_NAME = "candidates_websites"
_mock_vsh.embed = _mock_embed
_mock_vsh.identify_relevant_docs_combined = AsyncMock(return_value=([], []))
_mock_vsh.identify_relevant_parliamentary_questions = AsyncMock(return_value=[])
sys.modules.setdefault("src.vector_store_helper", _mock_vsh)

# --- chatbot_async mock ---
_mock_chatbot = MagicMock()
_mock_chatbot.get_improved_rag_query_voting_behavior = AsyncMock(
    return_value="improved query"
)
sys.modules.setdefault("src.chatbot_async", _mock_chatbot)

# --- websocket_app mock ---
_mock_sio = MagicMock()
_mock_sio.attach = MagicMock()
_mock_websocket_app = MagicMock()
_mock_websocket_app.sio = _mock_sio
sys.modules.setdefault("src.websocket_app", _mock_websocket_app)

# --- services mocks ---
_mock_manifesto_indexer = MagicMock()
_mock_manifesto_indexer.index_all_parties = AsyncMock(return_value={"lfi": 5, "rn": 3})
_mock_manifesto_indexer.index_party_by_id = AsyncMock(return_value=3)
sys.modules.setdefault("src.services.manifesto_indexer", _mock_manifesto_indexer)

_mock_candidate_indexer = MagicMock()
_mock_candidate_indexer.index_all_candidates = AsyncMock(return_value={"cand-001": 4})
_mock_candidate_indexer.index_candidate_by_id = AsyncMock(return_value=2)
_mock_candidate_indexer._get_indexed_candidate_counts = MagicMock(return_value={})
sys.modules.setdefault("src.services.candidate_indexer", _mock_candidate_indexer)

_mock_firestore_listener = MagicMock()
_mock_firestore_listener.start_parties_listener = MagicMock()
_mock_firestore_listener.start_candidates_listener = MagicMock()
_mock_firestore_listener.is_listener_running = MagicMock(return_value=False)
_mock_firestore_listener.is_candidates_listener_running = MagicMock(return_value=False)
sys.modules.setdefault("src.services.firestore_listener", _mock_firestore_listener)

_mock_document_upload = MagicMock()
_mock_document_upload.create_job = MagicMock(return_value="job-001")
_mock_document_upload.get_job = MagicMock(return_value={"status": "done"})
_mock_document_upload.get_all_jobs = MagicMock(return_value=[])
_mock_document_upload.process_upload = AsyncMock()
sys.modules.setdefault("src.services.document_upload", _mock_document_upload)

_mock_scheduler = MagicMock()
_mock_scheduler.create_scheduler = MagicMock(return_value=MagicMock())
sys.modules.setdefault("src.services.scheduler", _mock_scheduler)

# data pipeline sub-mocks
_mock_data_pipeline = MagicMock()
_mock_data_pipeline.PIPELINE_NODES = {}
_mock_data_pipeline.clear_context = MagicMock()
sys.modules.setdefault("src.services.data_pipeline", _mock_data_pipeline)
sys.modules.setdefault("src.services.data_pipeline.base", MagicMock())
sys.modules.setdefault("src.services.data_pipeline.population", MagicMock())
sys.modules.setdefault("src.services.data_pipeline.candidatures", MagicMock())
sys.modules.setdefault("src.services.data_pipeline.websites", MagicMock())
sys.modules.setdefault("src.services.data_pipeline.crawl_scraper", MagicMock())
sys.modules.setdefault("src.services.k8s_job_launcher", MagicMock())

# src.utils — mock get_cors_allowed_origins
_mock_utils = MagicMock()
_mock_utils.get_cors_allowed_origins = MagicMock(return_value=["*"])
sys.modules.setdefault("src.utils", _mock_utils)

# src.models.chunk_metadata — referenced lazily inside handlers
_mock_chunk_metadata = MagicMock()
_mock_chunk_metadata.THEME_TAXONOMY = ["economie", "education"]
_mock_chunk_metadata.Fiabilite = MagicMock()
sys.modules.setdefault("src.models.chunk_metadata", _mock_chunk_metadata)

# qdrant_client is a real installed package — do NOT mock it in sys.modules
# as that breaks other test files that import from it (e.g. test_vector_store_helper.py)

# aiohttp_pydantic.decorator.inject_params — stub the decorator so it's a no-op
_mock_aiohttp_pydantic_decorator = MagicMock()


def _passthrough_decorator(fn):
    return fn


_mock_aiohttp_pydantic_decorator.inject_params = _passthrough_decorator
sys.modules.setdefault("aiohttp_pydantic", MagicMock())
sys.modules["aiohttp_pydantic.decorator"] = _mock_aiohttp_pydantic_decorator

# ---------------------------------------------------------------------------
# Now safe to import the app module
# ---------------------------------------------------------------------------
from src import aiohttp_app  # noqa: E402

# Patch module-level objects that were imported by value at module load time
aiohttp_app.async_db = _mock_async_db
aiohttp_app.db = _mock_db
aiohttp_app.qdrant_client = _mock_qdrant_client
aiohttp_app.embed = _mock_embed
aiohttp_app.NON_DETERMINISTIC_LLMS = [_fake_llm]
aiohttp_app.reset_all_rate_limits = _mock_llms.reset_all_rate_limits
aiohttp_app.is_listener_running = _mock_firestore_listener.is_listener_running
aiohttp_app.is_candidates_listener_running = (
    _mock_firestore_listener.is_candidates_listener_running
)
aiohttp_app.index_party_by_id = _mock_manifesto_indexer.index_party_by_id
aiohttp_app.index_candidate_by_id = _mock_candidate_indexer.index_candidate_by_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_fresh_app():  # -> aiohttp.web.Application
    """Build a fresh aiohttp Application each time so it doesn't share the
    module-level event loop that was bound at import time."""
    import aiohttp_cors
    from aiohttp import web as _web

    fresh_app = _web.Application(middlewares=[aiohttp_app.api_key_middleware])
    fresh_app.router.add_routes(aiohttp_app.routes)

    # Minimal CORS setup (allow all) so route iteration doesn't error
    cors = aiohttp_cors.setup(fresh_app)
    cors_opts = aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
        allow_methods="*",
    )
    for route in list(fresh_app.router.routes()):
        cors.add(route, {"*": cors_opts})

    return fresh_app


# ---------------------------------------------------------------------------
# Fixtures — use TestServer + TestClient directly (no pytest-aiohttp required)
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Spin up a fresh aiohttp TestServer per test and return a TestClient."""
    app = _build_fresh_app()
    server = TestServer(app)
    tc = TestClient(server)
    await tc.start_server()
    yield tc
    await tc.close()


@pytest.fixture(autouse=True)
def reset_secrets(monkeypatch):
    """Ensure ADMIN_SECRET is unset for each test."""
    monkeypatch.delenv("ADMIN_SECRET", raising=False)


# ---------------------------------------------------------------------------
# /healthz — simple k8s liveness probe
# ---------------------------------------------------------------------------


class TestHealthz:
    async def test_healthz_returns_200(self, client):
        resp = await client.get("/healthz")
        assert resp.status == 200

    async def test_healthz_returns_ok_body(self, client):
        resp = await client.get("/healthz")
        data = await resp.json()
        assert data == {"status": "ok"}


# ---------------------------------------------------------------------------
# /health — deep health check
# ---------------------------------------------------------------------------


class TestHealthDeep:
    async def test_health_ok_when_all_services_healthy(self, client):
        _mock_qdrant_client.get_collections.side_effect = None
        _mock_qdrant_client.get_collections.return_value = MagicMock(collections=[])
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=MagicMock()
        )
        _fake_llm.is_at_rate_limit = False
        aiohttp_app.NON_DETERMINISTIC_LLMS = [_fake_llm]

        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["checks"]["qdrant"]["status"] == "ok"
        assert data["checks"]["firestore"]["status"] == "ok"
        assert data["checks"]["llms"]["status"] == "ok"
        assert data["checks"]["stateless"]["status"] == "ok"

    async def test_health_degraded_when_qdrant_fails(self, client):
        _mock_qdrant_client.get_collections.side_effect = Exception("conn refused")
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=MagicMock()
        )
        _fake_llm.is_at_rate_limit = False
        aiohttp_app.NON_DETERMINISTIC_LLMS = [_fake_llm]

        resp = await client.get("/health")
        assert resp.status == 503
        data = await resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["qdrant"]["status"] == "error"
        # restore
        _mock_qdrant_client.get_collections.side_effect = None

    async def test_health_degraded_when_all_llms_rate_limited(self, client):
        _mock_qdrant_client.get_collections.side_effect = None
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=MagicMock()
        )
        _fake_llm.is_at_rate_limit = True
        aiohttp_app.NON_DETERMINISTIC_LLMS = [_fake_llm]

        resp = await client.get("/health")
        assert resp.status == 503
        data = await resp.json()
        assert data["checks"]["llms"]["status"] == "error"
        # restore
        _fake_llm.is_at_rate_limit = False
        aiohttp_app.NON_DETERMINISTIC_LLMS = [_fake_llm]

    async def test_health_degraded_when_no_llms_configured(self, client):
        _mock_qdrant_client.get_collections.side_effect = None
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=MagicMock()
        )
        aiohttp_app.NON_DETERMINISTIC_LLMS = []

        resp = await client.get("/health")
        assert resp.status == 503
        data = await resp.json()
        assert data["checks"]["llms"]["status"] == "error"
        # restore
        aiohttp_app.NON_DETERMINISTIC_LLMS = [_fake_llm]

    async def test_health_includes_stateless_check(self, client):
        _mock_qdrant_client.get_collections.side_effect = None
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=MagicMock()
        )
        _fake_llm.is_at_rate_limit = False
        aiohttp_app.NON_DETERMINISTIC_LLMS = [_fake_llm]

        resp = await client.get("/health")
        data = await resp.json()
        assert "stateless" in data["checks"]
        assert data["checks"]["stateless"]["status"] == "ok"


# ---------------------------------------------------------------------------
# /api/v1/assistant
# ---------------------------------------------------------------------------


class TestAssistantEndpoint:
    async def test_returns_200(self, client):
        resp = await client.get("/api/v1/assistant")
        assert resp.status == 200

    async def test_returns_correct_assistant_id(self, client):
        resp = await client.get("/api/v1/assistant")
        data = await resp.json()
        assert data["assistant_id"] == "chat-vote"

    async def test_returns_expected_fields(self, client):
        resp = await client.get("/api/v1/assistant")
        data = await resp.json()
        for field in (
            "assistant_id",
            "name",
            "long_name",
            "description",
            "website_url",
        ):
            assert field in data

    async def test_returns_json_content_type(self, client):
        resp = await client.get("/api/v1/assistant")
        assert "application/json" in resp.content_type


# ---------------------------------------------------------------------------
# Upload endpoints now use _check_admin_secret (X-Admin-Secret / ADMIN_SECRET)
# ---------------------------------------------------------------------------


class TestUploadAdminSecret:
    async def test_200_when_no_secret_configured(self, client):
        # No ADMIN_SECRET → _check_admin_secret returns True → allows all
        resp = await client.get("/api/v1/admin/upload-status")
        assert resp.status == 200

    async def test_404_when_wrong_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "correct")
        resp = await client.get(
            "/api/v1/admin/upload-status",
            headers={"X-Admin-Secret": "wrong"},
        )
        assert resp.status == 404

    async def test_200_when_correct_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "s3cret")
        _mock_document_upload.get_all_jobs.return_value = []
        resp = await client.get(
            "/api/v1/admin/upload-status",
            headers={"X-Admin-Secret": "s3cret"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "jobs" in data


# ---------------------------------------------------------------------------
# _check_admin_secret — tested via /api/v1/admin/listener-status  (GET)
# ---------------------------------------------------------------------------


class TestCheckAdminSecret:
    """Test _check_admin_secret via /api/v1/admin/maintenance (GET) which enforces it."""

    async def test_accessible_when_no_secret_configured(self, client):
        # No ADMIN_SECRET → _check_admin_secret returns True → route proceeds
        doc = MagicMock()
        doc.exists = False
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )
        resp = await client.get("/api/v1/admin/maintenance")
        assert resp.status == 200

    async def test_401_with_missing_header_when_secret_configured(self, client):
        os.environ["ADMIN_SECRET"] = "admin-secret"
        try:
            resp = await client.get("/api/v1/admin/maintenance")
            assert resp.status == 401
        finally:
            del os.environ["ADMIN_SECRET"]

    async def test_401_with_wrong_header(self, client):
        os.environ["ADMIN_SECRET"] = "admin-secret"
        try:
            resp = await client.get(
                "/api/v1/admin/maintenance",
                headers={"X-Admin-Secret": "bad"},
            )
            assert resp.status == 401
        finally:
            del os.environ["ADMIN_SECRET"]

    async def test_200_with_correct_header(self, client):
        os.environ["ADMIN_SECRET"] = "admin-secret"
        doc = MagicMock()
        doc.exists = False
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )
        try:
            resp = await client.get(
                "/api/v1/admin/maintenance",
                headers={"X-Admin-Secret": "admin-secret"},
            )
            assert resp.status == 200
        finally:
            del os.environ["ADMIN_SECRET"]


# ---------------------------------------------------------------------------
# /api/v1/admin/listener-status
# ---------------------------------------------------------------------------


class TestListenerStatus:
    async def test_returns_listener_flags(self, client):
        _mock_firestore_listener.is_listener_running.return_value = True
        _mock_firestore_listener.is_candidates_listener_running.return_value = False
        aiohttp_app.is_listener_running = _mock_firestore_listener.is_listener_running
        aiohttp_app.is_candidates_listener_running = (
            _mock_firestore_listener.is_candidates_listener_running
        )
        resp = await client.get("/api/v1/admin/listener-status")
        assert resp.status == 200
        data = await resp.json()
        assert data["parties_listener_running"] is True
        assert data["candidates_listener_running"] is False


# ---------------------------------------------------------------------------
# /api/v1/admin/index-status
# ---------------------------------------------------------------------------


class TestIndexStatus:
    async def test_returns_indexing_status_keys(self, client):
        resp = await client.get("/api/v1/admin/index-status")
        assert resp.status == 200
        data = await resp.json()
        assert "manifestos" in data
        assert "candidates" in data


# ---------------------------------------------------------------------------
# /api/v1/admin/index-all-manifestos  (POST)
# ---------------------------------------------------------------------------


class TestIndexAllManifestos:
    async def test_returns_started_status(self, client):
        resp = await client.post("/api/v1/admin/index-all-manifestos")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "started"

    async def test_response_includes_message(self, client):
        resp = await client.post("/api/v1/admin/index-all-manifestos")
        data = await resp.json()
        assert "message" in data


# ---------------------------------------------------------------------------
# /api/v1/admin/index-all-candidates  (POST)
# ---------------------------------------------------------------------------


class TestIndexAllCandidates:
    async def test_returns_started_status(self, client):
        resp = await client.post("/api/v1/admin/index-all-candidates")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "started"

    async def test_accepts_scraper_and_force_query_params(self, client):
        resp = await client.post(
            "/api/v1/admin/index-all-candidates?scraper=playwright&force=true"
        )
        assert resp.status == 200


# ---------------------------------------------------------------------------
# /api/v1/admin/index-party-manifesto/{party_id}  (POST)
# ---------------------------------------------------------------------------


class TestIndexPartyManifesto:
    async def test_success_when_chunks_indexed(self, client):
        aiohttp_app.index_party_by_id = AsyncMock(return_value=5)
        resp = await client.post("/api/v1/admin/index-party-manifesto/lfi")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "success"
        assert "lfi" in data["message"]

    async def test_warning_when_zero_chunks(self, client):
        aiohttp_app.index_party_by_id = AsyncMock(return_value=0)
        resp = await client.post("/api/v1/admin/index-party-manifesto/unknown")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "warning"

    async def test_500_when_indexer_raises(self, client):
        aiohttp_app.index_party_by_id = AsyncMock(
            side_effect=Exception("indexer error")
        )
        resp = await client.post("/api/v1/admin/index-party-manifesto/lfi")
        assert resp.status == 500
        data = await resp.json()
        assert data["status"] == "error"


# ---------------------------------------------------------------------------
# /api/v1/admin/index-candidate-website/{candidate_id}  (POST)
# ---------------------------------------------------------------------------


class TestIndexCandidateWebsite:
    async def test_success_when_chunks_indexed(self, client):
        aiohttp_app.index_candidate_by_id = AsyncMock(return_value=3)
        resp = await client.post("/api/v1/admin/index-candidate-website/cand-001")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "success"

    async def test_warning_when_zero_chunks(self, client):
        aiohttp_app.index_candidate_by_id = AsyncMock(return_value=0)
        resp = await client.post("/api/v1/admin/index-candidate-website/unknown")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "warning"

    async def test_500_when_indexer_raises(self, client):
        aiohttp_app.index_candidate_by_id = AsyncMock(side_effect=Exception("boom"))
        resp = await client.post("/api/v1/admin/index-candidate-website/cand-001")
        assert resp.status == 500


# ---------------------------------------------------------------------------
# /api/v1/admin/reset-rate-limit  (POST)
# ---------------------------------------------------------------------------


class TestResetRateLimit:
    async def test_returns_success(self, client):
        aiohttp_app.reset_all_rate_limits = AsyncMock()
        resp = await client.post("/api/v1/admin/reset-rate-limit")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "success"

    async def test_500_when_reset_raises(self, client):
        aiohttp_app.reset_all_rate_limits = AsyncMock(side_effect=Exception("fail"))
        resp = await client.post("/api/v1/admin/reset-rate-limit")
        assert resp.status == 500
        # restore
        aiohttp_app.reset_all_rate_limits = AsyncMock()


# ---------------------------------------------------------------------------
# /api/v1/maintenance  (public GET)
# ---------------------------------------------------------------------------


class TestPublicMaintenanceStatus:
    async def test_returns_disabled_when_doc_not_found(self, client):
        doc = MagicMock()
        doc.exists = False
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )
        resp = await client.get("/api/v1/maintenance")
        assert resp.status == 200
        data = await resp.json()
        assert data["enabled"] is False
        assert "message" in data

    async def test_returns_enabled_when_doc_says_enabled(self, client):
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {"enabled": True, "message": "Maintenance en cours"}
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )
        resp = await client.get("/api/v1/maintenance")
        assert resp.status == 200
        data = await resp.json()
        assert data["enabled"] is True
        assert data["message"] == "Maintenance en cours"

    async def test_returns_disabled_on_firestore_error(self, client):
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            side_effect=Exception("firestore down")
        )
        resp = await client.get("/api/v1/maintenance")
        assert resp.status == 200
        data = await resp.json()
        assert data["enabled"] is False


# ---------------------------------------------------------------------------
# /api/v1/admin/maintenance  (admin GET)
# ---------------------------------------------------------------------------


class TestAdminGetMaintenance:
    async def test_401_without_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        resp = await client.get("/api/v1/admin/maintenance")
        assert resp.status == 401

    async def test_returns_maintenance_data_with_valid_secret(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {"enabled": False, "message": "", "updated_at": None}
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )
        resp = await client.get(
            "/api/v1/admin/maintenance",
            headers={"X-Admin-Secret": "secret123"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "enabled" in data
        assert "message" in data

    async def test_returns_defaults_when_doc_missing(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        doc = MagicMock()
        doc.exists = False
        _mock_async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )
        resp = await client.get(
            "/api/v1/admin/maintenance",
            headers={"X-Admin-Secret": "secret123"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["enabled"] is False


# ---------------------------------------------------------------------------
# /api/v1/admin/maintenance  (admin PUT)
# ---------------------------------------------------------------------------


class TestAdminSetMaintenance:
    async def test_401_without_secret(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        resp = await client.put(
            "/api/v1/admin/maintenance",
            data=json.dumps({"enabled": True}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 401

    async def test_400_for_invalid_json(self, client):
        resp = await client.put(
            "/api/v1/admin/maintenance",
            data="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_enables_maintenance_mode(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        _mock_async_db.collection.return_value.document.return_value.set = AsyncMock()
        resp = await client.put(
            "/api/v1/admin/maintenance",
            data=json.dumps({"enabled": True, "message": "Back soon"}),
            headers={
                "Content-Type": "application/json",
                "X-Admin-Secret": "secret123",
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["enabled"] is True
        assert data["message"] == "Back soon"

    async def test_disables_maintenance_mode(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        _mock_async_db.collection.return_value.document.return_value.set = AsyncMock()
        resp = await client.put(
            "/api/v1/admin/maintenance",
            data=json.dumps({"enabled": False, "message": ""}),
            headers={
                "Content-Type": "application/json",
                "X-Admin-Secret": "secret123",
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["enabled"] is False

    async def test_500_when_firestore_write_fails(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        _mock_async_db.collection.return_value.document.return_value.set = AsyncMock(
            side_effect=Exception("write failed")
        )
        resp = await client.put(
            "/api/v1/admin/maintenance",
            data=json.dumps({"enabled": True}),
            headers={
                "Content-Type": "application/json",
                "X-Admin-Secret": "secret123",
            },
        )
        assert resp.status == 500


# ---------------------------------------------------------------------------
# api_key_middleware — OPTIONS and normal request passthrough
# ---------------------------------------------------------------------------


class TestApiKeyMiddleware:
    async def test_options_passes_through(self, client):
        resp = await client.options("/healthz")
        # CORS handles OPTIONS — must not be blocked by our middleware (not 401)
        assert resp.status != 401

    async def test_get_passes_through_to_handler(self, client):
        resp = await client.get("/healthz")
        assert resp.status == 200


# ---------------------------------------------------------------------------
# /api/v1/admin/upload-status/{job_id}  (GET)
# ---------------------------------------------------------------------------


class TestUploadJobStatus:
    async def test_200_without_secret_in_dev_mode(self, client):
        """When ADMIN_SECRET is unset, endpoint is accessible."""
        resp = await client.get("/api/v1/admin/upload-status/job-123")
        assert resp.status == 200

    async def test_returns_job_data_when_found(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "s3cret")
        _mock_document_upload.get_job.return_value = {
            "job_id": "job-123",
            "status": "done",
            "filename": "test.pdf",
        }
        resp = await client.get(
            "/api/v1/admin/upload-status/job-123",
            headers={"X-Admin-Secret": "s3cret"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "done"

    async def test_404_when_job_not_found(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "s3cret")
        _mock_document_upload.get_job.return_value = None
        resp = await client.get(
            "/api/v1/admin/upload-status/nonexistent",
            headers={"X-Admin-Secret": "s3cret"},
        )
        assert resp.status == 404


# ---------------------------------------------------------------------------
# /api/v1/admin/data-sources/run/{node_id}  (POST)
# ---------------------------------------------------------------------------


class TestDsRunNode:
    async def test_404_for_unknown_node(self, client):
        # Ensure the mocked data_pipeline module has an empty PIPELINE_NODES
        sys.modules["src.services.data_pipeline"].PIPELINE_NODES = {}
        resp = await client.post(
            "/api/v1/admin/data-sources/run/nonexistent",
            data="{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 404

    async def test_401_without_secret_when_secret_configured(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        resp = await client.post("/api/v1/admin/data-sources/run/population")
        assert resp.status == 401


# ---------------------------------------------------------------------------
# /api/v1/admin/data-sources/bust-cache  (POST)
# ---------------------------------------------------------------------------


class TestDsBustCache:
    async def test_401_without_secret_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret123")
        resp = await client.post("/api/v1/admin/data-sources/bust-cache")
        assert resp.status == 401

    async def test_ok_without_secret_env_set(self, client):
        resp = await client.post("/api/v1/admin/data-sources/bust-cache")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# /api/v1/experiment/search  (POST) — input validation
# ---------------------------------------------------------------------------


class TestExperimentSearch:
    async def test_400_when_query_missing(self, client):
        resp = await client.post(
            "/api/v1/experiment/search",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["status"] == "error"
        assert "query" in data["message"]

    async def test_500_on_embed_error(self, client):
        aiohttp_app.embed = MagicMock()
        aiohttp_app.embed.aembed_query = AsyncMock(
            side_effect=Exception("embed failed")
        )
        resp = await client.post(
            "/api/v1/experiment/search",
            data=json.dumps({"query": "test query"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 500
        # restore
        aiohttp_app.embed = _mock_embed


# ---------------------------------------------------------------------------
# /api/v1/admin/multi-query  (POST) — input validation
# ---------------------------------------------------------------------------


class TestAdminMultiQuery:
    async def test_401_without_secret_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_SECRET", "secret")
        resp = await client.post(
            "/api/v1/admin/multi-query",
            data=json.dumps({"query": "test"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 401

    async def test_400_when_query_missing(self, client):
        resp = await client.post(
            "/api/v1/admin/multi-query",
            data=json.dumps({}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert "query" in data["message"]

    async def test_400_when_municipality_codes_empty(self, client):
        resp = await client.post(
            "/api/v1/admin/multi-query",
            data=json.dumps({"query": "test", "municipality_codes": []}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_400_for_invalid_json(self, client):
        resp = await client.post(
            "/api/v1/admin/multi-query",
            data="bad-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400
