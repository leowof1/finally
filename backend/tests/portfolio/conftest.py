"""Fixtures for portfolio tests: a fresh database and a price cache."""

import pytest

from app.db.database import connect, init_db
from app.market import PriceCache


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    init_db()
    connection = connect()
    yield connection
    connection.close()


@pytest.fixture
def cache():
    price_cache = PriceCache()
    price_cache.update("AAPL", 100.0)
    price_cache.update("TSLA", 200.0)
    return price_cache
