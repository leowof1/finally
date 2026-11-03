"""Trade execution and portfolio valuation."""

from __future__ import annotations

from app import db
from app.market import PriceCache

DUST = 1e-6


class TradeError(Exception):
    """Raised when a trade fails validation."""


def execute_trade(cache: PriceCache, ticker: str, side: str, quantity: float) -> dict:
    """Execute a market order at the current cached price and record a snapshot."""
    ticker = ticker.upper()
    if side not in ("buy", "sell"):
        raise TradeError(f"Invalid side: {side}")
    if quantity <= 0:
        raise TradeError("Quantity must be positive")
    price = cache.get_price(ticker)
    if price is None:
        raise TradeError(f"No price available for {ticker}")

    if side == "buy":
        _buy(ticker, quantity, price)
    else:
        _sell(ticker, quantity, price)

    trade = db.insert_trade(ticker, side, quantity, price)
    db.insert_snapshot(get_portfolio(cache)["total_value"])
    return trade


def _buy(ticker: str, quantity: float, price: float) -> None:
    """Deduct cash and grow the position with a weighted average cost."""
    cash = db.get_cash()
    cost = quantity * price
    if cost > cash + DUST:
        raise TradeError(f"Insufficient cash: need ${cost:.2f}, have ${cash:.2f}")
    position = db.get_position(ticker)
    old_qty = position["quantity"] if position else 0.0
    old_cost = position["avg_cost"] if position else 0.0
    new_qty = old_qty + quantity
    avg_cost = (old_qty * old_cost + quantity * price) / new_qty
    db.set_cash(cash - cost)
    db.upsert_position(ticker, new_qty, avg_cost)


def _sell(ticker: str, quantity: float, price: float) -> None:
    """Add cash and shrink the position, deleting it when it reaches zero."""
    position = db.get_position(ticker)
    owned = position["quantity"] if position else 0.0
    if quantity > owned + DUST:
        raise TradeError(f"Insufficient shares: trying to sell {quantity}, own {owned}")
    remaining = owned - quantity
    db.set_cash(db.get_cash() + quantity * price)
    if remaining <= DUST:
        db.delete_position(ticker)
    else:
        db.upsert_position(ticker, remaining, position["avg_cost"])


def get_portfolio(cache: PriceCache) -> dict:
    """Value cash and positions at current prices (avg cost if unpriced)."""
    positions = [_value_position(p, cache) for p in db.get_positions()]
    cash = db.get_cash()
    market_value = sum(p["market_value"] for p in positions)
    return {
        "cash_balance": round(cash, 2),
        "total_value": round(cash + market_value, 2),
        "unrealized_pnl": round(sum(p["unrealized_pnl"] for p in positions), 2),
        "positions": positions,
    }


def _value_position(position: dict, cache: PriceCache) -> dict:
    """Compute market value and unrealized P&L for one position."""
    qty = position["quantity"]
    avg_cost = position["avg_cost"]
    price = cache.get_price(position["ticker"]) or avg_cost
    pnl = (price - avg_cost) * qty
    return {
        "ticker": position["ticker"],
        "quantity": qty,
        "avg_cost": round(avg_cost, 4),
        "current_price": price,
        "market_value": round(price * qty, 2),
        "unrealized_pnl": round(pnl, 2),
        "pnl_percent": round((price - avg_cost) / avg_cost * 100, 2) if avg_cost else 0.0,
    }
