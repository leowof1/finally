import json
from datetime import UTC, datetime

from fastapi import FastAPI

from app.api.stream import price_events, router
from app.market.cache import PriceCache

TS = datetime(2026, 10, 14, 13, 30, tzinfo=UTC)


async def test_price_events_yields_full_snapshot_until_disconnect():
    cache = PriceCache()
    cache.update("MSFT", 420.0, TS)
    cache.update("AAPL", 190.0, TS)
    checks = iter([False, False, True])

    async def is_disconnected():
        return next(checks)

    events = [e async for e in price_events(cache, is_disconnected, interval=0)]
    assert events[0] == "retry: 1000\n\n"
    assert len(events) == 3
    payload = json.loads(events[1].removeprefix("data: "))
    assert list(payload) == ["AAPL", "MSFT"]
    assert payload["AAPL"]["timestamp"] == "2026-10-14T13:30:00.000Z"
    assert set(payload["AAPL"]) == {
        "price", "previous_price", "change_percent", "direction", "timestamp"
    }


async def test_price_events_empty_cache_sends_empty_object():
    async def gone():
        return False

    gen = price_events(PriceCache(), gone, interval=0)
    assert await gen.__anext__() == "retry: 1000\n\n"
    assert await gen.__anext__() == "data: {}\n\n"
    await gen.aclose()


def test_route_is_registered_on_contract_path():
    app = FastAPI()
    app.include_router(router)
    route = next(r for r in app.routes if getattr(r, "path", "") == "/api/stream/prices")
    assert "GET" in route.methods
