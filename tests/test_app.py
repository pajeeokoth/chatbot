import pytest
import sys
from pathlib import Path

import pytest_asyncio

sys.path.append(str(Path(__file__).resolve().parent.parent))

from mytravel.app import create_app


@pytest_asyncio.fixture
async def client(aiohttp_client):
    """Return aiohttp test client for the app."""
    app = create_app()
    return await aiohttp_client(app)


# ---------------------------------------------------------------------
# 1. Basic health smoke test: response returns 200
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status == 200
    text = await resp.text()
    assert "OK" in text

# ---------------------------------------------------------------------
# 2. Basic Index page test: response contains title
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_index_page_contains_title(client):
    resp = await client.get("/")
    assert resp.status == 200
    text = await resp.text()
    assert "MyTravel Bot" in text


# ---------------------------------------------------------------------
# 3. Basic POST smoke test: /api/messages returns 200
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_post_messages_returns_ok(client):
    payload = {
        "type": "message",
        "text": "hello",
        "from": {"id": "test-user"},
        "recipient": {"id": "bot"},
        "conversation": {"id": "conv"},
        "channelId": "webchat",
    }
    resp = await client.post("/api/messages", json=payload)
    assert resp.status == 200
    text = await resp.text()
    assert text, "Expected some reply text from /api/messages"
