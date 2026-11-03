"""SQLite connection helper and lazy initialization."""

import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

USER_ID = "default"
DEFAULT_CASH = 10000.0
DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def db_path() -> Path:
    """Return the database path from env DB_PATH, defaulting to <project root>/db/finally.db."""
    return Path(os.environ.get("DB_PATH", PROJECT_ROOT / "db" / "finally.db"))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Yield a connection with dict-like rows; commit on success, always close."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    """New UUID string for primary keys."""
    return str(uuid.uuid4())


def init_db() -> None:
    """Create tables if missing and seed the default user and watchlist. Idempotent."""
    with connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        if conn.execute("SELECT 1 FROM users_profile WHERE id = ?", (USER_ID,)).fetchone():
            return
        ts = now_iso()
        conn.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (USER_ID, DEFAULT_CASH, ts),
        )
        conn.executemany(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            [(new_id(), USER_ID, t, ts) for t in DEFAULT_TICKERS],
        )
