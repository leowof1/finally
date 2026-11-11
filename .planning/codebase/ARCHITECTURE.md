<!-- refreshed: 2026-11-03 -->
# Architecture

**Analysis Date:** 2026-11-03

## System Overview

The repository is a partially built system. Only the market data subsystem in `backend/app/market/` contains implemented source code. The planned API, portfolio, database, LLM, and frontend layers described in `planning/PLAN.md` exist only as empty directories or artifacts.

```text
┌──────────────────────────────────────────────────────────────┐
│  Planned (not implemented)                                    │
│  FastAPI app entry, /api routes, portfolio, SQLite, LLM chat  │
│  `backend/app/api/`  `backend/app/portfolio/`  `backend/app/db/`│
│  `backend/app/llm/`  (only __pycache__ present)               │
├──────────────────────────────────────────────────────────────┤
│  Implemented: Market Data Subsystem                           │
│  `backend/app/market/`                                        │
│                                                               │
│  MarketDataSource (ABC)  `interface.py`                       │
│   ├── SimulatorDataSource  `simulator.py`  (GBM, default)     │
│   └── MassiveDataSource    `massive_client.py` (REST poller)  │
│          │  created by                                        │
│          ▼                                                    │
│  create_market_data_source()  `factory.py`                    │
│          │  writes to                                         │
│          ▼                                                    │
│  PriceCache  `cache.py`  (Lock + version counter)             │
│          │  read by                                           │
│          ▼                                                    │
│  create_stream_router() → GET /api/stream/prices  `stream.py` │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  Standalone consumer                                          │
│  `backend/market_data_demo.py` (Rich terminal dashboard)      │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  `backend/static/` — Next.js static export artifacts           │
│  (no `frontend/` source present; `frontend/` is empty)         │
└──────────────────────────────────────────────────────────────┘
```

## Pattern Overview

**Overall:** Producer/consumer over a shared in-memory cache, with a Strategy pattern for market data providers and a factory for selection.

**Key Characteristics:**
- Producers (simulator or Massive poller) run as background `asyncio` tasks and write only to `PriceCache`.
- Consumers (SSE endpoint, and planned portfolio valuation and trade execution) read only from `PriceCache`. They never call a data source for prices.
- Provider selection is driven by the `MASSIVE_API_KEY` environment variable, read once in `backend/app/market/factory.py`.
- Dependency injection is done through factory functions and constructor arguments rather than module globals (`create_stream_router(price_cache)`, `SimulatorDataSource(price_cache=...)`).
- The package uses explicit public exports in `backend/app/market/__init__.py`.

## Layers

**Domain models:**
- Purpose: Immutable price snapshot value type.
- Location: `backend/app/market/models.py`
- Contains: frozen, slotted dataclass `PriceUpdate` with derived `change`, `change_percent`, `direction`, and `to_dict()`.
- Depends on: standard library only.
- Used by: `cache.py`, `stream.py`, `simulator.py`, `massive_client.py`.

**Storage (in-memory state):**
- Purpose: Latest-price store shared between producers and consumers.
- Location: `backend/app/market/cache.py`
- Contains: `PriceCache` with a `threading.Lock`, a dict of `PriceUpdate`, and a monotonically increasing `version`.
- Depends on: `models.py`.
- Used by: all data sources (writers) and `stream.py` (reader).

**Provider contract:**
- Purpose: Abstract lifecycle and ticker-management interface for any market data source.
- Location: `backend/app/market/interface.py`
- Contains: `MarketDataSource(ABC)` with abstract `start`, `stop`, `add_ticker`, `remove_ticker`, `get_tickers`.
- Depends on: nothing in the project.
- Used by: `simulator.py`, `massive_client.py`, `factory.py`.

**Providers (implementations):**
- Simulator: `backend/app/market/simulator.py`
  - `GBMSimulator` (pure math, numpy-based Cholesky correlation, random shock events) and `SimulatorDataSource` (asyncio loop, 0.5 s interval).
  - Parameters come from `backend/app/market/seed_prices.py` (`SEED_PRICES`, `TICKER_PARAMS`).
- Massive: `backend/app/market/massive_client.py`
  - `MassiveDataSource` polls the Massive REST snapshot API every 15 s (`poll_interval` default). The blocking SDK call runs via `asyncio.to_thread`.

**Selection:**
- Purpose: Choose a provider from the environment.
- Location: `backend/app/market/factory.py`
- Contains: `create_market_data_source(price_cache)`. Returns an unstarted source.
- Depends on: both provider modules, `cache.py`, `interface.py`.

**Transport (SSE):**
- Purpose: Push all cached prices to browsers as Server-Sent Events.
- Location: `backend/app/market/stream.py`
- Contains: `create_stream_router(price_cache)` returning an `APIRouter` with `GET /api/stream/prices`, and the generator `_generate_events`.
- Depends on: `cache.py`, FastAPI.
- Used by: the future FastAPI app (not yet present).

## Data Flow

### Price Update Path (producer to cache)

1. `create_market_data_source(cache)` picks a provider (`backend/app/market/factory.py`).
2. The caller awaits `source.start(tickers)`. The simulator seeds the cache immediately, then starts `_run_loop` (`backend/app/market/simulator.py`). The Massive source performs one poll in `start()` and then schedules `_poll_loop` (`backend/app/market/massive_client.py`).
3. Each cycle writes `PriceCache.update(ticker, price)` (`backend/app/market/cache.py`). The cache computes `previous_price` and `direction`, rounds the price to 2 decimals, and increments `version`.

### SSE Delivery Path (cache to browser)

1. Browser opens `EventSource` on `GET /api/stream/prices` (`backend/app/market/stream.py`).
2. `_generate_events` first yields `retry: 1000`.
3. Every 0.5 s it compares `price_cache.version` with its last-sent version. When it differs, it serializes `get_all()` as one JSON object keyed by ticker and yields `data: {...}`.
4. It checks `request.is_disconnected()` each loop and exits when the client is gone.

### Watchlist Add/Remove (planned contract, partly implemented)

- `add_ticker(ticker)` on the simulator adds the ticker to the GBM model and seeds the cache immediately (`simulator.py`).
- `remove_ticker(ticker)` removes it from the model and from the cache (`simulator.py`, `cache.py`).
- The Massive source updates its tracked set on the next poll cycle (`massive_client.py`).

**State Management:**
- All live price state is process-local memory in `PriceCache`. There is no persistence of prices.
- Simulator state (current prices, Cholesky matrix) is held in `GBMSimulator` instances.

## Key Abstractions

**`PriceUpdate`:**
- Purpose: Single-ticker price snapshot.
- Examples: `backend/app/market/models.py`
- Pattern: Frozen dataclass with derived properties. Use `to_dict()` for JSON.

**`PriceCache`:**
- Purpose: Single source of truth for latest prices.
- Examples: `backend/app/market/cache.py`
- Pattern: Lock-guarded dict plus version counter. Readers take snapshots via `get_all()`.

**`MarketDataSource`:**
- Purpose: Swappable price provider.
- Examples: `backend/app/market/interface.py`, `backend/app/market/simulator.py`, `backend/app/market/massive_client.py`
- Pattern: Strategy via ABC. Each implementation owns one background task.

**`GBMSimulator`:**
- Purpose: Correlated geometric Brownian motion price generator with occasional shock events.
- Examples: `backend/app/market/simulator.py`
- Pattern: Pure computation object wrapped by `SimulatorDataSource`, which owns the asyncio loop.

## Entry Points

**Market data package import:**
- Location: `backend/app/market/__init__.py`
- Triggers: any `from app.market import ...` usage.
- Responsibilities: exports `PriceUpdate`, `PriceCache`, `MarketDataSource`, `create_market_data_source`, `create_stream_router`.

**Market data demo:**
- Location: `backend/market_data_demo.py`
- Triggers: `cd backend && uv run market_data_demo.py`
- Responsibilities: runs a simulator for about 60 s and renders a live Rich dashboard. It is a standalone script, not part of the server.

**Application entry point (planned, missing):**
- Expected by `planning/PLAN.md` as a FastAPI app served by uvicorn on port 8000.
- No `backend/app/main.py` exists in the source tree. Only a stale `backend/app/__pycache__/main.cpython-314.pyc` remains.

## Architectural Constraints

- **Threading:** The application is async (`asyncio`). `PriceCache` uses `threading.Lock` so reads from other threads (for example the `asyncio.to_thread` Massive call path and any future thread-based reader) are safe. Simulator writes happen on the event loop.
- **Global state:** None at module level in `backend/app/market/`. `stream.py` defines a module-level `router = APIRouter(...)` that `create_stream_router` attaches a route to. Calling `create_stream_router` more than once adds duplicate `/prices` routes to that same shared router. Call it once at app startup.
- **Circular imports:** None detected. Import direction is `models` ← `cache` ← `{simulator, massive_client, stream}` ← `factory` ← `__init__`.
- **Single process:** Price state lives in the process. Multi-worker uvicorn would give each worker its own cache and simulator. Run one worker.
- **Single writer:** The design assumes one active data source per cache (`PriceCache` docstring: "one at a time").
- **Storage:** Planned SQLite at `db/finally.db` is not yet implemented. No database code exists in the tree.

## Anti-Patterns

### Module-level router with factory function

**What happens:** `backend/app/market/stream.py` creates `router` at import time and attaches the `/prices` route inside `create_stream_router`.
**Why it's wrong:** Each call adds another handler to the same router. Tests or repeated app construction accumulate duplicate routes.
**Do this instead:** Build the `APIRouter` inside `create_stream_router` and return it. Keep the endpoint closure local, as the function already does for `stream_prices`.

### Mutating state via the simulator for cache writes

**What happens:** `SimulatorDataSource.add_ticker` and `remove_ticker` both mutate the `GBMSimulator` and the `PriceCache` (`backend/app/market/simulator.py`).
**Why it's wrong:** Callers must know to update both places. Forgetting one leaves stale prices or missing tickers.
**Do this instead:** Route all watchlist changes through `MarketDataSource.add_ticker` / `remove_ticker`, which keep both in sync. Do not write to `PriceCache` directly for tickers the source manages.

## Error Handling

**Strategy:** Log and continue inside background loops. Do not let the producer task die.

**Patterns:**
- `SimulatorDataSource._run_loop` wraps each `step()` in `try/except Exception` with `logger.exception` (`backend/app/market/simulator.py`).
- `MassiveDataSource._poll_once` logs and swallows errors so the next interval retries (`backend/app/market/massive_client.py`).
- `stream.py` handles `asyncio.CancelledError` at shutdown and logs the disconnect.

## Cross-Cutting Concerns

**Logging:** Standard `logging.getLogger(__name__)` in each module. Info for lifecycle events, `logger.exception` for loop failures. No logging configuration exists yet.
**Validation:** Not present at the market layer. Ticker validation is expected from the planned API layer.
**Authentication:** None. The plan specifies a single-user app with no login.
**Configuration:** Environment variables read directly with `os.environ` in `backend/app/market/factory.py`. The plan's `OPENROUTER_API_KEY`, `LLM_MOCK`, and `.env` loading are not yet implemented.

---

*Architecture analysis: 2026-11-03*
