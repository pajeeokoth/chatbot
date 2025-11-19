import json
import os
import pytest
from aiohttp import web
from unittest.mock import AsyncMock, patch

# Import app
# from mytravel.app import app  
from mytravel.app import create_app

@pytest.fixture
async def test_client(aiohttp_client):
    app = create_app()
    return await aiohttp_client(app)

# @pytest.fixture
# def test_client(aiohttp_client):
#     return aiohttp_client


# ---------------------------------------------------------------------
# 1. Basic POST smoke test: /api/messages returns 200
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_post_messages_returns_200(test_client):
    # client = await test_client(app)
    client = await test_client


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
    # client = await test_client(app)
    client = await test_client


    tunnel_url = "https://purple-deer-1234.devtunnels.ms"
    monkeypatch.setenv("DEV_TUNNEL_URL", tunnel_url)

    mock_process = AsyncMock(return_value=None)

    # Patch adapter.process_activity so we can inspect the Activity passed in
    with patch("mytravel.app.adapter.process_activity", mock_process):
        payload = {
            "type": "message",
            "text": "test",
            "serviceUrl": "http://localhost:3978",
            "channelId": "directline",
            "from": {"id": "user1"},
            "conversation": {"id": "conv1"},
        }

        resp = await client.post("/api/messages", json=payload)
        assert resp.status == 200

        # get activity arg the adapter received
        called_activity = mock_process.call_args[0][0]
        assert called_activity.service_url == tunnel_url


# ---------------------------------------------------------------------
# 3. Bot receives text and returns a reply (using fallback handler)
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bot_returns_reply_via_fallback(test_client, monkeypatch):
    """
    Forces adapter.process_activity() to fail
    so the fallback SimpleTurnContext path runs.
    """
    # client = await test_client(app)
    client = await test_client


    # Force adapter to throw so fallback is used
    async def fail(*args, **kwargs):
        raise Exception("forced failure")

    monkeypatch.setattr("mytravel.app.adapter.process_activity", fail)

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
    assert "OK" in text or len(text) > 0  # TravelBot replies something


# ###############################################################################################
# import pytest
# from mytravel.app import create_app
# from unittest.mock import AsyncMock, patch

# @pytest.fixture
# async def test_client(aiohttp_client):
#     """Return aiohttp test client for the app."""
#     return await aiohttp_client(create_app())  # only this needs await

# @pytest.mark.asyncio
# async def test_post_messages_returns_200(test_client):
#     client = test_client  # NO await here
#     payload = {
#         "type": "message",
#         "text": "hello",
#         "channelId": "directline",
#         "serviceUrl": "http://localhost:3978",
#         "from": {"id": "user1"},
#         "conversation": {"id": "conv1"},
#     }
#     resp = await client.post("/api/messages", json=payload)
#     assert resp.status == 200

# @pytest.mark.asyncio
# async def test_service_url_is_overridden(test_client, monkeypatch):
#     client = test_client  # NO await here
#     tunnel_url = "https://purple-deer-1234.devtunnels.ms"
#     monkeypatch.setenv("DEV_TUNNEL_URL", tunnel_url)

#     mock_process = AsyncMock(return_value=None)
#     with patch("mytravel.app.adapter.process_activity", mock_process):
#         payload = {
#             "type": "message",
#             "text": "test",
#             "serviceUrl": "http://localhost:3978",
#             "channelId": "directline",
#             "from": {"id": "user1"},
#             "conversation": {"id": "conv1"},
#         }
#         resp = await client.post("/api/messages", json=payload)
#         assert resp.status == 200

#         # get activity arg the adapter received
#         called_activity = mock_process.call_args[0][0]
#         assert called_activity.service_url == tunnel_url

# @pytest.mark.asyncio
# async def test_bot_returns_reply_via_fallback(test_client, monkeypatch):
#     client = test_client  # NO await here

#     async def fail(*args, **kwargs):
#         raise Exception("forced failure")

#     monkeypatch.setattr("mytravel.app.adapter.process_activity", fail)

#     payload = {
#         "type": "message",
#         "text": "test reply",
#         "serviceUrl": "http://localhost:3978",
#         "channelId": "directline",
#         "from": {"id": "user1"},
#         "conversation": {"id": "conv1"},
#     }

#     resp = await client.post("/api/messages", json=payload)
#     text = await resp.text()
#     assert resp.status == 200
#     assert "OK" in text or len(text) > 0
