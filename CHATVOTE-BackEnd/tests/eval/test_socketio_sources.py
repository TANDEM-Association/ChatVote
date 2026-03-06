"""
Socket.IO integration test for source delivery.

Verifies that the full Socket.IO pipeline delivers sources alongside
streamed responses — catching issues the direct-function e2e tests miss.

Requires: Backend running on localhost:8080 + Qdrant + LLM API key.

Run:
    poetry run pytest tests/eval/test_socketio_sources.py -v -s
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _skip_if_no_backend():
    """Skip if backend is not running."""
    import urllib.request
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8080")
    try:
        urllib.request.urlopen(f"{backend_url}/health", timeout=3)
    except Exception:
        pytest.skip(f"Backend not reachable at {backend_url}")


@pytest.fixture(scope="module")
def backend_url():
    _skip_if_no_backend()
    return os.environ.get("BACKEND_URL", "http://localhost:8080")


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def test_socketio_delivers_sources(backend_url, event_loop):
    """Connect via Socket.IO, send a question, verify sources are delivered."""
    try:
        import socketio
    except ImportError:
        pytest.skip("python-socketio not installed")

    received_events = {
        "sources_ready": [],
        "party_response_chunk_ready": [],
        "chat_response_complete": [],
    }
    connection_error = None

    async def _run():
        nonlocal connection_error

        sio = socketio.AsyncClient()

        @sio.on("sources_ready")
        async def on_sources(data):
            received_events["sources_ready"].append(data)

        @sio.on("party_response_chunk_ready")
        async def on_chunk(data):
            received_events["party_response_chunk_ready"].append(data)

        @sio.on("chat_response_complete")
        async def on_complete(data):
            received_events["chat_response_complete"].append(data)

        try:
            await sio.connect(backend_url, transports=["websocket"])
        except Exception as e:
            connection_error = str(e)
            return

        session_id = str(uuid.uuid4())

        # Init session
        init_future = asyncio.Future()

        @sio.on("chat_session_initialized")
        async def on_init(data):
            if not init_future.done():
                init_future.set_result(data)

        await sio.emit("chat_session_init", {
            "session_id": session_id,
            "municipality_code": "33063",  # Bordeaux
        })

        try:
            await asyncio.wait_for(init_future, timeout=10)
        except asyncio.TimeoutError:
            await sio.disconnect()
            pytest.skip("Session init timed out — backend may not be fully configured")
            return

        # Send a question
        complete_future = asyncio.Future()

        @sio.on("chat_response_complete")
        async def on_complete_resolve(data):
            received_events["chat_response_complete"].append(data)
            if not complete_future.done():
                complete_future.set_result(data)

        await sio.emit("chat_answer_request", {
            "session_id": session_id,
            "user_message": "Que propose Renaissance pour les communes ?",
            "party_ids": ["renaissance"],
        })

        try:
            await asyncio.wait_for(complete_future, timeout=60)
        except asyncio.TimeoutError:
            await sio.disconnect()
            pytest.fail("chat_response_complete never received within 60s")
            return

        await sio.disconnect()

    event_loop.run_until_complete(_run())

    if connection_error:
        pytest.skip(f"Could not connect to backend: {connection_error}")

    # Assertions: sources must have been delivered
    assert len(received_events["sources_ready"]) > 0, (
        "No 'sources_ready' event received — sources are not being delivered to the client"
    )

    # Verify sources contain actual data
    for sources_event in received_events["sources_ready"]:
        sources = sources_event.get("sources", [])
        assert len(sources) > 0, (
            f"sources_ready event had empty sources list: {sources_event}"
        )

    # Verify we got response chunks
    assert len(received_events["party_response_chunk_ready"]) > 0, (
        "No response chunks received"
    )

    # Verify completion
    assert len(received_events["chat_response_complete"]) > 0, (
        "No chat_response_complete event received"
    )
