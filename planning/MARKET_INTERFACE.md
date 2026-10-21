# Market Data Interface

The unified Python API that the FinAlly backend uses to get stock prices. The backend picks one of two sources at startup:

- `MASSIVE_API_KEY` set and non-empty → `MassiveSource` (REST polling, see MASSIVE_API.md)
- otherwise → `SimulatorSource` (GBM simulator, see MARKET_SIMULATOR.md)

Downstream code (SSE, trades, watchlist, portfolio, LLM context) only ever reads the **`PriceCache`** and calls the **`MarketDataSource`** methods. It never knows which source is running.

## 1. Module Layout

```
backend/app/market/
├── __init__.py        # re-exports PriceCache, PriceEntry, MarketDataSource, UnknownTickerError, create_market_source
├── cache.py           # PriceEntry, PriceCache
├── source.py          # MarketDataSource (abstract base), UnknownTickerError
├── factory.py         # create_market_source()
├── massive.py         # MassiveSource
├── simulator.py       # SimulatorSource
└── seeds.py           # seed prices and volatilities for the simulator
```

## 2. Data Flow

```
            ┌──────────────────────┐
            │ MarketDataSource     │   one background asyncio task
            │ (Simulator|Massive)  │
            └──────────┬───────────┘
                       │ cache.update(ticker, price, timestamp, reference_price)
                       ▼
            ┌──────────────────────┐
            │ PriceCache           │   in-memory dict[ticker, PriceEntry]
            └──────────┬───────────┘
        ┌──────────────┼───────────────┬───────────────┐
        ▼              ▼               ▼               ▼
  SSE /api/stream  trade execution  GET /api/watchlist  LLM portfolio context
  (every 500ms)    (fill price)     GET /api/portfolio
```

Everything runs on the single asyncio event loop. Writes happen in the loop (Massive's blocking HTTP call runs in a thread, but the cache write happens back on the loop), so the cache needs no lock.

## 3. PriceCache (`cache.py`)

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PriceEntry:
    """Latest price state for one ticker."""

    price: float
    previous_price: float
    reference_price: float
    timestamp: datetime  # UTC, time of the last update

    @property
    def direction(self) -> str:
        """'up', 'down' or 'flat' compared to the previous price."""
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    @property
    def change_percent(self) -> float:
        """Percent change vs. reference_price (daily change)."""
        return round((self.price - self.reference_price) / self.reference_price * 100, 2)

    def to_dict(self) -> dict:
        """SSE payload for this ticker (PLAN.md section 6)."""
        return {
            "price": round(self.price, 2),
            "previous_price": round(self.previous_price, 2),
            "change_percent": self.change_percent,
            "direction": self.direction,
            "timestamp": iso_utc(self.timestamp),
        }


def iso_utc(ts: datetime) -> str:
    """Format as ISO 8601 UTC with milliseconds, e.g. 2026-10-14T13:30:00.500Z."""
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


class PriceCache:
    """In-memory latest prices, written by one market data source."""

    def __init__(self) -> None:
        self._entries: dict[str, PriceEntry] = {}

    def update(
        self, ticker: str, price: float, timestamp: datetime, reference_price: float | None = None
    ) -> None:
        """Record a new price; the old price becomes previous_price."""
        old = self._entries.get(ticker)
        self._entries[ticker] = PriceEntry(
            price=price,
            previous_price=old.price if old else price,
            reference_price=reference_price or (old.reference_price if old else price),
            timestamp=timestamp,
        )

    def get(self, ticker: str) -> PriceEntry | None:
        return self._entries.get(ticker)

    def remove(self, ticker: str) -> None:
        self._entries.pop(ticker, None)

    def snapshot(self) -> dict[str, PriceEntry]:
        """Copy of all entries, safe to iterate while the source keeps writing."""
        return dict(self._entries)
```

Rules:

- `reference_price` is set once, on the first update: the seed price (simulator) or `prevDay.c` (Massive). A later update may pass a new one (Massive after a new trading day starts).
- An entry is created on the first `update` only, so `get()` returning `None` means "no price yet" (the API returns `null` for price and the trade fails with `No price for XYZ`).

## 4. MarketDataSource (`source.py`)

```python
from abc import ABC, abstractmethod
from collections.abc import Iterable


class UnknownTickerError(Exception):
    """The data source has no data for this ticker."""


class MarketDataSource(ABC):
    """Produces prices for a set of tracked tickers and writes them to a PriceCache."""

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache
        self.tickers: set[str] = set()

    @abstractmethod
    async def start(self, tickers: Iterable[str]) -> None:
        """Seed the cache for `tickers` and start the background update task."""

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background task."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Start tracking `ticker` and put a first price in the cache before returning.

        Does nothing if the ticker is already tracked.
        Raises UnknownTickerError if the source has no data for it.
        """

    async def remove_ticker(self, ticker: str) -> None:
        """Stop tracking `ticker` and drop it from the cache."""
        self.tickers.discard(ticker)
        self.cache.remove(ticker)
```

Contract:

| Method | Simulator | Massive |
|---|---|---|
| `start(tickers)` | seed prices, start 500ms tick loop | one snapshot poll, then poll every 15s |
| `add_ticker(t)` | known seed or random $50-$300, always succeeds | one-off snapshot for `t`; empty result → `UnknownTickerError` |
| `remove_ticker(t)` | shared default | shared default |
| `stop()` | cancel task | cancel task |

`add_ticker` puts a price in the cache **before returning**, so `POST /api/watchlist` can answer 201 with a price, and the LLM can add a ticker and trade it in the same response.

What the source does **not** do (it stays simple; the API layer owns these):

- Ticker format validation (`^[A-Z][A-Z.]{0,9}$`, uppercasing) → in the route, before calling `add_ticker`
- The "watchlist ∪ positions" rule → the route only calls `remove_ticker` when the ticker is not held, and a sell that closes a position calls `remove_ticker` when the ticker is not on the watchlist
- Persistence → the source is in-memory; tickers come from the database at startup

## 5. Factory (`factory.py`)

```python
import os


def create_market_source(cache: PriceCache) -> MarketDataSource:
    """Massive if MASSIVE_API_KEY is set and non-empty, otherwise the simulator."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveSource(cache, api_key)
    return SimulatorSource(cache)
```

## 6. MassiveSource (`massive.py`)

Polls the multi-ticker snapshot (`GET /v2/snapshot/locale/us/markets/stocks/tickers`) with **one request per poll** for all tracked tickers.

```python
import asyncio
import logging
import time
from datetime import UTC, datetime

from massive import RESTClient

logger = logging.getLogger(__name__)


def snapshot_price(s) -> float | None:
    """Best available price: last trade, then today's bar, then previous close."""
    if s.last_trade and s.last_trade.price:
        return s.last_trade.price
    if s.day and s.day.close:
        return s.day.close
    if s.prev_day and s.prev_day.close:
        return s.prev_day.close
    return None


class MassiveSource(MarketDataSource):
    """Market data from the Massive REST snapshot endpoint."""

    def __init__(self, cache: PriceCache, api_key: str, poll_interval: float = 15.0) -> None:
        super().__init__(cache)
        self._client = RESTClient(api_key=api_key)
        self._poll_interval = poll_interval
        self._task: asyncio.Task | None = None

    async def start(self, tickers) -> None:
        self.tickers = set(tickers)
        await self._poll()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self.tickers:
            return
        snaps = await self._fetch([ticker])
        if not snaps or snapshot_price(snaps[0]) is None:
            raise UnknownTickerError(ticker)
        self._apply(snaps[0])
        self.tickers.add(ticker)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            await self._poll()

    async def _poll(self) -> None:
        """Fetch all tracked tickers; a failed poll is logged and retried next interval."""
        if not self.tickers:
            return
        try:
            snaps = await self._fetch(sorted(self.tickers))
        except Exception:
            logger.exception("Massive snapshot poll failed")
            return
        for s in snaps:
            if s.ticker in self.tickers:
                self._apply(s)

    async def _fetch(self, tickers: list[str]) -> list:
        return await asyncio.to_thread(self._client.get_snapshot_all, "stocks", tickers=tickers)

    def _apply(self, s) -> None:
        """Write one snapshot to the cache, skipping it if nothing changed since the last poll."""
        price = snapshot_price(s)
        if price is None:
            return
        ts = datetime.fromtimestamp((s.updated or time.time_ns()) / 1e9, UTC)
        old = self.cache.get(s.ticker)
        if old and old.timestamp == ts:
            return
        reference = s.prev_day.close if s.prev_day else None
        self.cache.update(s.ticker, price, ts, reference_price=reference)
```

Notes:

- **Skip unchanged snapshots.** If `updated` hasn't moved, the cache entry is left alone. Otherwise `previous_price` would be overwritten with the same price and `direction` would turn `flat` every 15s.
- `updated` is in **nanoseconds** (see MASSIVE_API.md, Section 4).
- `except Exception` in `_poll` is deliberate: the background loop must not die on a network error or a 429. It is the one broad catch in the module.
- Massive tickers are case-sensitive and uppercase, which matches FinAlly's normalisation.
- `poll_interval=15.0` suits the free 5 calls/min limit; paid plans can lower it (2-15s).

### Plan requirements

The snapshot endpoint is **not included in the free Stocks Basic plan** (Starter or higher is required). With a Basic key every poll fails with 403 and no prices ever arrive. The behaviour stays simple and visible: `_poll` logs the error on every poll:

```
Massive snapshot poll failed ... NOT_AUTHORIZED
```

Users with a free key should leave `MASSIVE_API_KEY` empty and use the simulator. Supporting Basic would need a separate end-of-day source built on `get_grouped_daily_aggs` (prices that change once per day). That is out of scope.

## 7. SimulatorSource (summary)

Full design is in MARKET_SIMULATOR.md. Interface behaviour:

- `start(tickers)` seeds each ticker's price (known seed or random $50-$300), writes it to the cache with `reference_price = seed`, and starts a loop that steps all tickers with GBM every 500ms.
- `add_ticker` seeds the new ticker the same way and writes its first price right away.
- It never raises `UnknownTickerError`.

## 8. Wiring into FastAPI

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.market import PriceCache, create_market_source


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()
    source = create_market_source(cache)
    await source.start(load_tracked_tickers())   # watchlist ∪ positions, from SQLite
    app.state.prices = cache
    app.state.market = source
    yield
    await source.stop()


app = FastAPI(lifespan=lifespan)
```

### SSE endpoint

```python
import asyncio
import json

from fastapi import Request
from fastapi.responses import StreamingResponse


@app.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    """Push the full snapshot of all tracked tickers every 500ms."""
    cache: PriceCache = request.app.state.prices

    async def events():
        while not await request.is_disconnected():
            payload = {t: e.to_dict() for t, e in cache.snapshot().items()}
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")
```

### Watchlist add / remove

```python
@app.post("/api/watchlist", status_code=201)
async def add_to_watchlist(body: AddTicker, request: Request):
    ticker = normalize_ticker(body.ticker)          # uppercase + regex, 400 on failure
    try:
        await request.app.state.market.add_ticker(ticker)
    except UnknownTickerError:
        raise HTTPException(400, "Unknown ticker")
    ...  # insert into watchlist table, return {ticker, price, change_percent}


@app.delete("/api/watchlist/{ticker}", status_code=204)
async def remove_from_watchlist(ticker: str, request: Request):
    ...  # delete from watchlist table (404 if missing)
    if not holds_position(ticker):
        await request.app.state.market.remove_ticker(ticker)
```

### Trade fill price

```python
entry = request.app.state.prices.get(ticker)
if entry is None:
    raise HTTPException(400, f"No price for {ticker}; add it to the watchlist first")
fill_price = entry.price
```

## 9. Tests (`backend/tests/market/`)

- `PriceCache`: first update sets `previous_price == price == reference_price`; second update moves `previous_price`; `direction` and `change_percent` math; `iso_utc` format ends in `Z` with milliseconds.
- `create_market_source`: returns `SimulatorSource` for a missing or blank key, `MassiveSource` for a set key (`monkeypatch.setenv`).
- `MassiveSource`: replace `_client` with a fake whose `get_snapshot_all` returns `TickerSnapshot.from_dict(...)` built from the JSON sample in MASSIVE_API.md. Check price selection order, the nanosecond timestamp conversion, the skip on unchanged `updated`, `UnknownTickerError` on an empty result, and that a raising client doesn't stop `_poll`.
- Both sources: after `start` and `add_ticker`, `cache.get(t)` is not `None` (interface conformance test, parametrized over both classes).
