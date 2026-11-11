"""Watchlist persistence."""

from __future__ import annotations

import re
import sqlite3

from app.db.database import DEFAULT_USER, new_id, now_iso

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class WatchlistError(ValueError):
    """Raised for invalid watchlist operations."""


def normalize_ticker(ticker: str) -> str:
    """Uppercase and validate a ticker symbol."""
    ticker = ticker.upper().strip()
    if not TICKER_PATTERN.match(ticker):
        raise WatchlistError(f"Invalid ticker symbol '{ticker}'")
    return ticker


def get_tickers(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> list[str]:
    """Watched tickers in the order they were added."""
    rows = conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY added_at, ticker", (user_id,)
    ).fetchall()
    return [row["ticker"] for row in rows]


def add_ticker(conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER) -> bool:
    """Add a ticker; returns False if it was already present."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (new_id(), user_id, ticker, now_iso()),
    )
    return cursor.rowcount == 1


def remove_ticker(conn: sqlite3.Connection, ticker: str, user_id: str = DEFAULT_USER) -> bool:
    """Remove a ticker; returns False if it was not present."""
    cursor = conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    )
    return cursor.rowcount == 1
