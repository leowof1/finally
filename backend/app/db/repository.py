"""Repository functions for the single default user."""

import json

from app.db.connection import USER_ID, connect, new_id, now_iso


def get_cash() -> float:
    """Return the user's cash balance."""
    with connect() as conn:
        row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,))
        return row.fetchone()["cash_balance"]


def set_cash(amount: float) -> None:
    """Set the user's cash balance."""
    with connect() as conn:
        conn.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (amount, USER_ID))


def get_watchlist() -> list[dict]:
    """Return watchlist entries (ticker, added_at), oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
            (USER_ID,),
        )
        return [dict(r) for r in rows]


def add_watchlist(ticker: str) -> dict | None:
    """Add a ticker; return {ticker, added_at}, or None if already present."""
    added_at = now_iso()
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (new_id(), USER_ID, ticker, added_at),
        )
        return {"ticker": ticker, "added_at": added_at} if cur.rowcount else None


def remove_watchlist(ticker: str) -> bool:
    """Remove a ticker; return True if it was present."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (USER_ID, ticker)
        )
        return cur.rowcount > 0


POSITION_COLUMNS = "ticker, quantity, avg_cost, updated_at"


def get_positions() -> list[dict]:
    """Return all positions ordered by ticker."""
    with connect() as conn:
        rows = conn.execute(
            f"SELECT {POSITION_COLUMNS} FROM positions WHERE user_id = ? ORDER BY ticker",
            (USER_ID,),
        )
        return [dict(r) for r in rows]


def get_position(ticker: str) -> dict | None:
    """Return one position or None."""
    with connect() as conn:
        row = conn.execute(
            f"SELECT {POSITION_COLUMNS} FROM positions WHERE user_id = ? AND ticker = ?",
            (USER_ID, ticker),
        ).fetchone()
        return dict(row) if row else None


def upsert_position(ticker: str, quantity: float, avg_cost: float) -> None:
    """Insert or replace the quantity and average cost of a position."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (user_id, ticker) DO UPDATE SET
                 quantity = excluded.quantity,
                 avg_cost = excluded.avg_cost,
                 updated_at = excluded.updated_at""",
            (new_id(), USER_ID, ticker, quantity, avg_cost, now_iso()),
        )


def delete_position(ticker: str) -> None:
    """Delete a position."""
    with connect() as conn:
        conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (USER_ID, ticker))


def insert_trade(ticker: str, side: str, quantity: float, price: float) -> dict:
    """Append a trade and return {ticker, side, quantity, price, executed_at}."""
    trade = {
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": now_iso(),
    }
    with connect() as conn:
        conn.execute(
            """INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
               VALUES (:id, :user_id, :ticker, :side, :quantity, :price, :executed_at)""",
            {"id": new_id(), "user_id": USER_ID, **trade},
        )
    return trade


def get_trades() -> list[dict]:
    """Return all trades, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT ticker, side, quantity, price, executed_at FROM trades
               WHERE user_id = ? ORDER BY executed_at, rowid""",
            (USER_ID,),
        )
        return [dict(r) for r in rows]


def insert_snapshot(total_value: float) -> None:
    """Record a portfolio value snapshot."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
               VALUES (?, ?, ?, ?)""",
            (new_id(), USER_ID, total_value, now_iso()),
        )


def get_snapshots() -> list[dict]:
    """Return snapshots (total_value, recorded_at), oldest first."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT total_value, recorded_at FROM portfolio_snapshots
               WHERE user_id = ? ORDER BY recorded_at, rowid""",
            (USER_ID,),
        )
        return [dict(r) for r in rows]


def insert_chat_message(role: str, content: str, actions: dict | None) -> None:
    """Store a chat message; actions are serialized to JSON."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (new_id(), USER_ID, role, content, json.dumps(actions) if actions else None, now_iso()),
        )


def get_chat_messages(limit: int = 20) -> list[dict]:
    """Return the most recent messages (role, content, actions, created_at), oldest first."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT role, content, actions, created_at FROM chat_messages
               WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?""",
            (USER_ID, limit),
        ).fetchall()
    messages = [dict(r) for r in reversed(rows)]
    for m in messages:
        m["actions"] = json.loads(m["actions"]) if m["actions"] else None
    return messages
