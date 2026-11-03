"""Tests for app.db init and repository functions."""

import app.db as repo


def test_init_creates_file_and_seeds(db):
    assert db.exists()
    assert repo.get_cash() == 10000.0
    assert [w["ticker"] for w in repo.get_watchlist()] == repo.DEFAULT_TICKERS


def test_init_is_idempotent():
    repo.set_cash(500.0)
    repo.init_db()
    assert repo.get_cash() == 500.0
    assert len(repo.get_watchlist()) == 10


def test_set_cash():
    repo.set_cash(1234.5)
    assert repo.get_cash() == 1234.5


def test_add_watchlist():
    entry = repo.add_watchlist("PYPL")
    assert entry["ticker"] == "PYPL"
    assert repo.get_watchlist()[-1] == entry


def test_add_watchlist_duplicate_returns_none():
    assert repo.add_watchlist("AAPL") is None
    assert len(repo.get_watchlist()) == 10


def test_remove_watchlist():
    assert repo.remove_watchlist("AAPL") is True
    assert repo.remove_watchlist("AAPL") is False
    assert "AAPL" not in [w["ticker"] for w in repo.get_watchlist()]


def test_positions_upsert_get_delete():
    assert repo.get_position("AAPL") is None
    repo.upsert_position("AAPL", 10, 190.0)
    repo.upsert_position("AAPL", 15, 192.0)
    pos = repo.get_position("AAPL")
    assert (pos["quantity"], pos["avg_cost"]) == (15, 192.0)
    assert len(repo.get_positions()) == 1
    repo.delete_position("AAPL")
    assert repo.get_positions() == []


def test_positions_fractional_and_sorted():
    repo.upsert_position("MSFT", 0.5, 400.0)
    repo.upsert_position("AAPL", 1.25, 190.0)
    assert [p["ticker"] for p in repo.get_positions()] == ["AAPL", "MSFT"]
    assert repo.get_position("AAPL")["quantity"] == 1.25


def test_trades():
    t1 = repo.insert_trade("AAPL", "buy", 2, 190.0)
    t2 = repo.insert_trade("AAPL", "sell", 1, 195.0)
    assert set(t1) == {"ticker", "side", "quantity", "price", "executed_at"}
    assert repo.get_trades() == [t1, t2]


def test_snapshots_oldest_first():
    repo.insert_snapshot(10000.0)
    repo.insert_snapshot(10050.0)
    snaps = repo.get_snapshots()
    assert [s["total_value"] for s in snaps] == [10000.0, 10050.0]
    assert set(snaps[0]) == {"total_value", "recorded_at"}


def test_chat_messages_roundtrip_actions():
    actions = {"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1}]}
    repo.insert_chat_message("user", "buy AAPL", None)
    repo.insert_chat_message("assistant", "Done", actions)
    msgs = repo.get_chat_messages()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["actions"] is None
    assert msgs[1]["actions"] == actions


def test_chat_messages_limit_returns_latest_oldest_first():
    for i in range(5):
        repo.insert_chat_message("user", f"m{i}", None)
    assert [m["content"] for m in repo.get_chat_messages(limit=3)] == ["m2", "m3", "m4"]


def test_db_path_default(monkeypatch):
    monkeypatch.delenv("DB_PATH")
    path = repo.db_path()
    assert path.parts[-2:] == ("db", "finally.db")
    assert (path.parent.parent / "backend").is_dir()
