"""Fixtures for LLM tests: temp database, primed price cache, fake market source."""

import pytest

from app.db import init_db
from app.market import PriceCache


class FakeSource:
    """Records tickers added/removed and keeps the cache in sync like the real sources."""

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache
        self.added: list[str] = []
        self.removed: list[str] = []

    async def add_ticker(self, ticker: str) -> None:
        self.added.append(ticker)
        self.cache.update(ticker, 50.0)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)
        self.cache.remove(ticker)


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    """Fresh temp database; mock mode off unless a test enables it."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_MOCK", "false")
    init_db()


@pytest.fixture
def cache() -> PriceCache:
    """Price cache with a few tickers priced."""
    cache = PriceCache()
    cache.update("AAPL", 200.0)
    cache.update("NVDA", 100.0)
    cache.update("TSLA", 250.0)
    return cache


@pytest.fixture
def source(cache) -> FakeSource:
    """Fake market data source bound to the cache."""
    return FakeSource(cache)
