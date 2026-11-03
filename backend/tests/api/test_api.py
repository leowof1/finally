"""Tests for health, portfolio and watchlist HTTP endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with lifespan running against a fresh temp DB."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_fresh_portfolio(client):
    p = client.get("/api/portfolio").json()
    assert p == {"cash_balance": 10000.0, "total_value": 10000.0, "unrealized_pnl": 0.0, "positions": []}


def test_buy_then_sell(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "aapl", "quantity": 2, "side": "buy"})
    assert r.status_code == 200
    body = r.json()
    trade = body["trade"]
    assert set(trade) == {"ticker", "side", "quantity", "price", "executed_at"}
    assert trade["ticker"] == "AAPL"
    assert body["portfolio"]["cash_balance"] == pytest.approx(10000 - 2 * trade["price"], abs=0.01)
    position = body["portfolio"]["positions"][0]
    assert set(position) == {
        "ticker", "quantity", "avg_cost", "current_price", "market_value", "unrealized_pnl", "pnl_percent",
    }

    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "sell"})
    assert r.status_code == 200
    assert r.json()["portfolio"]["positions"] == []


def test_trade_errors_return_400(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 100000, "side": "buy"})
    assert r.status_code == 400
    assert "Insufficient cash" in r.json()["detail"]
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "sell"})
    assert r.status_code == 400


def test_trade_invalid_side_is_422(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "hold"})
    assert r.status_code == 422


def test_history_after_trade(client):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"})
    history = client.get("/api/portfolio/history").json()
    assert len(history) >= 1
    assert set(history[-1]) == {"total_value", "recorded_at"}


def test_watchlist_default(client):
    items = client.get("/api/watchlist").json()
    assert len(items) == 10
    aapl = next(i for i in items if i["ticker"] == "AAPL")
    assert set(aapl) == {"ticker", "price", "previous_price", "change_percent", "direction", "added_at"}
    assert aapl["price"] > 0


def test_watchlist_add_and_remove(client):
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 201
    assert r.json()["ticker"] == "PYPL"
    assert "PYPL" in client.app.state.market_source.get_tickers()
    assert client.post("/api/watchlist", json={"ticker": "PYPL"}).status_code == 409

    assert client.delete("/api/watchlist/pypl").status_code == 204
    assert "PYPL" not in client.app.state.market_source.get_tickers()
    assert client.delete("/api/watchlist/PYPL").status_code == 404


def test_watchlist_invalid_ticker(client):
    assert client.post("/api/watchlist", json={"ticker": "not a ticker!"}).status_code == 400
