import random

import pytest

from app.market.cache import PriceCache
from app.market.factory import create_market_source
from app.market.massive import MassiveSource
from app.market.simulator import GBMModel, SimulatorSource

from .test_massive import AAPL, FakeMassive, make_source


def simulator():
    cache = PriceCache()
    return SimulatorSource(cache, GBMModel(random.Random(0))), cache


def massive():
    items = [AAPL, {**AAPL, "ticker": "PYPL", "lastTrade": {"p": 61.2, "t": 5}}]
    return make_source(FakeMassive(items))


@pytest.mark.parametrize("factory", [simulator, massive], ids=["simulator", "massive"])
async def test_interface(factory):
    src, cache = factory()
    await src.start(["AAPL"])
    assert cache.get("AAPL") is not None
    await src.add_ticker("PYPL")
    assert cache.get("PYPL") is not None
    await src.add_ticker("PYPL")  # idempotent
    await src.remove_ticker("PYPL")
    assert cache.get("PYPL") is None and src.tickers == {"AAPL"}
    await src.stop()


@pytest.mark.parametrize("factory", [simulator, massive], ids=["simulator", "massive"])
async def test_tickers_is_read_only(factory):
    src, _ = factory()
    await src.start(["AAPL"])
    assert isinstance(src.tickers, frozenset)
    assert not hasattr(src.tickers, "add")
    copy = set(src.tickers)
    copy.add("MSFT")
    assert src.tickers == {"AAPL"}
    await src.stop()


@pytest.mark.parametrize("factory", [simulator, massive], ids=["simulator", "massive"])
async def test_start_twice_raises(factory):
    src, _ = factory()
    await src.start(["AAPL"])
    with pytest.raises(RuntimeError):
        await src.start(["AAPL"])
    await src.stop()
    await src.stop()  # safe to call twice


@pytest.mark.parametrize("value", [None, "", "   "])
def test_factory_simulator(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("MASSIVE_API_KEY", value)
    assert isinstance(create_market_source(PriceCache()), SimulatorSource)


def test_factory_massive(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "k")
    monkeypatch.setenv("MASSIVE_POLL_SECONDS", "5")
    src = create_market_source(PriceCache())
    assert isinstance(src, MassiveSource) and src.poll_interval == 5.0


def test_factory_massive_default_interval(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "k")
    monkeypatch.setenv("MASSIVE_POLL_SECONDS", "")
    assert create_market_source(PriceCache()).poll_interval == 15.0


@pytest.mark.parametrize(
    "value,expected",
    [("abc", 15.0), ("15s", 15.0), ("0", 1.0), ("-5", 1.0), ("0.2", 1.0), ("nan", 1.0), (" 2.5 ", 2.5)],
)
def test_factory_poll_interval_is_validated(monkeypatch, caplog, value, expected):
    monkeypatch.setenv("MASSIVE_API_KEY", "k")
    monkeypatch.setenv("MASSIVE_POLL_SECONDS", value)
    assert create_market_source(PriceCache()).poll_interval == expected
    if expected != 2.5:
        assert "MASSIVE_POLL_SECONDS" in caplog.text
