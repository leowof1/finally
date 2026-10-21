# Market Simulator

How the FinAlly backend simulates stock prices when `MASSIVE_API_KEY` is not set. The simulator is the default data source and implements the `MarketDataSource` interface from MARKET_INTERFACE.md. It has no external dependencies: only the standard library (`random`, `math`, `asyncio`).

## 1. Goals

- Prices that look real: positive, a reasonable size, moving a little on every tick, never jumping wildly (except for deliberate events).
- An update every 500ms for every tracked ticker, so the UI flashes and sparklines fill steadily.
- Any valid ticker works (unknown tickers get a random seed price).
- Deterministic when given a seeded RNG, so unit tests are reproducible.

Built in two increments, as PLAN.md requires:

1. **Plain GBM**: independent tickers. Build and test this first.
2. **Correlation + events**: sector/market co-movement and occasional 2-5% jumps.

## 2. The Math: Geometric Brownian Motion

For each ticker, each tick:

```
S(t+dt) = S(t) * exp( (mu - sigma^2 / 2) * dt + sigma * sqrt(dt) * Z )
```

| Symbol | Meaning | Value |
|---|---|---|
| `S` | price | starts at the seed price |
| `mu` | annual drift | `0.05` (5%/yr) for all tickers |
| `sigma` | annual volatility | per ticker, 0.20-0.60 (table below); unknown tickers `0.30` |
| `dt` | tick length in trading years | `0.5 / (252 * 6.5 * 3600)` ≈ `8.5e-8` |
| `Z` | standard normal shock | `random.gauss(0, 1)` (increment 1); the correlated shock (increment 2) |

Why this form:

- `exp(...)` keeps prices positive, and log-returns are normally distributed, the textbook equity model.
- The `- sigma^2/2` term makes the expected price grow at `mu`, with no drift bias from volatility.
- With `dt` measured in trading time, `sigma` is a normal annual volatility, so the seed table reads like real data.

Typical size of moves (AAPL, $190, sigma 0.25): about **$0.014 per tick**, about **$0.43 over 8 minutes** (1 sd). That's realistic and small. Sparklines auto-scale their y-axis, so the movement is still clearly visible; events (increment 2) add the drama.

## 3. Seed Data (`seeds.py`)

```python
DEFAULT_SIGMA = 0.30
DEFAULT_SECTOR = "other"

# ticker: (seed price, annual volatility, sector)
SEEDS: dict[str, tuple[float, float, str]] = {
    "AAPL":  (190.0, 0.25, "tech"),
    "GOOGL": (175.0, 0.28, "tech"),
    "MSFT":  (420.0, 0.24, "tech"),
    "AMZN":  (185.0, 0.30, "tech"),
    "TSLA":  (250.0, 0.60, "auto"),
    "NVDA":  (130.0, 0.50, "tech"),
    "META":  (560.0, 0.35, "tech"),
    "JPM":   (210.0, 0.20, "finance"),
    "V":     (280.0, 0.20, "finance"),
    "NFLX":  (700.0, 0.40, "media"),
}
```

Unknown tickers (e.g. `PYPL` added from the UI) get `rng.uniform(50, 300)`, `DEFAULT_SIGMA` and `DEFAULT_SECTOR`, as PLAN.md requires.

## 4. Code Structure

Two layers, so the math is tested without asyncio:

```
backend/app/market/
├── seeds.py        # SEEDS, DEFAULT_SIGMA, DEFAULT_SECTOR
└── simulator.py    # GBMModel (pure math)  +  SimulatorSource (asyncio + PriceCache)
```

- **`GBMModel`**: holds per-ticker state, `add()` / `remove()` tickers, `step()` advances all of them one tick and returns new prices. No I/O, no clock, injectable `random.Random`.
- **`SimulatorSource`**: the `MarketDataSource`. Owns a `GBMModel`, runs the 500ms loop, writes to the `PriceCache`.

### 4.1 Increment 1: plain GBM

```python
import math
import random
from dataclasses import dataclass

from app.market.seeds import DEFAULT_SECTOR, DEFAULT_SIGMA, SEEDS

TICK_SECONDS = 0.5
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
DT = TICK_SECONDS / TRADING_SECONDS_PER_YEAR
DRIFT = 0.05


@dataclass
class TickerState:
    """Simulated state of one ticker."""

    price: float
    sigma: float
    sector: str


class GBMModel:
    """Geometric Brownian motion over a set of tickers."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.states: dict[str, TickerState] = {}

    def add(self, ticker: str) -> float:
        """Start simulating `ticker` and return its seed price."""
        if ticker not in self.states:
            price, sigma, sector = SEEDS.get(
                ticker, (round(self.rng.uniform(50, 300), 2), DEFAULT_SIGMA, DEFAULT_SECTOR)
            )
            self.states[ticker] = TickerState(price, sigma, sector)
        return self.states[ticker].price

    def remove(self, ticker: str) -> None:
        self.states.pop(ticker, None)

    def step(self) -> dict[str, float]:
        """Advance every ticker by one tick and return the new prices."""
        for state in self.states.values():
            z = self.rng.gauss(0, 1)
            state.price *= math.exp(
                (DRIFT - state.sigma**2 / 2) * DT + state.sigma * math.sqrt(DT) * z
            )
        return {ticker: state.price for ticker, state in self.states.items()}
```

### 4.2 SimulatorSource

```python
import asyncio
from datetime import UTC, datetime


class SimulatorSource(MarketDataSource):
    """Simulated prices, updated every 500ms."""

    def __init__(self, cache: PriceCache, model: GBMModel | None = None) -> None:
        super().__init__(cache)
        self.model = model or GBMModel()
        self._task: asyncio.Task | None = None

    async def start(self, tickers) -> None:
        for ticker in tickers:
            await self.add_ticker(ticker)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self.tickers:
            return
        price = self.model.add(ticker)
        self.cache.update(ticker, price, datetime.now(UTC), reference_price=price)
        self.tickers.add(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.model.remove(ticker)
        await super().remove_ticker(ticker)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(TICK_SECONDS)
            self.tick()

    def tick(self) -> None:
        """Step the model once and write all prices with one shared timestamp."""
        now = datetime.now(UTC)
        for ticker, price in self.model.step().items():
            self.cache.update(ticker, price, now)
```

Notes:

- `reference_price` = seed price, set on the first `cache.update`, as PLAN.md specifies ("seed price at startup"). Daily change % is the move since the server started.
- The price stays a full-precision float inside the model; rounding to cents only happens in `PriceEntry.to_dict()`. Rounding inside the model would make small moves vanish.
- Every tick changes every price, so `timestamp` changes every 500ms and the frontend flashes and appends a point each time.
- Prices restart from the seeds when the server restarts (there's no persistence). Positions keep their `avg_cost`, so P&L jumps on restart. That's acceptable for a simulator.
- `tick()` is public and synchronous, so tests can call it directly without sleeping.

### 4.3 Increment 2: correlation and events

Only after increment 1 works and is tested. Two changes inside `GBMModel.step()`; nothing else changes.

**Correlated shocks: a one-factor-per-level model.** Each tick draws one market shock `M`, one shock `S_k` per sector, and one idiosyncratic shock `e_i` per ticker:

```
Z_i = sqrt(w_m) * M + sqrt(w_s) * S_sector(i) + sqrt(1 - w_m - w_s) * e_i
```

With `w_m = 0.3`, `w_s = 0.3`, every `Z_i` is still standard normal (the weights sum to 1), so `sigma` keeps its meaning. The resulting correlation of returns is `w_m + w_s = 0.6` within a sector and `w_m = 0.3` across sectors: tech stocks move together, and everything moves a little with the market.

**Random events.** After the GBM step, each ticker has probability `p = 0.001` per tick of an event: an instant jump of ±2-5%. With 10 tickers at 2 ticks/s that is about one event every ~50 seconds somewhere on the board, and about one every ~8 minutes per ticker.

```python
MARKET_WEIGHT = 0.3
SECTOR_WEIGHT = 0.3
EVENT_PROBABILITY = 0.001
EVENT_MIN, EVENT_MAX = 0.02, 0.05


class GBMModel:
    ...

    def step(self) -> dict[str, float]:
        """Advance every ticker by one tick with correlated shocks and rare jumps."""
        market = self.rng.gauss(0, 1)
        sectors = {s.sector: self.rng.gauss(0, 1) for s in self.states.values()}
        for state in self.states.values():
            z = self._shock(market, sectors[state.sector])
            state.price *= math.exp(
                (DRIFT - state.sigma**2 / 2) * DT + state.sigma * math.sqrt(DT) * z
            )
            if self.rng.random() < EVENT_PROBABILITY:
                jump = self.rng.uniform(EVENT_MIN, EVENT_MAX)
                state.price *= 1 + self.rng.choice((-1, 1)) * jump
        return {ticker: state.price for ticker, state in self.states.items()}

    def _shock(self, market: float, sector: float) -> float:
        """Standard normal shock mixing market, sector and ticker-specific noise."""
        idio = self.rng.gauss(0, 1)
        return (
            math.sqrt(MARKET_WEIGHT) * market
            + math.sqrt(SECTOR_WEIGHT) * sector
            + math.sqrt(1 - MARKET_WEIGHT - SECTOR_WEIGHT) * idio
        )
```

## 5. Validation (prototype run)

The model above was prototyped and checked before writing this document:

| Check | Expected | Measured |
|---|---|---|
| Annual vol recovered from 200k ticks (sigma 0.25, no corr/events) | 0.25 | 0.2498 |
| Return correlation, same sector | 0.60 | 0.602 |
| Return correlation, different sectors | 0.30 | 0.294 |
| 1-sd move, $190 stock, 8 minutes | — | $0.43 |

## 6. Tests (`backend/tests/market/test_simulator.py`)

Use `GBMModel(random.Random(42))` for determinism.

Increment 1:

- `add()` returns the seed price for a known ticker; unknown ticker gets a price in `[50, 300]`; adding twice keeps the first price.
- `step()` returns all tracked tickers, every price > 0, and prices change.
- Volatility: realised annual vol over ~100k steps of one ticker is within 5% of its `sigma`.
- Same seed → identical price paths.
- `SimulatorSource`: after `start([...])`, every ticker is in the cache with `previous_price == price == reference_price`; after `tick()`, `timestamp` and `previous_price` have moved; `add_ticker` writes a price right away; `remove_ticker` removes it from the cache and model.

Increment 2:

- Correlation over ~50k steps: same-sector ≈ 0.6, cross-sector ≈ 0.3 (tolerance ±0.05).
- Events: with `EVENT_PROBABILITY` monkeypatched to `1.0` and zero volatility, each step moves every price by 2-5%.
