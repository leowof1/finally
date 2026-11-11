"""Trade execution, portfolio valuation and value snapshots."""

from __future__ import annotations

import sqlite3

from app.db.database import DEFAULT_USER, new_id, now_iso
from app.market import PriceCache

EPSILON = 1e-9


class TradeError(ValueError):
    """Raised when a trade fails validation."""


def get_cash(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> float:
    """Current cash balance."""
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    return row["cash_balance"]


def get_positions(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> list[sqlite3.Row]:
    """All open positions ordered by ticker."""
    return conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()


def held_tickers(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> set[str]:
    """Tickers with an open position."""
    return {row["ticker"] for row in get_positions(conn, user_id)}


def execute_trade(
    conn: sqlite3.Connection,
    cache: PriceCache,
    ticker: str,
    side: str,
    quantity: float,
    user_id: str = DEFAULT_USER,
) -> dict:
    """Validate and execute a market order at the current cached price."""
    ticker = ticker.upper().strip()
    if side not in ("buy", "sell"):
        raise TradeError(f"Invalid side '{side}'; must be 'buy' or 'sell'")
    if quantity <= 0:
        raise TradeError("Quantity must be greater than zero")
    price = cache.get_price(ticker)
    if price is None:
        raise TradeError(f"No price available for {ticker}; add it to the watchlist first")

    cash = get_cash(conn, user_id)
    position = conn.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()
    held = position["quantity"] if position else 0.0
    cost = price * quantity

    if side == "buy":
        if cost > cash + EPSILON:
            raise TradeError(
                f"Insufficient cash: buying {quantity:g} {ticker} costs ${cost:,.2f}, "
                f"available ${cash:,.2f}"
            )
        new_qty = held + quantity
        avg_cost = ((position["avg_cost"] * held if position else 0.0) + cost) / new_qty
        _set_cash(conn, user_id, cash - cost)
        _upsert_position(conn, user_id, ticker, new_qty, avg_cost)
    else:
        if quantity > held + EPSILON:
            raise TradeError(f"Insufficient shares: trying to sell {quantity:g} {ticker}, own {held:g}")
        _set_cash(conn, user_id, cash + cost)
        remaining = held - quantity
        if remaining <= EPSILON:
            conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker))
        else:
            _upsert_position(conn, user_id, ticker, remaining, position["avg_cost"])

    trade = {
        "id": new_id(),
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": now_iso(),
    }
    conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (trade["id"], user_id, ticker, side, quantity, price, trade["executed_at"]),
    )
    record_snapshot(conn, cache, user_id)
    return trade


def get_portfolio(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> dict:
    """Cash, positions with live P&L, and total value."""
    cash = get_cash(conn, user_id)
    positions = []
    for row in get_positions(conn, user_id):
        price = cache.get_price(row["ticker"]) or row["avg_cost"]
        cost_basis = row["avg_cost"] * row["quantity"]
        market_value = price * row["quantity"]
        pnl = market_value - cost_basis
        positions.append(
            {
                "ticker": row["ticker"],
                "quantity": row["quantity"],
                "avg_cost": round(row["avg_cost"], 4),
                "current_price": price,
                "market_value": round(market_value, 2),
                "unrealized_pnl": round(pnl, 2),
                "pnl_percent": round(pnl / cost_basis * 100, 2) if cost_basis else 0.0,
            }
        )
    positions_value = sum(p["market_value"] for p in positions)
    return {
        "cash_balance": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(cash + positions_value, 2),
        "unrealized_pnl": round(sum(p["unrealized_pnl"] for p in positions), 2),
        "positions": positions,
    }


def record_snapshot(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> None:
    """Store the current total portfolio value."""
    total = get_portfolio(conn, cache, user_id)["total_value"]
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (new_id(), user_id, total, now_iso()),
    )


def get_history(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> list[dict]:
    """All portfolio value snapshots, oldest first."""
    rows = conn.execute(
        "SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ? "
        "ORDER BY recorded_at",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _set_cash(conn: sqlite3.Connection, user_id: str, cash: float) -> None:
    conn.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (cash, user_id))


def _upsert_position(
    conn: sqlite3.Connection, user_id: str, ticker: str, quantity: float, avg_cost: float
) -> None:
    conn.execute(
        "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (user_id, ticker) DO UPDATE SET "
        "quantity = excluded.quantity, avg_cost = excluded.avg_cost, updated_at = excluded.updated_at",
        (new_id(), user_id, ticker, quantity, avg_cost, now_iso()),
    )
