"""SQLite connection handling with lazy schema creation and seeding."""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.market.seed_prices import SEED_PRICES

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "db" / "finally.db"
DEFAULT_USER = "default"
DEFAULT_CASH = 10000.0
DEFAULT_TICKERS = list(SEED_PRICES.keys())


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    """Random UUID string for primary keys."""
    return str(uuid.uuid4())


def db_path() -> Path:
    """Database file location, overridable with the DB_PATH env var."""
    return Path(os.environ.get("DB_PATH", DEFAULT_DB_PATH))


def connect() -> sqlite3.Connection:
    """Open a connection with dict-like rows."""
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Connection that commits on success, rolls back on error, and always closes."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if missing and seed default data on a fresh database."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with transaction() as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        if conn.execute("SELECT 1 FROM users_profile WHERE id = ?", (DEFAULT_USER,)).fetchone():
            return
        conn.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER, DEFAULT_CASH, now_iso()),
        )
        conn.executemany(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            [(new_id(), DEFAULT_USER, t, now_iso()) for t in DEFAULT_TICKERS],
        )
