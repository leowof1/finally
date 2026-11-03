"""HTTP tests for /api/chat in mock mode through the full app."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    """TestClient with lifespan running, mock LLM on (DB comes from the autouse fixture)."""
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c


def test_chat_buy_and_history(client):
    r = client.post("/api/chat", json={"message": "buy AAPL"})
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "Mock: bought 1 AAPL"
    assert body["trades"][0]["status"] == "executed"
    assert body["watchlist_changes"] == []
    assert client.get("/api/portfolio").json()["positions"][0]["ticker"] == "AAPL"

    history = client.get("/api/chat/history").json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "buy AAPL" and history[0]["actions"] is None
    assert history[1]["actions"]["trades"][0]["ticker"] == "AAPL"
    assert set(history[1]) == {"role", "content", "actions", "created_at"}


def test_chat_requires_message(client):
    assert client.post("/api/chat", json={}).status_code == 422
