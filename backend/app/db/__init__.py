"""SQLite persistence layer for FinAlly."""

from app.db.connection import DEFAULT_TICKERS, connect, db_path, init_db
from app.db.repository import (
    add_watchlist,
    delete_position,
    get_cash,
    get_chat_messages,
    get_position,
    get_positions,
    get_snapshots,
    get_trades,
    get_watchlist,
    insert_chat_message,
    insert_snapshot,
    insert_trade,
    remove_watchlist,
    set_cash,
    upsert_position,
)

__all__ = [
    "DEFAULT_TICKERS",
    "add_watchlist",
    "connect",
    "db_path",
    "delete_position",
    "get_cash",
    "get_chat_messages",
    "get_position",
    "get_positions",
    "get_snapshots",
    "get_trades",
    "get_watchlist",
    "init_db",
    "insert_chat_message",
    "insert_snapshot",
    "insert_trade",
    "remove_watchlist",
    "set_cash",
    "upsert_position",
]
