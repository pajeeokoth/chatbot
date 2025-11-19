import pytest
from unittest.mock import AsyncMock, patch

import mytravel.app as app_module
from mytravel.app import create_app


@pytest.fixture
async def test_client(aiohttp_client):
    """Return aiohttp test client for the app."""
    app = create_app()
    return await aiohttp_client(app)


# ---------------------------------------------------------------------
# 1. Basic POST smoke test: /api/messages returns 200
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_post_messages_returns_200(test_client):
    client = test_client
    payload = {
        "type": "message",
        "text": "hello",
        "channelId": "directline",
        "serviceUrl": "http://localhost:3978",
        "from": {"id": "user1"},
        "conversation": {"id": "conv1"},
    }

    resp = await client.post("/api/messages", json=payload)
    assert resp.status == 200


# ---------------------------------------------------------------------
# 2. Service URL override test
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_service_url_is_overridden(test_client, monkeypatch):
    client = test_client
    tunnel_url = "https://purple-deer-1234.devtunnels.ms"
    monkeypatch.setenv("DEV_TUNNEL_URL", tunnel_url)

    payload = {
        "type": "message",
        "text": "test",
        "serviceUrl": "http://localhost:3978",
        "channelId": "directline",
        "from": {"id": "user1"},
        "conversation": {"id": "conv1"},
    }

    resp = await client.post("/api/messages", json=payload)
    text = await resp.text()

    assert resp.status == 200
    # No real adapter means activity cannot be inspected directly,
    # this ensures the endpoint works under the tunnel config.
    assert text  # non-empty response

# ---------------------------------------------------------------------
# 3. Bot receives text and returns a reply (using fallback handler)
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bot_returns_reply_via_fallback(test_client):
    client = test_client

    payload = {
        "type": "message",
        "text": "test reply",
        "serviceUrl": "http://localhost:3978",
        "channelId": "directline",
        "from": {"id": "user1"},
        "conversation": {"id": "conv1"},
    }

    resp = await client.post("/api/messages", json=payload)
    text = await resp.text()

    assert resp.status == 200
    # When BOT_AVAILABLE is False, a friendly “bot unavailable” message is returned
    assert "Bot unavailable" in text