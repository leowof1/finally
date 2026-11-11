"""Tests for trade execution and portfolio valuation."""

import pytest

from app.portfolio.service import (
    TradeError,
    execute_trade,
    get_cash,
    get_history,
    get_portfolio,
)


def test_buy_reduces_cash_and_creates_position(conn, cache):
    trade = execute_trade(conn, cache, "aapl", "buy", 10)
    assert trade["ticker"] == "AAPL"
    assert trade["price"] == 100.0
    assert get_cash(conn) == pytest.approx(9000.0)
    portfolio = get_portfolio(conn, cache)
    assert portfolio["positions"][0]["quantity"] == 10
    assert portfolio["total_value"] == pytest.approx(10000.0)


def test_buy_averages_cost(conn, cache):
    execute_trade(conn, cache, "AAPL", "buy", 10)
    cache.update("AAPL", 200.0)
    execute_trade(conn, cache, "AAPL", "buy", 10)
    position = get_portfolio(conn, cache)["positions"][0]
    assert position["avg_cost"] == pytest.approx(150.0)
    assert position["unrealized_pnl"] == pytest.approx(1000.0)


def test_fractional_shares(conn, cache):
    execute_trade(conn, cache, "AAPL", "buy", 0.5)
    assert get_cash(conn) == pytest.approx(9950.0)


def test_insufficient_cash(conn, cache):
    with pytest.raises(TradeError, match="Insufficient cash"):
        execute_trade(conn, cache, "AAPL", "buy", 101)
    assert get_cash(conn) == 10000.0


def test_sell_more_than_owned(conn, cache):
    execute_trade(conn, cache, "AAPL", "buy", 5)
    with pytest.raises(TradeError, match="Insufficient shares"):
        execute_trade(conn, cache, "AAPL", "sell", 6)


def test_sell_without_position(conn, cache):
    with pytest.raises(TradeError, match="Insufficient shares"):
        execute_trade(conn, cache, "TSLA", "sell", 1)


def test_partial_sell_keeps_avg_cost(conn, cache):
    execute_trade(conn, cache, "AAPL", "buy", 10)
    cache.update("AAPL", 120.0)
    execute_trade(conn, cache, "AAPL", "sell", 4)
    position = get_portfolio(conn, cache)["positions"][0]
    assert position["quantity"] == pytest.approx(6)
    assert position["avg_cost"] == pytest.approx(100.0)
    assert get_cash(conn) == pytest.approx(9000.0 + 480.0)


def test_sell_at_loss_closes_position(conn, cache):
    execute_trade(conn, cache, "AAPL", "buy", 10)
    cache.update("AAPL", 80.0)
    execute_trade(conn, cache, "AAPL", "sell", 10)
    portfolio = get_portfolio(conn, cache)
    assert portfolio["positions"] == []
    assert portfolio["cash_balance"] == pytest.approx(9800.0)


def test_invalid_inputs(conn, cache):
    with pytest.raises(TradeError):
        execute_trade(conn, cache, "AAPL", "hold", 1)
    with pytest.raises(TradeError):
        execute_trade(conn, cache, "AAPL", "buy", 0)
    with pytest.raises(TradeError, match="No price"):
        execute_trade(conn, cache, "ZZZZ", "buy", 1)


def test_trade_records_snapshot(conn, cache):
    execute_trade(conn, cache, "AAPL", "buy", 1)
    history = get_history(conn)
    assert len(history) == 1
    assert history[0]["total_value"] == pytest.approx(10000.0)
