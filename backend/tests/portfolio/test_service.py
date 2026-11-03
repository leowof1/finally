"""Tests for trade execution and portfolio valuation."""

import pytest

from app import db
from app.market import PriceCache
from app.portfolio import TradeError, execute_trade, get_portfolio


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """Fresh DB plus a cache with fixed prices."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    db.init_db()
    c = PriceCache()
    c.update("AAPL", 100.0)
    c.update("MSFT", 200.0)
    return c


def test_buy_deducts_cash_and_creates_position(cache):
    trade = execute_trade(cache, "aapl", "buy", 10)
    assert trade["ticker"] == "AAPL"
    assert trade["price"] == 100.0
    assert db.get_cash() == pytest.approx(9000.0)
    assert db.get_position("AAPL")["quantity"] == 10


def test_buy_averages_cost(cache):
    execute_trade(cache, "AAPL", "buy", 10)
    cache.update("AAPL", 130.0)
    execute_trade(cache, "AAPL", "buy", 5)
    position = db.get_position("AAPL")
    assert position["quantity"] == 15
    assert position["avg_cost"] == pytest.approx((1000 + 650) / 15)


def test_insufficient_cash(cache):
    with pytest.raises(TradeError, match="Insufficient cash"):
        execute_trade(cache, "AAPL", "buy", 101)
    assert db.get_cash() == 10000.0


def test_sell_more_than_owned(cache):
    execute_trade(cache, "AAPL", "buy", 5)
    with pytest.raises(TradeError, match="Insufficient shares"):
        execute_trade(cache, "AAPL", "sell", 6)


def test_sell_without_position(cache):
    with pytest.raises(TradeError):
        execute_trade(cache, "AAPL", "sell", 1)


def test_sell_at_loss_keeps_avg_cost(cache):
    execute_trade(cache, "AAPL", "buy", 10)
    cache.update("AAPL", 80.0)
    execute_trade(cache, "AAPL", "sell", 4)
    assert db.get_cash() == pytest.approx(9000 + 320)
    position = db.get_position("AAPL")
    assert position["quantity"] == 6
    assert position["avg_cost"] == pytest.approx(100.0)


def test_sell_all_deletes_position_with_float_dust(cache):
    execute_trade(cache, "AAPL", "buy", 0.1)
    execute_trade(cache, "AAPL", "buy", 0.2)
    execute_trade(cache, "AAPL", "sell", 0.3)
    assert db.get_position("AAPL") is None


def test_rejects_bad_input(cache):
    with pytest.raises(TradeError):
        execute_trade(cache, "AAPL", "buy", 0)
    with pytest.raises(TradeError):
        execute_trade(cache, "AAPL", "hold", 1)
    with pytest.raises(TradeError, match="No price"):
        execute_trade(cache, "ZZZZ", "buy", 1)


def test_trade_records_snapshot(cache):
    execute_trade(cache, "AAPL", "buy", 1)
    assert db.get_snapshots()[-1]["total_value"] == pytest.approx(10000.0)


def test_portfolio_valuation(cache):
    execute_trade(cache, "AAPL", "buy", 10)
    execute_trade(cache, "MSFT", "buy", 5)
    cache.update("AAPL", 110.0)
    cache.update("MSFT", 190.0)
    p = get_portfolio(cache)
    assert p["cash_balance"] == pytest.approx(8000.0)
    assert p["total_value"] == pytest.approx(8000 + 1100 + 950)
    assert p["unrealized_pnl"] == pytest.approx(100 - 50)
    aapl = next(x for x in p["positions"] if x["ticker"] == "AAPL")
    assert aapl["current_price"] == 110.0
    assert aapl["market_value"] == pytest.approx(1100.0)
    assert aapl["pnl_percent"] == pytest.approx(10.0)
