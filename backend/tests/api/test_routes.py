"""API route tests using the real app with simulator and mock LLM."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.setenv("MASSIVE_API_KEY", "")
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_default_watchlist_has_prices(client):
    entries = client.get("/api/watchlist").json()
    assert len(entries) == 10
    assert all(e["price"] for e in entries)


def test_fresh_portfolio(client):
    portfolio = client.get("/api/portfolio").json()
    assert portfolio["cash_balance"] == 10000.0
    assert portfolio["total_value"] == 10000.0
    assert portfolio["positions"] == []


def test_buy_and_sell(client):
    response = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "buy"})
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio"]["positions"][0]["ticker"] == "AAPL"
    assert body["portfolio"]["cash_balance"] < 10000.0

    response = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "sell"})
    assert response.status_code == 200
    assert response.json()["portfolio"]["positions"] == []
    assert len(client.get("/api/portfolio/history").json()) == 2


def test_trade_validation_errors(client):
    too_big = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 100000, "side": "buy"})
    assert too_big.status_code == 400
    assert "Insufficient cash" in too_big.json()["detail"]
    bad_side = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "hold"})
    assert bad_side.status_code == 422


def test_watchlist_add_remove(client):
    added = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert added.status_code == 201
    assert added.json()["ticker"] == "PYPL"
    assert added.json()["price"] is not None
    assert client.post("/api/watchlist", json={"ticker": "PYPL"}).status_code == 409
    assert client.delete("/api/watchlist/PYPL").status_code == 200
    assert client.delete("/api/watchlist/PYPL").status_code == 404
    assert client.post("/api/watchlist", json={"ticker": "!!"}).status_code == 400


def test_chat_mock_executes_actions(client):
    response = client.post("/api/chat", json={"message": "Please buy 3 AAPL and add PYPL"})
    assert response.status_code == 200
    body = response.json()
    assert body["actions"]["trades"][0]["status"] == "ok"
    assert body["actions"]["watchlist_changes"][0]["ticker"] == "PYPL"
    assert body["portfolio"]["positions"][0]["quantity"] == 3
    tickers = [e["ticker"] for e in client.get("/api/watchlist").json()]
    assert "PYPL" in tickers


def test_chat_reports_failed_trade(client):
    body = client.post("/api/chat", json={"message": "sell 5 TSLA"}).json()
    assert body["actions"]["trades"][0]["status"] == "error"
    assert "Insufficient shares" in body["message"]
