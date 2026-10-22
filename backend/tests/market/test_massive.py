from datetime import UTC, datetime

import httpx
import pytest

from app.market.cache import PriceCache
from app.market.massive import (
    SNAPSHOT_PATH,
    MassiveSource,
    ns_to_datetime,
    parse_snapshot,
)
from app.market.source import MarketDataUnavailableError, UnknownTickerError

AAPL = {
    "ticker": "AAPL",
    "todaysChange": 1.23,
    "todaysChangePerc": 0.65,
    "updated": 1605192894630916600,
    "day": {"o": 189.1, "h": 191.0, "l": 188.7, "c": 190.5, "v": 41234567, "vw": 190.02},
    "prevDay": {"o": 188.0, "h": 189.9, "l": 187.5, "c": 189.27, "v": 52345678, "vw": 188.9},
    "min": {"o": 190.4, "h": 190.6, "l": 190.3, "c": 190.45, "v": 120345, "t": 1684428600000},
    "lastTrade": {"p": 190.52, "s": 100, "t": 1605192894630916600, "x": 4},
}


class FakeMassive:
    """httpx.MockTransport handler serving canned snapshots and recording requests."""

    def __init__(self, items=None, status=200):
        self.items = {i["ticker"]: i for i in (items or [])}
        self.status = status
        self.requests: list[list[str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == SNAPSHOT_PATH
        assert request.headers["Authorization"] == "Bearer test-key"
        assert "test-key" not in str(request.url)
        tickers = request.url.params["tickers"].split(",")
        self.requests.append(tickers)
        if self.status != 200:
            return httpx.Response(self.status, json={"status": "ERROR", "error": "nope"})
        found = [self.items[t] for t in tickers if t in self.items]
        return httpx.Response(200, json={"status": "OK", "count": len(found), "tickers": found})


def make_source(fake: FakeMassive) -> tuple[MassiveSource, PriceCache]:
    cache = PriceCache()
    client = httpx.AsyncClient(
        base_url="https://api.massive.com",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(fake),
    )
    return MassiveSource(cache, "test-key", client=client), cache


def test_ns_to_datetime():
    assert ns_to_datetime(1605192894630916600) == datetime(
        2020, 11, 12, 14, 54, 54, 630916, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "drop,expected",
    [
        ((), 190.52),
        (("lastTrade",), 190.45),
        (("lastTrade", "min"), 190.5),
        (("lastTrade", "min", "day"), 189.27),
    ],
)
def test_price_fallback_order(drop, expected):
    item = {k: v for k, v in AAPL.items() if k not in drop}
    q = parse_snapshot(item)
    assert q.price == expected and q.reference_price == 189.27


def test_zeroed_overnight_bars_fall_back_to_prev_close():
    item = {**AAPL, "lastTrade": None, "min": {"c": 0}, "day": {"c": 0}}
    assert parse_snapshot(item).price == 189.27


def test_no_price_at_all():
    assert parse_snapshot({"ticker": "X", "day": {"c": 0}, "prevDay": {}}) is None


def test_missing_updated_uses_now():
    now = datetime(2026, 10, 14, tzinfo=UTC)
    item = {k: v for k, v in AAPL.items() if k not in ("updated", "lastTrade")}
    assert parse_snapshot(item, now=now).timestamp == now


def test_missing_updated_falls_back_to_last_trade_time():
    item = {k: v for k, v in AAPL.items() if k != "updated"}
    assert parse_snapshot(item).timestamp == ns_to_datetime(AAPL["lastTrade"]["t"])


async def test_start_polls_once_for_all_tickers():
    msft = {**AAPL, "ticker": "MSFT", "lastTrade": {"p": 420.0, "t": 1}}
    fake = FakeMassive([AAPL, msft])
    src, cache = make_source(fake)
    await src.start(["MSFT", "AAPL"])
    await src.stop()
    assert fake.requests == [["AAPL", "MSFT"]]
    assert cache.get("AAPL").price == 190.52
    assert cache.get("AAPL").reference_price == 189.27
    assert cache.get("MSFT").price == 420.0


async def test_start_with_no_tickers_makes_no_request():
    fake = FakeMassive([AAPL])
    src, _ = make_source(fake)
    await src.start([])
    await src.stop()
    assert fake.requests == []


async def test_unchanged_updated_is_skipped():
    fake = FakeMassive([AAPL])
    src, cache = make_source(fake)
    await src.start(["AAPL"])
    first = cache.get("AAPL")
    fake.items["AAPL"] = {**AAPL, "lastTrade": {"p": 999.0}}  # same `updated`
    await src.poll()
    assert cache.get("AAPL") is first
    fake.items["AAPL"] = {
        **AAPL,
        "updated": AAPL["updated"] + 15 * 10**9,
        "lastTrade": {"p": 191.0},
    }
    await src.poll()
    e = cache.get("AAPL")
    assert (e.previous_price, e.price, e.direction) == (190.52, 191.0, "up")
    await src.stop()


async def test_add_ticker_known_unknown_and_unavailable():
    src, cache = make_source(FakeMassive([AAPL]))
    await src.add_ticker("AAPL")
    assert cache.get("AAPL").price == 190.52 and "AAPL" in src.tickers
    with pytest.raises(UnknownTickerError):
        await src.add_ticker("NOPE")
    assert "NOPE" not in src.tickers
    await src.stop()

    down, _ = make_source(FakeMassive(status=503))
    with pytest.raises(MarketDataUnavailableError):
        await down.add_ticker("AAPL")
    await down.stop()


async def test_add_ticker_refetches_when_tracked_but_unpriced():
    fake = FakeMassive(status=503)
    src, cache = make_source(fake)
    await src.start(["AAPL"])  # poll fails, ticker tracked without a price
    assert cache.get("AAPL") is None
    fake.status = 200
    fake.items = {"AAPL": AAPL}
    await src.add_ticker("AAPL")
    assert cache.get("AAPL").price == 190.52
    await src.stop()


@pytest.mark.parametrize("status,hint", [(401, "invalid"), (403, "Starter or higher"), (429, "rate limit")])
async def test_failed_poll_is_logged_and_survives(caplog, status, hint):
    src, cache = make_source(FakeMassive(status=status))
    await src.start(["AAPL"])  # must not raise
    assert cache.get("AAPL") is None
    assert hint in caplog.text
    assert "test-key" not in caplog.text
    await src.stop()


async def test_removed_ticker_is_not_rewritten():
    src, cache = make_source(FakeMassive([AAPL]))
    await src.start(["AAPL"])
    await src.remove_ticker("AAPL")
    await src.poll()
    assert cache.get("AAPL") is None
    await src.stop()


async def test_stop_is_idempotent_for_task():
    src, _ = make_source(FakeMassive([AAPL]))
    await src.start(["AAPL"])
    assert src._task is not None
    await src.stop()
    assert src._task is None
