import asyncio
import math
import random
import statistics

import pytest

from app.market.cache import PriceCache
from app.market.simulator import DT, GBMModel, SimulatorSource


def plain(seed=42, **kw):
    """Independent GBM, no events."""
    return GBMModel(random.Random(seed), market_weight=0, sector_weight=0, event_probability=0, **kw)


def log_returns(model, ticker_a, ticker_b, n):
    a, b = [], []
    pa, pb = model.states[ticker_a].price, model.states[ticker_b].price
    for _ in range(n):
        prices = model.step()
        a.append(math.log(prices[ticker_a] / pa))
        b.append(math.log(prices[ticker_b] / pb))
        pa, pb = prices[ticker_a], prices[ticker_b]
    return a, b


def test_add_known_unknown_and_twice():
    m = plain()
    assert m.add("AAPL") == 190.0
    p = m.add("PYPL")
    assert 50 <= p <= 300
    assert m.add("PYPL") == p


def test_step_moves_every_price_and_stays_positive():
    m = plain()
    for t in ("AAPL", "TSLA", "ZZZ"):
        m.add(t)
    before = {t: s.price for t, s in m.states.items()}
    after = m.step()
    assert set(after) == set(before)
    assert all(after[t] > 0 and after[t] != before[t] for t in after)


def test_remove_stops_simulating():
    m = plain()
    m.add("AAPL")
    m.remove("AAPL")
    m.remove("AAPL")
    assert m.step() == {}


def test_realised_volatility_matches_sigma():
    m = plain()
    m.add("AAPL")
    r, _ = log_returns(m, "AAPL", "AAPL", 100_000)
    annual = statistics.stdev(r) / math.sqrt(DT)
    assert annual == pytest.approx(0.25, rel=0.05)


def test_same_seed_same_path():
    a, b = plain(7), plain(7)
    for m in (a, b):
        m.add("AAPL")
        m.add("NEW")
    assert [a.step() for _ in range(50)] == [b.step() for _ in range(50)]


def test_correlation_same_and_cross_sector():
    m = GBMModel(random.Random(1), event_probability=0)
    for t in ("AAPL", "MSFT", "JPM"):
        m.add(t)
    tech_a, tech_b = log_returns(m, "AAPL", "MSFT", 50_000)
    m2 = GBMModel(random.Random(2), event_probability=0)
    for t in ("AAPL", "JPM"):
        m2.add(t)
    x_a, x_b = log_returns(m2, "AAPL", "JPM", 50_000)
    assert statistics.correlation(tech_a, tech_b) == pytest.approx(0.6, abs=0.05)
    assert statistics.correlation(x_a, x_b) == pytest.approx(0.3, abs=0.05)


def test_events_jump_two_to_five_percent():
    m = GBMModel(random.Random(3), event_probability=1.0, dt=0.0)
    m.add("AAPL")
    for _ in range(100):
        before = m.states["AAPL"].price
        after = m.step()["AAPL"]
        assert 0.02 <= abs(after / before - 1) <= 0.05 + 1e-12


def test_invalid_weights():
    with pytest.raises(ValueError):
        GBMModel(market_weight=0.7, sector_weight=0.5)
    with pytest.raises(ValueError):
        GBMModel(market_weight=-0.1)


async def test_source_start_tick_add_remove():
    cache = PriceCache()
    src = SimulatorSource(cache, plain())
    await src.start(["AAPL", "MSFT"])
    try:
        e = cache.get("AAPL")
        assert e.price == e.previous_price == e.reference_price == 190.0
        first_ts = e.timestamp
        src.tick()
        e = cache.get("AAPL")
        assert e.previous_price == 190.0 and e.price != 190.0
        assert e.reference_price == 190.0 and e.timestamp >= first_ts

        await src.add_ticker("PYPL")
        assert cache.get("PYPL") is not None and "PYPL" in src.tickers

        await src.remove_ticker("PYPL")
        assert cache.get("PYPL") is None and "PYPL" not in src.model.states
    finally:
        await src.stop()
        await src.stop()  # idempotent


async def test_background_loop_ticks():
    cache = PriceCache()
    src = SimulatorSource(cache, plain(), tick_seconds=0.01)
    await src.start(["AAPL"])
    await asyncio.sleep(0.05)
    await src.stop()
    assert cache.get("AAPL").price != 190.0


async def test_loop_survives_tick_error(monkeypatch):
    src = SimulatorSource(PriceCache(), plain(), tick_seconds=0.01)
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("boom")

    monkeypatch.setattr(src, "tick", boom)
    await src.start([])
    await asyncio.sleep(0.05)
    await src.stop()
    assert len(calls) >= 2
