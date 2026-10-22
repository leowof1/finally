# Market Data Backend — Detailed Design

The implementation guide for everything market-data related in the FinAlly backend: the unified API (`PriceCache` + `MarketDataSource`), the GBM simulator, the Massive REST poller, the factory, the SSE endpoint, and how routes use them.

It builds on the three reference documents and is the **one to implement from**:

| Document | Role |
|---|---|
| `PLAN.md` §6, §8, §11, §12 | Requirements (the contract) |
| `MARKET_INTERFACE.md` | First design of the unified API |
| `MARKET_SIMULATOR.md` | GBM math, seed table, validation numbers |
| `MASSIVE_API.md` | Massive endpoint, JSON fields, plans, errors |
| **this document** | Final design with complete code. Where it differs from the two design docs above, this document wins (see §2) |

All code below was prototyped as a real uv project and its test suite (§12) passes: **46 tests**, Python 3.13, FastAPI 0.156, httpx 0.28. It was also run under uvicorn and the SSE stream checked with `curl` (sample output in §11.2).

---

## 1. Requirements Checklist

Every market-data requirement in PLAN.md and where it is met:

| Requirement (PLAN.md) | Where |
|---|---|
| Two sources, one interface; downstream code agnostic | §7 `MarketDataSource`, §10 factory |
| `MASSIVE_API_KEY` set and non-empty → Massive, else simulator | §9 |
| Track watchlist ∪ open positions | §11.4 `untrack_if_unused`, §11.1 `load_tracked_tickers` |
| Tickers uppercased, `^[A-Z][A-Z.]{0,9}$`, else 400 | §5 `normalize_ticker` |
| Simulator accepts any valid ticker; unknown → random $50–$300, default vol | §8.4 `GBMModel.add` |
| Massive: one-off snapshot on add; no data → 400 `Unknown ticker` | §9.3 `add_ticker`, §11.3 |
| GBM, ~500ms, realistic seeds, in-process task | §8 |
| Increment 2: correlated moves + 2–5% events | §8.2, §8.4 (constructor weights) |
| Massive: REST polling, **one** multi-ticker snapshot request per poll | §9.3 `poll` / `_fetch` |
| Free tier → 15s poll; paid → 2–15s | §9.3 `DEFAULT_POLL_SECONDS`, §10 `MASSIVE_POLL_SECONDS` |
| Cache holds `price`, `previous_price`, `reference_price`, `timestamp` | §6 `PriceEntry` |
| `reference_price` = seed (simulator) / previous close (Massive) | §8.5, §9.1 |
| SSE `GET /api/stream/prices`, full snapshot every ~500ms, exact payload | §11.2 |
| `direction` up/down/flat vs `previous_price`; `change_percent` vs reference | §6 |
| Massive: unchanged entries resent, `timestamp` only moves on real updates | §9.3 `_apply` |
| ISO 8601 UTC timestamps with `Z` | §6 `iso_utc` |
| Trade fill = cached price; no price → 400 `No price for XYZ; …` | §11.4 |
| Unit tests: GBM math, Massive parsing, interface conformance | §12 |

---

## 2. Design Decisions (and changes vs. the earlier docs)

1. **Massive is called with `httpx.AsyncClient`, not the `massive` SDK.** The SDK is synchronous (needs `asyncio.to_thread`), retries on its own (a slow retry chain can stall a 15s poll loop), and returns model objects that tests must build with `TickerSnapshot.from_dict`. One GET with a Bearer header is all we need. With httpx the poller is natively async, there are no threads at all (so the "no lock needed" argument becomes trivially true), timeouts are explicit, and tests feed the exact JSON from MASSIVE_API.md through `httpx.MockTransport`. `httpx` is one small dependency and is already what FastAPI's `TestClient` uses.
2. **`direction` compares prices rounded to cents**, i.e. what the user sees. A simulator tick moves AAPL ~$0.014, so raw-float comparison would often say `"up"` while the displayed price is unchanged. Rounding keeps colour and number consistent.
3. **`change_percent` never returns `-0.0`** (found when running the prototype: a $0.001 drop rounded to `-0.0`, which renders as "-0.00%"). It also returns `0.0` if `reference_price` is 0.
4. **Massive price fallback adds the minute bar**: `lastTrade.p` → `min.c` → `day.c` → `prevDay.c`. `min.c` is fresher than `day.c` on plans without trades. Zeroed bars (the snapshot is reset at 3:30 AM ET) are treated as missing.
5. **A third error type, `MarketDataUnavailableError`.** "Massive is down / 429 / 403" is not "unknown ticker". Routes map it to **503 `Market data unavailable`** instead of a misleading 400.
6. **`start()` never raises** because the upstream is unreachable. The app still boots with a bad key or no network; prices are simply `null` until a poll succeeds, and the log says why (§9.4).
7. **`GBMModel` takes the increment-2 knobs as constructor arguments** (`market_weight`, `sector_weight`, `event_probability`, `dt`) instead of having two versions of `step()`. Increment 1 is the same class with the knobs at 0, so increment-1 tests keep passing after increment 2 lands.
8. **Per-ticker drift** in the seed table (`TickerSpec.drift`, default 0.05), since PLAN.md asks for "configurable drift and volatility per ticker".
9. **`MassiveSource.add_ticker` refetches a ticker that is tracked but has no price yet** (e.g. the startup poll failed), instead of returning silently with nothing in the cache.
10. **`tickers` is a read-only `frozenset` property**; only the source mutates its internal set.
11. **`stop()` awaits the cancelled task, is idempotent, and closes the HTTP client.**
12. **Optional env var `MASSIVE_POLL_SECONDS`** (default 15) so paid-plan users can poll faster without a code change.
13. **The SSE endpoint is split** into a pure async generator (`price_events`, unit-testable without a server) and a thin route. It sends a `retry: 1000` hint first, sorts tickers for a stable payload, and sets `Cache-Control: no-cache` / `X-Accel-Buffering: no`.

---

## 3. Module Layout and Dependencies

```
backend/
├── pyproject.toml
├── app/
│   ├── main.py                 # FastAPI app + lifespan (§11.1)
│   ├── api/
│   │   ├── stream.py           # GET /api/stream/prices (§11.2)
│   │   ├── watchlist.py        # uses normalize_ticker, add_ticker, untrack_if_unused (§11.3)
│   │   └── portfolio.py        # trade fill price from the cache (§11.4)
│   └── market/
│       ├── __init__.py         # public API re-exports
│       ├── tickers.py          # normalize_ticker, InvalidTickerError
│       ├── cache.py            # PriceEntry, PriceCache, iso_utc
│       ├── source.py           # MarketDataSource (ABC) + error types
│       ├── seeds.py            # TickerSpec, SEEDS, defaults
│       ├── simulator.py        # GBMModel (math) + SimulatorSource (asyncio)
│       ├── massive.py          # parse_snapshot (pure) + MassiveSource (asyncio)
│       └── factory.py          # create_market_source()
└── tests/
    ├── api/test_stream.py
    └── market/
        ├── test_tickers.py
        ├── test_cache.py
        ├── test_simulator.py
        ├── test_massive.py
        └── test_conformance.py
```

Downstream code imports **only from `app.market`** (the `__init__` re-exports). Nothing outside `app/market/` imports `simulator` or `massive` directly.

### `pyproject.toml` (market-data relevant parts)

```toml
[project]
name = "finally-backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "httpx>=0.27",          # Massive REST client (and FastAPI TestClient)
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
pythonpath = ["."]
```

```bash
cd backend
uv add fastapi "uvicorn[standard]" httpx
uv add --dev pytest pytest-asyncio
uv run pytest tests/market tests/api -q
```

### Public API (`app/market/__init__.py`)

```python
"""Market data: one price cache, two interchangeable sources."""

from app.market.cache import PriceCache, PriceEntry, iso_utc
from app.market.factory import create_market_source
from app.market.source import (
    MarketDataError,
    MarketDataSource,
    MarketDataUnavailableError,
    UnknownTickerError,
)
from app.market.tickers import InvalidTickerError, normalize_ticker

__all__ = [
    "InvalidTickerError",
    "MarketDataError",
    "MarketDataSource",
    "MarketDataUnavailableError",
    "PriceCache",
    "PriceEntry",
    "UnknownTickerError",
    "create_market_source",
    "iso_utc",
    "normalize_ticker",
]
```

---

## 4. Data Flow and Concurrency

```
                 ┌───────────────────────────────┐
                 │ MarketDataSource               │  exactly one, chosen at startup
                 │  SimulatorSource: tick 500ms   │  one background asyncio.Task
                 │  MassiveSource:   poll 15s     │
                 └───────────────┬───────────────┘
                                 │ cache.update(ticker, price, timestamp, reference_price)
                                 ▼
                 ┌───────────────────────────────┐
                 │ PriceCache                     │  dict[ticker, PriceEntry] (immutable entries)
                 └───────────────┬───────────────┘
      ┌──────────────────┬───────┴─────────┬────────────────────┬──────────────────┐
      ▼                  ▼                 ▼                    ▼                  ▼
 SSE stream        trade execution   GET /api/watchlist   GET /api/portfolio   LLM context
 every 500ms       fill = .price     price, change_%      current_price        prices + P&L

 Routes ──► source.add_ticker / remove_ticker   (watchlist add/remove, LLM watchlist_changes,
                                                 sell that closes a position)
```

- Everything — the tick/poll task, the SSE generators, the routes — runs on the **single asyncio event loop**. The simulator has no `await` inside `tick()`, and the Massive poller writes to the cache after its `await` returns, so a cache write never interleaves with a read. **No locks.**
- `PriceEntry` is a frozen dataclass and `snapshot()` returns a shallow copy, so a consumer holding a snapshot never sees a half-updated entry.
- The source is purely in-memory. Which tickers to track comes from SQLite at startup (§11.1); after that, routes tell the source about changes.

---

## 5. Ticker Normalisation (`app/market/tickers.py`)

Used by `POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`, `POST /api/portfolio/trade` and the LLM action executor, **before** anything touches the source or the database.

```python
"""Ticker normalisation shared by the REST routes and the LLM action executor."""

import re

TICKER_RE = re.compile(r"^[A-Z][A-Z.]{0,9}$")


class InvalidTickerError(ValueError):
    """The ticker does not match ^[A-Z][A-Z.]{0,9}$ after uppercasing."""


def normalize_ticker(raw: str) -> str:
    """Strip and uppercase `raw`; raise InvalidTickerError if the format is wrong."""
    ticker = raw.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise InvalidTickerError(f"Invalid ticker: {raw!r}")
    return ticker
```

```python
normalize_ticker(" brk.b ")   # "BRK.B"
normalize_ticker("aapl")      # "AAPL"
normalize_ticker("BRK-B")     # InvalidTickerError -> route returns 400
```

---

## 6. Price Cache (`app/market/cache.py`)

```python
"""In-memory cache of the latest price per ticker."""

from dataclasses import dataclass
from datetime import UTC, datetime


def iso_utc(ts: datetime) -> str:
    """Format as ISO 8601 UTC with milliseconds, e.g. 2026-10-14T13:30:00.500Z."""
    ts = ts.astimezone(UTC)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


@dataclass(frozen=True, slots=True)
class PriceEntry:
    """Latest price state for one ticker."""

    price: float
    previous_price: float
    reference_price: float
    timestamp: datetime  # tz-aware UTC, time of the last update

    @property
    def direction(self) -> str:
        """'up', 'down' or 'flat', comparing prices as displayed (rounded to cents)."""
        now, before = round(self.price, 2), round(self.previous_price, 2)
        if now > before:
            return "up"
        if now < before:
            return "down"
        return "flat"

    @property
    def change_percent(self) -> float:
        """Percent change vs. reference_price (the 'daily change')."""
        if not self.reference_price:
            return 0.0
        pct = round((self.price - self.reference_price) / self.reference_price * 100, 2)
        return pct + 0.0  # turn -0.0 into 0.0

    def to_dict(self) -> dict:
        """SSE payload for this ticker (PLAN.md section 6)."""
        return {
            "price": round(self.price, 2),
            "previous_price": round(self.previous_price, 2),
            "change_percent": self.change_percent,
            "direction": self.direction,
            "timestamp": iso_utc(self.timestamp),
        }


class PriceCache:
    """Latest prices, written by the one active market data source.

    All access happens on the asyncio event loop, so no lock is needed.
    """

    def __init__(self) -> None:
        self._entries: dict[str, PriceEntry] = {}

    def update(
        self,
        ticker: str,
        price: float,
        timestamp: datetime,
        reference_price: float | None = None,
    ) -> PriceEntry:
        """Record a new price; the current price becomes previous_price.

        reference_price is kept from the existing entry unless a new one is given.
        On the first update it defaults to the price itself.
        """
        old = self._entries.get(ticker)
        if reference_price is None:
            reference_price = old.reference_price if old else price
        entry = PriceEntry(
            price=price,
            previous_price=old.price if old else price,
            reference_price=reference_price,
            timestamp=timestamp,
        )
        self._entries[ticker] = entry
        return entry

    def get(self, ticker: str) -> PriceEntry | None:
        """Latest entry, or None if no price has arrived yet."""
        return self._entries.get(ticker)

    def price(self, ticker: str) -> float | None:
        """Shortcut for the latest price, or None."""
        entry = self._entries.get(ticker)
        return entry.price if entry else None

    def remove(self, ticker: str) -> None:
        self._entries.pop(ticker, None)

    def snapshot(self) -> dict[str, PriceEntry]:
        """Shallow copy of all entries, safe to iterate while the source keeps writing."""
        return dict(self._entries)

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._entries

    def __len__(self) -> int:
        return len(self._entries)
```

### Semantics

| Call | `price` | `previous_price` | `reference_price` | `direction` |
|---|---|---|---|---|
| `update("AAPL", 190.00, t0, reference_price=188.00)` (first) | 190.00 | 190.00 | 188.00 | flat |
| `update("AAPL", 190.30, t1)` | 190.30 | 190.00 | 188.00 (kept) | up |
| `update("AAPL", 190.304, t2)` | 190.304 | 190.30 | 188.00 | **flat** (same cents) |
| `update("AAPL", 189.90, t3, reference_price=190.30)` (new trading day) | 189.90 | 190.304 | 190.30 | down |

- No entry until the first `update`, so `get()` → `None` means "no price yet": the watchlist API shows `null`, and a trade fails with `No price for XYZ; add it to the watchlist first`.
- Prices are stored at **full float precision**; rounding to cents happens only in `to_dict()`. (Rounding in the model would make sub-cent simulator moves vanish forever.)
- Timestamps are tz-aware UTC `datetime`s internally; `iso_utc` is the one place they become strings. Other modules (portfolio snapshots, chat messages) should import `iso_utc` too so the whole API uses one format.

---

## 7. Unified Source Interface (`app/market/source.py`)

```python
"""The abstract market data source shared by the simulator and Massive."""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.market.cache import PriceCache


class MarketDataError(Exception):
    """Base class for market data errors."""


class UnknownTickerError(MarketDataError):
    """The data source has no data for this ticker."""


class MarketDataUnavailableError(MarketDataError):
    """The data source could not be reached (network error, auth error, rate limit)."""


class MarketDataSource(ABC):
    """Produces prices for a set of tracked tickers and writes them to a PriceCache."""

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache
        self._tickers: set[str] = set()

    @property
    def tickers(self) -> frozenset[str]:
        """Tickers currently tracked (watchlist ∪ open positions)."""
        return frozenset(self._tickers)

    @abstractmethod
    async def start(self, tickers: Iterable[str]) -> None:
        """Seed the cache for `tickers` and start the background update task.

        Must not raise because the upstream is unreachable: log and keep going.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background task and release resources. Safe to call twice."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Start tracking `ticker` and put a first price in the cache before returning.

        Does nothing if the ticker is already tracked and priced.
        Raises UnknownTickerError if the source has no data for it, and
        MarketDataUnavailableError if the source could not be reached.
        """

    async def remove_ticker(self, ticker: str) -> None:
        """Stop tracking `ticker` and drop it from the cache. Unknown tickers are ignored."""
        self._tickers.discard(ticker)
        self.cache.remove(ticker)
```

### Contract

| Method | `SimulatorSource` | `MassiveSource` |
|---|---|---|
| `start(tickers)` | seed every ticker into the cache, start 500ms tick task | one snapshot poll for all tickers (failure logged), start poll task |
| `add_ticker(t)` | seed price (known or random $50–300), cache it now; never raises | one-off snapshot for `t`; empty → `UnknownTickerError`; HTTP failure → `MarketDataUnavailableError` |
| `remove_ticker(t)` | drop from model and cache | shared default (drop from set and cache) |
| `stop()` | cancel + await task | cancel + await task, close HTTP client |
| `tickers` | read-only view of tracked set | same |

**Guarantee:** when `add_ticker` returns normally, `cache.get(t)` is not `None`. This is what lets `POST /api/watchlist` answer 201 with a price, and lets the LLM add a ticker and trade it in one response (watchlist changes execute before trades — PLAN.md §9).

**Not the source's job** (keeps it small; routes own it):

- format validation → `normalize_ticker` (§5)
- the watchlist ∪ positions rule → `untrack_if_unused` (§11.4)
- persistence → the database

---

## 8. Simulator

### 8.1 Model

Per ticker, per 500ms tick:

```
S(t+dt) = S(t) · exp( (μ − σ²/2)·dt + σ·√dt·Z )

dt = 0.5 s / (252 days · 6.5 h · 3600 s)  ≈ 8.48e-8 trading years
```

- `exp(…)` keeps prices positive; log-returns are normal. `−σ²/2` makes the expected price grow at μ.
- `dt` is in **trading time**, so σ is an ordinary annual volatility and the seed table reads like real data.
- Typical move (AAPL, $190, σ = 0.25): ≈ **$0.014 per tick**, ≈ **$0.43 per 8 minutes** (1 sd). Small but visible: sparklines auto-scale, and events add drama.

### 8.2 Increment 2: correlation and events

One market shock `M`, one shock per sector `S_k`, one idiosyncratic shock `e_i` per ticker each tick:

```
Z_i = √w_m · M + √w_s · S_sector(i) + √(1 − w_m − w_s) · e_i        (still standard normal)

w_m = 0.3, w_s = 0.3  →  corr = 0.6 within a sector, 0.3 across sectors
```

Then each ticker has probability `p = 0.001` per tick of a jump of ±2–5%. With 10 tickers at 2 ticks/s: about one event on the board every ~50 s, one per ticker every ~8 min.

Validated numbers (from MARKET_SIMULATOR.md §5, re-confirmed by the tests in §12): realised vol 0.2498 for σ = 0.25; same-sector correlation 0.602; cross-sector 0.294.

**Build order:** implement and test with `market_weight=0, sector_weight=0, event_probability=0` (increment 1) first; then switch the defaults on. The class supports both from day one.

### 8.3 Seed data (`app/market/seeds.py`)

```python
"""Seed prices and parameters for the simulator."""

from typing import NamedTuple

DEFAULT_DRIFT = 0.05   # annual drift (mu)
DEFAULT_SIGMA = 0.30   # annual volatility for unknown tickers
DEFAULT_SECTOR = "other"
UNKNOWN_PRICE_RANGE = (50.0, 300.0)


class TickerSpec(NamedTuple):
    price: float
    sigma: float
    sector: str
    drift: float = DEFAULT_DRIFT


SEEDS: dict[str, TickerSpec] = {
    "AAPL": TickerSpec(190.0, 0.25, "tech"),
    "GOOGL": TickerSpec(175.0, 0.28, "tech"),
    "MSFT": TickerSpec(420.0, 0.24, "tech"),
    "AMZN": TickerSpec(185.0, 0.30, "tech"),
    "TSLA": TickerSpec(250.0, 0.60, "auto"),
    "NVDA": TickerSpec(130.0, 0.50, "tech", drift=0.10),
    "META": TickerSpec(560.0, 0.35, "tech"),
    "JPM": TickerSpec(210.0, 0.20, "finance"),
    "V": TickerSpec(280.0, 0.20, "finance"),
    "NFLX": TickerSpec(700.0, 0.40, "media"),
}
```

### 8.4 Code (`app/market/simulator.py`)

```python
"""GBM market simulator: the default market data source."""

import asyncio
import logging
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.market.cache import PriceCache
from app.market.seeds import (
    DEFAULT_DRIFT,
    DEFAULT_SECTOR,
    DEFAULT_SIGMA,
    SEEDS,
    UNKNOWN_PRICE_RANGE,
)
from app.market.source import MarketDataSource

logger = logging.getLogger(__name__)

TICK_SECONDS = 0.5
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
DT = TICK_SECONDS / TRADING_SECONDS_PER_YEAR  # one tick, in trading years (~8.5e-8)

# Increment 2: correlation and events
MARKET_WEIGHT = 0.3       # share of shock variance from the market factor
SECTOR_WEIGHT = 0.3       # share from the sector factor
EVENT_PROBABILITY = 0.001  # per ticker per tick
EVENT_MIN, EVENT_MAX = 0.02, 0.05


@dataclass
class TickerState:
    """Simulated state of one ticker."""

    price: float
    sigma: float
    sector: str
    drift: float = DEFAULT_DRIFT


class GBMModel:
    """Geometric Brownian motion over a set of tickers. Pure math: no I/O, no clock.

    S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)

    With market_weight = sector_weight = event_probability = 0 this is plain,
    independent GBM (increment 1).
    """

    def __init__(
        self,
        rng: random.Random | None = None,
        *,
        market_weight: float = MARKET_WEIGHT,
        sector_weight: float = SECTOR_WEIGHT,
        event_probability: float = EVENT_PROBABILITY,
        dt: float = DT,
    ) -> None:
        if market_weight < 0 or sector_weight < 0 or market_weight + sector_weight > 1:
            raise ValueError("weights must be >= 0 and sum to at most 1")
        self.rng = rng or random.Random()
        self.states: dict[str, TickerState] = {}
        self.dt = dt
        self.event_probability = event_probability
        self._w_market = math.sqrt(market_weight)
        self._w_sector = math.sqrt(sector_weight)
        self._w_idio = math.sqrt(1 - market_weight - sector_weight)

    def add(self, ticker: str) -> float:
        """Start simulating `ticker` (no-op if present) and return its current price."""
        if ticker not in self.states:
            spec = SEEDS.get(ticker)
            if spec:
                state = TickerState(spec.price, spec.sigma, spec.sector, spec.drift)
            else:
                price = round(self.rng.uniform(*UNKNOWN_PRICE_RANGE), 2)
                state = TickerState(price, DEFAULT_SIGMA, DEFAULT_SECTOR)
            self.states[ticker] = state
        return self.states[ticker].price

    def remove(self, ticker: str) -> None:
        self.states.pop(ticker, None)

    def step(self) -> dict[str, float]:
        """Advance every ticker by one tick and return the new prices."""
        market = self.rng.gauss(0, 1)
        sectors: dict[str, float] = {}
        sqrt_dt = math.sqrt(self.dt)
        for state in self.states.values():
            if state.sector not in sectors:
                sectors[state.sector] = self.rng.gauss(0, 1)
            z = (
                self._w_market * market
                + self._w_sector * sectors[state.sector]
                + self._w_idio * self.rng.gauss(0, 1)
            )
            state.price *= math.exp(
                (state.drift - state.sigma**2 / 2) * self.dt + state.sigma * sqrt_dt * z
            )
            if self.event_probability and self.rng.random() < self.event_probability:
                jump = self.rng.uniform(EVENT_MIN, EVENT_MAX)
                state.price *= 1 + self.rng.choice((-1, 1)) * jump
        return {ticker: state.price for ticker, state in self.states.items()}


class SimulatorSource(MarketDataSource):
    """Simulated prices for every tracked ticker, updated every 500ms."""

    def __init__(
        self,
        cache: PriceCache,
        model: GBMModel | None = None,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        super().__init__(cache)
        self.model = model or GBMModel()
        self.tick_seconds = tick_seconds
        self._task: asyncio.Task | None = None

    async def start(self, tickers: Iterable[str]) -> None:
        for ticker in tickers:
            await self.add_ticker(ticker)
        self._task = asyncio.create_task(self._run(), name="market-simulator")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            return
        price = self.model.add(ticker)
        self.cache.update(ticker, price, datetime.now(UTC), reference_price=price)
        self._tickers.add(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.model.remove(ticker)
        await super().remove_ticker(ticker)

    def tick(self) -> None:
        """Step the model once and write all prices with one shared timestamp."""
        now = datetime.now(UTC)
        for ticker, price in self.model.step().items():
            self.cache.update(ticker, price, now)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                self.tick()
            except Exception:
                logger.exception("Simulator tick failed")
```

### 8.5 Behaviour notes

- `reference_price` = seed price, so "daily change %" is the move since the server started (PLAN.md: "the seed price at startup for the simulator").
- All tickers in a tick share one timestamp, so every SSE event after a tick carries a new `timestamp` for every ticker → the frontend appends a point every 500ms.
- Prices restart from the seeds on server restart (no persistence). Positions keep their `avg_cost`, so P&L jumps on restart. Acceptable for a simulator.
- `tick()` is public and synchronous: tests call it directly instead of sleeping.
- `_run` catches and logs any exception from a tick so the price feed never silently dies. (`CancelledError` is a `BaseException`, so cancellation still works.)
- Tuning: to make the demo livelier, pass a larger `dt` (e.g. `GBMModel(dt=DT * 20)`) or raise `EVENT_PROBABILITY`. Don't round inside the model.
- A removed ticker that is added again restarts from its seed (known tickers) or a new random price (unknown tickers), with a new `reference_price`. This fits the "since server start" meaning, but it is a visible jump if a user sells their last share of an unwatched ticker and adds it back.
- `start()` raises `RuntimeError` if called twice; it would otherwise leak a second background task (both sources).

---

## 9. Massive API Source

### 9.1 Endpoint

```
GET https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,TSLA
Authorization: Bearer $MASSIVE_API_KEY
```

- **One request per poll** covering all tracked tickers (sorted, comma-joined). Never one request per ticker.
- `tickers` must never be empty (an empty param returns the whole market, 10,000+ entries) — `poll()` returns early when nothing is tracked.
- The key goes in the header, never the URL, so it can't leak into logs.
- Needs **Stocks Starter or higher**. The free Basic plan has no snapshot access (403). See §9.4.

Response fields used (full sample in MASSIVE_API.md §4):

| JSON | Used as |
|---|---|
| `ticker` | cache key |
| `lastTrade.p` → `min.c` → `day.c` → `prevDay.c` | `price` (first non-zero) |
| `prevDay.c` | `reference_price` |
| `updated` (**nanoseconds**) → `lastTrade.t` → now | `timestamp` |

### 9.2 Parsing example

Input (one element of `tickers`):

```json
{
  "ticker": "AAPL",
  "updated": 1605192894630916600,
  "day":     {"c": 190.5},
  "prevDay": {"c": 189.27},
  "min":     {"c": 190.45},
  "lastTrade": {"p": 190.52, "t": 1605192894630916600}
}
```

```python
>>> parse_snapshot(item)
Quote(ticker='AAPL', price=190.52, reference_price=189.27,
      timestamp=datetime(2020, 11, 12, 14, 54, 54, 630916, tzinfo=UTC))
```

Overnight (snapshot reset at 3:30 AM ET): `lastTrade` absent, `min.c` and `day.c` are `0` → price falls back to `prevDay.c` = 189.27, `change_percent` = 0.

### 9.3 Code (`app/market/massive.py`)

```python
"""Massive (formerly Polygon.io) REST poller: the real market data source."""

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.market.cache import PriceCache
from app.market.source import (
    MarketDataSource,
    MarketDataUnavailableError,
    UnknownTickerError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.massive.com"
SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
DEFAULT_POLL_SECONDS = 15.0
REQUEST_TIMEOUT = 10.0


@dataclass(frozen=True, slots=True)
class Quote:
    """One ticker's price, parsed from a snapshot entry."""

    ticker: str
    price: float
    reference_price: float | None  # previous day's close
    timestamp: datetime            # UTC


def ns_to_datetime(ns: int) -> datetime:
    """Nanoseconds since the epoch -> tz-aware UTC datetime (integer math, no float loss)."""
    seconds, rem = divmod(ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=rem // 1000)


def _bar_close(item: dict, key: str) -> float | None:
    bar = item.get(key) or {}
    return bar.get("c") or None  # 0 means "no bar yet" (snapshot reset overnight)


def parse_snapshot(item: dict, now: datetime | None = None) -> Quote | None:
    """Parse one entry of the snapshot `tickers` array; None if it carries no usable price.

    Price order: last trade -> current minute bar -> today's bar -> previous close.
    """
    last_trade = item.get("lastTrade") or {}
    price = (
        last_trade.get("p")
        or _bar_close(item, "min")
        or _bar_close(item, "day")
        or _bar_close(item, "prevDay")
    )
    if not price:
        return None
    updated = item.get("updated") or last_trade.get("t")
    timestamp = ns_to_datetime(updated) if updated else (now or datetime.now(UTC))
    return Quote(
        ticker=item["ticker"],
        price=float(price),
        reference_price=_bar_close(item, "prevDay"),
        timestamp=timestamp,
    )


class MassiveSource(MarketDataSource):
    """Polls the multi-ticker snapshot endpoint: one request per poll for all tickers."""

    def __init__(
        self,
        cache: PriceCache,
        api_key: str,
        poll_interval: float = DEFAULT_POLL_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(cache)
        self.poll_interval = poll_interval
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
        self._task: asyncio.Task | None = None

    async def start(self, tickers: Iterable[str]) -> None:
        self._tickers = set(tickers)
        await self.poll()
        self._task = asyncio.create_task(self._run(), name="market-massive")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._client.aclose()

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers and ticker in self.cache:
            return
        try:
            items = await self._fetch([ticker])
        except httpx.HTTPError as exc:
            raise MarketDataUnavailableError(str(exc)) from exc
        quote = next(
            (q for q in map(parse_snapshot, items) if q and q.ticker == ticker), None
        )
        if quote is None:
            raise UnknownTickerError(ticker)
        self._apply(quote)
        self._tickers.add(ticker)

    async def poll(self) -> None:
        """Fetch all tracked tickers once. Failures are logged; the next poll retries."""
        if not self._tickers:
            return
        try:
            items = await self._fetch(sorted(self._tickers))
        except httpx.HTTPError as exc:
            logger.warning("Massive snapshot poll failed: %s", describe_error(exc))
            return
        for item in items:
            quote = parse_snapshot(item)
            # A ticker removed while the request was in flight must not come back.
            if quote and quote.ticker in self._tickers:
                self._apply(quote)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval)
            try:
                await self.poll()
            except Exception:
                logger.exception("Massive poll crashed")

    async def _fetch(self, tickers: list[str]) -> list[dict]:
        response = await self._client.get(
            SNAPSHOT_PATH, params={"tickers": ",".join(tickers)}
        )
        response.raise_for_status()
        return response.json().get("tickers") or []

    def _apply(self, quote: Quote) -> None:
        """Write a quote to the cache unless nothing changed since the last poll."""
        old = self.cache.get(quote.ticker)
        if old and old.timestamp == quote.timestamp:
            return
        self.cache.update(
            quote.ticker, quote.price, quote.timestamp, reference_price=quote.reference_price
        )


def describe_error(exc: httpx.HTTPError) -> str:
    """Short log text; never includes the API key (it travels in a header, not the URL)."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        hint = {
            401: "invalid MASSIVE_API_KEY",
            403: "plan does not include snapshots (Starter or higher needed)",
            429: "rate limit exceeded; raise MASSIVE_POLL_SECONDS",
        }.get(status, "")
        return f"HTTP {status} {hint}".strip()
    return f"{type(exc).__name__}: {exc}"
```

### 9.4 Behaviour notes

- **Skip unchanged snapshots.** If `updated` hasn't moved since the last poll, the cache entry is left untouched. Otherwise every poll would copy `price` into `previous_price`, turn `direction` to `flat`, and bump `timestamp`, making the frontend append fake flat points. Outside market hours this means prices simply stand still, which is correct.
- **SSE still sends every ticker every 500ms** (PLAN.md: "SSE resends unchanged entries"). The frontend flashes and appends a point only when `timestamp` changes.
- **Never go backwards.** A quote whose `updated` is not newer than the cached one is dropped (`quote.timestamp <= old.timestamp`), so a slow poll response arriving after an `add_ticker` refetch cannot roll a price back.
- **Failures never kill the loop.** `poll()` catches `httpx.HTTPError` (timeouts, connection errors, 4xx/5xx via `raise_for_status`) and logs one line; `_run` additionally catches anything unexpected. The next poll retries. There is no retry/backoff inside a poll — the next poll *is* the retry.
- **Malformed 200 bodies count as "unavailable".** `_fetch` turns a body that isn't a snapshot (HTML from a proxy, non-object JSON, `tickers` not a list) into `httpx.DecodingError`, and drops items without a `ticker`. So `start()` still boots and `add_ticker()` raises `MarketDataUnavailableError` (503), never a 500.
- Log lines name the likely cause:

  ```
  WARNING app.market.massive: Massive snapshot poll failed: HTTP 401 invalid MASSIVE_API_KEY
  WARNING app.market.massive: Massive snapshot poll failed: HTTP 403 plan does not include snapshots (Starter or higher needed)
  WARNING app.market.massive: Massive snapshot poll failed: HTTP 429 rate limit exceeded; raise MASSIVE_POLL_SECONDS
  WARNING app.market.massive: Massive snapshot poll failed: ConnectTimeout: ...
  ```

- **Free (Basic) keys:** every poll returns 403 and no prices ever arrive; the 403 line above appears every 15s. Users with a free key should leave `MASSIVE_API_KEY` empty and use the simulator. (Supporting Basic would need an end-of-day source on the grouped-daily endpoint — out of scope.)
- **Race with removal:** a ticker removed while a poll is in flight is not written back (`quote.ticker in self._tickers`).
- **Timestamps** are converted with integer math (`divmod` by 10⁹), so no float rounding at microsecond resolution.
- `add_ticker` costs one extra request (paid plans have no call limit).

---

## 10. Factory (`app/market/factory.py`)

```python
"""Pick the market data source from the environment."""

import logging
import os

from app.market.cache import PriceCache
from app.market.massive import DEFAULT_POLL_SECONDS, MassiveSource
from app.market.simulator import SimulatorSource
from app.market.source import MarketDataSource

logger = logging.getLogger(__name__)


def create_market_source(cache: PriceCache) -> MarketDataSource:
    """MassiveSource if MASSIVE_API_KEY is set and non-empty, otherwise SimulatorSource."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not api_key:
        logger.info("Market data: simulator")
        return SimulatorSource(cache)
    interval = float(os.environ.get("MASSIVE_POLL_SECONDS") or DEFAULT_POLL_SECONDS)
    logger.info("Market data: Massive, polling every %.0fs", interval)
    return MassiveSource(cache, api_key, poll_interval=interval)
```

| `MASSIVE_API_KEY` | `MASSIVE_POLL_SECONDS` | Result |
|---|---|---|
| unset / `""` / whitespace | — | `SimulatorSource` |
| `abc123` | unset | `MassiveSource`, 15s |
| `abc123` | `5` | `MassiveSource`, 5s (paid plans: 2–15s) |
| `abc123` | `abc`, `15s` | `MassiveSource`, 15s, with a warning |
| `abc123` | `0`, `-5`, `0.2`, `nan` | `MassiveSource`, clamped to the 1s floor, with a warning |

Add to `.env.example`:

```bash
# Optional: Massive poll interval in seconds (default 15; paid plans can use 2-15)
MASSIVE_POLL_SECONDS=
```

In local dev `main.py` loads `.env` from the project root with `python-dotenv` (`override=False`, so real environment variables win) before the factory runs; in Docker it comes from `--env-file`. `main.py` also calls `logging.basicConfig(level=INFO)`, so the "Market data: ..." line and Massive warnings appear in the server log.

---

## 11. FastAPI Integration

### 11.1 Lifespan (`app/main.py`)

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.stream import router as stream_router
from app.database import init_db, load_tracked_tickers   # owned by the database module
from app.market import PriceCache, create_market_source


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                                    # lazy schema + seed (PLAN.md §7)
    cache = PriceCache()
    source = create_market_source(cache)
    await source.start(load_tracked_tickers())   # watchlist ∪ positions
    app.state.prices = cache
    app.state.market = source
    try:
        yield
    finally:
        await source.stop()


app = FastAPI(lifespan=lifespan)
app.include_router(stream_router)
# ... other routers, then static files mounted last
```

`load_tracked_tickers()` is a single query:

```sql
SELECT ticker FROM watchlist WHERE user_id = 'default'
UNION
SELECT ticker FROM positions WHERE user_id = 'default';
```

The portfolio-snapshot background task (every 30s, PLAN.md §7) should also be started here and reads prices from `app.state.prices`. Start the market source **before** it so the startup snapshot sees prices.

Dependency helpers for routes:

```python
from fastapi import Request

from app.market import MarketDataSource, PriceCache


def get_prices(request: Request) -> PriceCache:
    return request.app.state.prices


def get_market(request: Request) -> MarketDataSource:
    return request.app.state.market
```

### 11.2 SSE endpoint (`app/api/stream.py`)

```python
"""SSE endpoint: GET /api/stream/prices."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.market.cache import PriceCache

STREAM_INTERVAL = 0.5
RETRY_MS = 1000

router = APIRouter()


async def price_events(
    cache: PriceCache,
    is_disconnected: Callable[[], Awaitable[bool]],
    interval: float = STREAM_INTERVAL,
) -> AsyncIterator[str]:
    """Yield one SSE event with the full snapshot every `interval` seconds."""
    yield f"retry: {RETRY_MS}\n\n"
    while not await is_disconnected():
        payload = {ticker: e.to_dict() for ticker, e in sorted(cache.snapshot().items())}
        yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
        await asyncio.sleep(interval)


@router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    return StreamingResponse(
        price_events(request.app.state.prices, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

Real output from the prototype (simulator, two tickers, `curl -N localhost:8000/api/stream/prices`):

```
retry: 1000

data: {"AAPL":{"price":190.0,"previous_price":190.0,"change_percent":0.0,"direction":"flat","timestamp":"2026-10-21T11:43:29.387Z"},"MSFT":{"price":420.0,"previous_price":420.0,"change_percent":0.0,"direction":"flat","timestamp":"2026-10-21T11:43:29.387Z"}}

data: {"AAPL":{"price":189.99,"previous_price":190.0,"change_percent":-0.01,"direction":"down","timestamp":"2026-10-21T11:43:29.888Z"},"MSFT":{"price":419.99,"previous_price":420.0,"change_percent":0.0,"direction":"down","timestamp":"2026-10-21T11:43:29.888Z"}}
```

Notes:

- No per-client state, no diffing: each connection runs its own generator over the shared cache. 500ms × a few clients is negligible.
- The SSE stream ticks independently of the source (500ms for both by default, but they are not synchronised). With Massive, ~30 identical events go out between polls; the frontend dedupes on `timestamp`.
- When the client goes away, `is_disconnected()` turns true or Starlette cancels the generator; either way it ends.
- **Server shutdown (post-review change).** The route returns `sse_starlette.EventSourceResponse`, not the `StreamingResponse` shown above. Uvicorn waits for open connections to close before it runs the lifespan shutdown, and a plain `StreamingResponse` only ends when the *client* leaves, so with a browser tab open `docker stop` hung for 10s and then SIGKILLed the process. sse-starlette watches for uvicorn's exit signal and sets a `shutdown_event`; the generator's stop check includes it, so the stream ends cleanly (within a 1s grace period) and shutdown takes well under a second. Keep-alive pings are disabled (`ping=0`) because a snapshot goes out every 500ms anyway.
- `EventSource` reconnects automatically; `retry: 1000` makes it try after 1s.

Frontend consumption (for reference; owned by the frontend agent):

```ts
const es = new EventSource("/api/stream/prices");
es.onmessage = (e) => {
  const snapshot: Record<string, PriceUpdate> = JSON.parse(e.data);
  for (const [ticker, u] of Object.entries(snapshot)) {
    if (u.timestamp !== lastTimestamp[ticker]) { /* flash + append point */ }
  }
};
```

### 11.3 Watchlist routes (`app/api/watchlist.py`)

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.market import (
    InvalidTickerError, MarketDataSource, MarketDataUnavailableError, PriceCache,
    UnknownTickerError, normalize_ticker,
)

router = APIRouter()


class AddTicker(BaseModel):
    ticker: str


def ticker_or_400(raw: str) -> str:
    try:
        return normalize_ticker(raw)
    except InvalidTickerError as exc:
        raise HTTPException(400, str(exc)) from exc


def watch_item(ticker: str, prices: PriceCache) -> dict:
    entry = prices.get(ticker)
    return {
        "ticker": ticker,
        "price": round(entry.price, 2) if entry else None,
        "change_percent": entry.change_percent if entry else None,
    }


@router.get("/api/watchlist")
async def list_watchlist(prices: PriceCache = Depends(get_prices)):
    return [watch_item(t, prices) for t in db.watchlist_tickers()]


@router.post("/api/watchlist", status_code=201)
async def add_to_watchlist(
    body: AddTicker,
    response: Response,
    market: MarketDataSource = Depends(get_market),
    prices: PriceCache = Depends(get_prices),
):
    ticker = ticker_or_400(body.ticker)
    if db.watchlist_contains(ticker):
        response.status_code = 200                       # silent success (PLAN.md §8)
        return watch_item(ticker, prices)
    try:
        await market.add_ticker(ticker)                  # price is in the cache after this
    except UnknownTickerError:
        raise HTTPException(400, "Unknown ticker")
    except MarketDataUnavailableError:
        raise HTTPException(503, "Market data unavailable")
    db.watchlist_add(ticker)
    return watch_item(ticker, prices)


@router.delete("/api/watchlist/{ticker}", status_code=204)
async def remove_from_watchlist(ticker: str, market: MarketDataSource = Depends(get_market)):
    ticker = ticker_or_400(ticker)
    if not db.watchlist_remove(ticker):
        raise HTTPException(404, f"{ticker} is not on the watchlist")
    await untrack_if_unused(ticker, market)
```

(`db.*` are placeholders for the database module's functions.) The add order matters: **source first, database second**, so an unknown ticker never lands in the watchlist table.

### 11.4 Trades, the tracked-ticker rule, and other consumers

```python
async def untrack_if_unused(ticker: str, market: MarketDataSource) -> None:
    """Stop price updates for `ticker` unless it is still watched or held (PLAN.md §6)."""
    if not db.watchlist_contains(ticker) and not db.position_exists(ticker):
        await market.remove_ticker(ticker)
```

Call it after: `DELETE /api/watchlist/{t}`, an LLM `remove` watchlist change, and **any sell that deletes a position** (quantity < 1e-9).

Trade execution (shared by `POST /api/portfolio/trade` and the LLM):

```python
def fill_price(ticker: str, prices: PriceCache) -> float:
    entry = prices.get(ticker)
    if entry is None:
        raise TradeError(f"No price for {ticker}; add it to the watchlist first")
    return entry.price          # full precision; round only when serialising
```

A buy is only possible for a ticker already in the cache, so buys never need to call `add_ticker`.

Other read-only consumers:

```python
# GET /api/portfolio
current_price = prices.price(pos.ticker) or pos.avg_cost   # fallback if Massive hasn't answered yet

# LLM context (PLAN.md §9 step 1)
watchlist_ctx = [
    {"ticker": t, "price": round(e.price, 2), "change_percent": e.change_percent}
    for t, e in prices.snapshot().items()
]
```

### 11.5 Error mapping

| Raised | Where | HTTP | `detail` |
|---|---|---|---|
| `InvalidTickerError` | any route taking a ticker | 400 | `Invalid ticker: '...'` |
| `UnknownTickerError` | `POST /api/watchlist`, LLM add | 400 | `Unknown ticker` |
| `MarketDataUnavailableError` | `POST /api/watchlist`, LLM add | 503 | `Market data unavailable` |
| no cache entry | trade | 400 | `No price for XYZ; add it to the watchlist first` |

In the chat flow these become `{"status": "failed", "error": "<detail>"}` on the individual action; other actions still run.

---

## 12. Tests

Layout under `backend/tests/` with `asyncio_mode = "auto"` (§3), so `async def test_…` just works. No network: Massive is faked with `httpx.MockTransport`; the simulator uses a seeded `random.Random`.

```bash
uv run pytest tests/market tests/api -q
# 81 passed in ~2s (after the review fixes)
```

### 12.1 `tests/market/test_tickers.py`

```python
import pytest

from app.market.tickers import InvalidTickerError, normalize_ticker


@pytest.mark.parametrize("raw,expected", [("aapl", "AAPL"), (" brk.b ", "BRK.B"), ("V", "V")])
def test_valid(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", ".AAPL", "AAPL1", "TOOLONGTICK", "AA PL", "BRK-B"])
def test_invalid(raw):
    with pytest.raises(InvalidTickerError):
        normalize_ticker(raw)
```

### 12.2 `tests/market/test_cache.py`

```python
from datetime import UTC, datetime, timedelta

from app.market.cache import PriceCache, iso_utc

T0 = datetime(2026, 10, 14, 13, 30, 0, 500_000, tzinfo=UTC)


def test_first_update_sets_all_prices_equal():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0)
    e = cache.get("AAPL")
    assert e.price == e.previous_price == e.reference_price == 190.0
    assert e.direction == "flat"
    assert e.change_percent == 0.0


def test_second_update_moves_previous_and_keeps_reference():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0, reference_price=188.0)
    cache.update("AAPL", 191.0, T0 + timedelta(seconds=1))
    e = cache.get("AAPL")
    assert (e.previous_price, e.price, e.reference_price) == (190.0, 191.0, 188.0)
    assert e.direction == "up"
    assert e.change_percent == 1.6


def test_direction_uses_displayed_cents():
    cache = PriceCache()
    cache.update("AAPL", 190.001, T0)
    cache.update("AAPL", 190.004, T0)
    assert cache.get("AAPL").direction == "flat"
    cache.update("AAPL", 189.99, T0)
    assert cache.get("AAPL").direction == "down"


def test_missing_and_removed():
    cache = PriceCache()
    assert cache.get("XYZ") is None
    cache.update("XYZ", 10.0, T0)
    cache.remove("XYZ")
    cache.remove("XYZ")
    assert "XYZ" not in cache


def test_to_dict_matches_sse_contract():
    cache = PriceCache()
    cache.update("AAPL", 190.05, T0, reference_price=189.45)
    cache.update("AAPL", 190.1234, T0)
    assert cache.get("AAPL").to_dict() == {
        "price": 190.12,
        "previous_price": 190.05,
        "change_percent": 0.36,
        "direction": "up",
        "timestamp": "2026-10-14T13:30:00.500Z",
    }


def test_iso_utc_converts_other_timezones():
    est = datetime(2026, 10, 14, 9, 30, tzinfo=UTC).astimezone()
    assert iso_utc(est) == "2026-10-14T09:30:00.000Z"


def test_tiny_drop_is_not_negative_zero():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0)
    cache.update("AAPL", 189.999, T0)
    assert str(cache.get("AAPL").change_percent) == "0.0"
```

### 12.3 `tests/market/test_simulator.py`

```python
import math
import random
import statistics

import pytest

from app.market import simulator
from app.market.cache import PriceCache
from app.market.simulator import DT, GBMModel, SimulatorSource


def plain(seed=42, **kw):
    """Increment 1 model: independent GBM, no events."""
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


def test_realised_volatility_matches_sigma():
    m = plain()
    m.add("AAPL")
    r, _ = log_returns(m, "AAPL", "AAPL", 100_000)
    annual = statistics.stdev(r) / math.sqrt(DT)
    assert annual == pytest.approx(0.25, rel=0.05)


def test_same_seed_same_path():
    a, b = plain(7), plain(7)
    for m in (a, b):
        m.add("AAPL"), m.add("NEW")
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
    import asyncio

    cache = PriceCache()
    src = SimulatorSource(cache, plain(), tick_seconds=0.01)
    await src.start(["AAPL"])
    await asyncio.sleep(0.05)
    await src.stop()
    assert cache.get("AAPL").price != 190.0


async def test_loop_survives_tick_error(monkeypatch, caplog):
    import asyncio

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
```

### 12.4 `tests/market/test_massive.py`

```python
import json
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
    [((), 190.52), (("lastTrade",), 190.45), (("lastTrade", "min"), 190.5),
     (("lastTrade", "min", "day"), 189.27)],
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


async def test_unchanged_updated_is_skipped():
    fake = FakeMassive([AAPL])
    src, cache = make_source(fake)
    await src.start(["AAPL"])
    first = cache.get("AAPL")
    fake.items["AAPL"] = {**AAPL, "lastTrade": {"p": 999.0}}  # same `updated`
    await src.poll()
    assert cache.get("AAPL") is first
    fake.items["AAPL"] = {**AAPL, "updated": AAPL["updated"] + 15 * 10**9,
                          "lastTrade": {"p": 191.0}}
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


async def test_failed_poll_is_logged_and_survives(caplog):
    src, cache = make_source(FakeMassive(status=403))
    await src.start(["AAPL"])  # must not raise
    assert cache.get("AAPL") is None
    assert "Starter or higher" in caplog.text
    assert "test-key" not in caplog.text
    await src.stop()


async def test_removed_ticker_is_not_rewritten():
    src, cache = make_source(FakeMassive([AAPL]))
    await src.start(["AAPL"])
    await src.remove_ticker("AAPL")
    await src.poll()
    assert cache.get("AAPL") is None
    await src.stop()
```

### 12.5 `tests/market/test_conformance.py`

The same behavioural test run against both sources, plus the factory:

```python
import random

import httpx
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
```

### 12.6 `tests/api/test_stream.py`

```python
import json
from datetime import UTC, datetime

from app.market.cache import PriceCache
from app.api.stream import price_events


async def test_price_events_yields_full_snapshot_until_disconnect():
    cache = PriceCache()
    ts = datetime(2026, 10, 14, 13, 30, tzinfo=UTC)
    cache.update("MSFT", 420.0, ts)
    cache.update("AAPL", 190.0, ts)
    checks = iter([False, False, True])

    async def is_disconnected():
        return next(checks)

    events = [e async for e in price_events(cache, is_disconnected, interval=0)]
    assert events[0] == "retry: 1000\n\n"
    assert len(events) == 3
    payload = json.loads(events[1].removeprefix("data: "))
    assert list(payload) == ["AAPL", "MSFT"]
    assert payload["AAPL"]["timestamp"] == "2026-10-14T13:30:00.000Z"
```

---

## 13. Implementation Order

1. `tickers.py`, `cache.py` + tests.
2. `source.py`, `seeds.py`, `simulator.py` with the increment-2 knobs at 0 + increment-1 tests.
3. `factory.py` (simulator branch), `api/stream.py`, lifespan in `main.py`. Check with `curl -N localhost:8000/api/stream/prices`.
4. Turn on increment 2 (default weights and events) + correlation/event tests.
5. `massive.py` + `test_massive.py` + conformance tests. Optional manual check with a Starter+ key: `MASSIVE_API_KEY=… uv run uvicorn app.main:app` and watch the log and the stream.
6. Wire watchlist add/remove, `untrack_if_unused`, and trade fill price into the routes (§11.3–11.4).
