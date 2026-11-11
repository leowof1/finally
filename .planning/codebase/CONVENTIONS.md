<!-- refreshed: 2026-11-03 -->
# Coding Conventions

**Analysis Date:** 2026-11-03

## Scope of Current Code

Only the backend market data subsystem exists. Code lives in `backend/app/market/` (8 modules), with `backend/app/__init__.py` as the package root and `backend/market_data_demo.py` as a standalone Rich demo. `frontend/` is empty. There is no `backend/app/main.py`, no routers besides the SSE router, no database layer, and no LLM integration yet. Conventions below are derived from the existing code and the backend `CLAUDE.md`; treat them as the standard for new code.

## Naming Patterns

**Files:**
- Lowercase snake_case modules named by responsibility: `backend/app/market/cache.py`, `backend/app/market/massive_client.py`, `backend/app/market/seed_prices.py`
- Tests mirror source with a `test_` prefix: `backend/tests/market/test_cache.py` tests `backend/app/market/cache.py`
- Test directories are grouped by subsystem with an `__init__.py`: `backend/tests/market/__init__.py`

**Classes:**
- PascalCase, role-suffixed where a pattern applies: `SimulatorDataSource`, `MassiveDataSource`, `MarketDataSource` (ABC), `GBMSimulator`, `PriceCache`, `PriceUpdate`
- Test classes are `Test*` and group tests by unit: `class TestPriceCache:` in `backend/tests/market/test_cache.py`

**Functions and Methods:**
- snake_case: `create_market_data_source` (`backend/app/market/factory.py`), `create_stream_router` (`backend/app/market/stream.py`), `_fetch_snapshots`, `_poll_once`
- Private helpers use a single leading underscore: `_add_ticker_internal`, `_rebuild_cholesky`, `_pairwise_correlation` (static method in `backend/app/market/simulator.py`)
- Factory functions use the `create_` prefix
- Async methods are `async def` on the same names as the sync interface (`start`, `stop`, `add_ticker`, `remove_ticker`)

**Variables and Constants:**
- Local and instance attributes: snake_case (`self._prices`, `self._cholesky`, `previous_price`)
- Module-level constants: UPPER_SNAKE_CASE (`SEED_PRICES`, `TICKER_PARAMS`, `DEFAULT_PARAMS`, `CORRELATION_GROUPS`, `INTRA_TECH_CORR` in `backend/app/market/seed_prices.py`)
- Class-level constants: UPPER_SNAKE_CASE (`TRADING_SECONDS_PER_YEAR`, `DEFAULT_DT` on `GBMSimulator`)
- Ticker symbols are uppercase strings (`"AAPL"`); `MassiveDataSource.add_ticker` normalizes with `ticker.upper().strip()`

**Types:**
- Dataclasses for value objects: `@dataclass(frozen=True, slots=True) class PriceUpdate` in `backend/app/market/models.py`
- Type hints on all public signatures, using PEP 604 unions (`float | None`, `PriceUpdate | None`) and builtin generics (`dict[str, PriceUpdate]`, `list[str]`)
- Every module starts with `from __future__ import annotations`

## Code Style

**Formatting:**
- Formatter: not configured as a separate tool; ruff is the only linter/formatter declared in `backend/pyproject.toml`
- Line length: 100 (`[tool.ruff] line-length = 100`)
- Target: Python 3.12 (`requires-python = ">=3.12"`, `target-version = "py312"`)
- Double quotes, trailing commas on multi-line calls, two blank lines between top-level definitions
- Section banners inside classes are written as comments: `# --- Public API ---` and `# --- Internals ---` in `backend/app/market/simulator.py` and `backend/app/market/massive_client.py`

**Linting:**
- Tool: ruff, configured in `backend/pyproject.toml`
- Enabled rule sets: `E`, `F`, `I`, `N`, `W` (pycodestyle, pyflakes, isort, pep8-naming, warnings)
- Ignored: `E501` (line length left to the formatter)
- Run with `uv run --extra dev ruff check app/ tests/` from `backend/`

## Import Organization

**Order (observed):**
1. `from __future__ import annotations`
2. Standard library (`asyncio`, `logging`, `math`, `random`, `time`, `os`)
3. Third-party (`numpy as np`, `fastapi`, `massive`)
4. Local relative imports within the package (`from .cache import PriceCache`, `from .interface import MarketDataSource`)

**Path Aliases:**
- None. Inside `backend/app/`, use relative imports (`from .models import PriceUpdate`) within a subpackage.
- Tests and external callers use absolute imports from the package root: `from app.market.cache import PriceCache`, `from app.market import PriceCache, PriceUpdate, MarketDataSource, create_market_data_source`

**Public API:**
- `backend/app/market/__init__.py` is a barrel file. It re-exports the public names and declares `__all__`. Import from `app.market`, not from private modules, in new code outside the subsystem.
- Some tests import from submodules directly (`from app.market.simulator import GBMSimulator`) because they test that module.

## Error Handling

**Patterns:**
- Background loops catch broad exceptions, log with `logger.exception`, and keep running so one failure does not kill the task. Example: `SimulatorDataSource._run_loop` in `backend/app/market/simulator.py` wraps `self._sim.step()` in `try/except Exception` and calls `logger.exception("Simulator step failed")`.
- External API failures are logged and swallowed so the poll loop retries on the next interval: `MassiveDataSource._poll_once` in `backend/app/market/massive_client.py` logs `logger.error("Massive poll failed: %s", e)` and does not re-raise.
- Per-item parsing failures are isolated: malformed snapshots are skipped with `logger.warning` (`except (AttributeError, TypeError)` in `_poll_once`), so one bad ticker does not drop the batch.
- Guard clauses return early instead of raising for "nothing to do" cases: `if not self._tickers or not self._client: return`; `GBMSimulator.add_ticker` returns if the ticker already exists; `remove_ticker` is a no-op for unknown tickers. Interface docstrings require these to be idempotent.
- Division-by-zero is handled by returning a default: `PriceUpdate.change_percent` returns `0.0` when `previous_price == 0`.
- Cancellation is handled explicitly when stopping tasks: `try: await self._task / except asyncio.CancelledError: pass` in both `stop()` methods.
- Do not add defensive wrappers beyond these cases; the project guidance is to avoid overengineering and use exception handling only where a failure is expected to recur.

## Logging

**Framework:** standard library `logging`

**Setup pattern (every module that logs):**
```python
logger = logging.getLogger(__name__)
```

**Patterns:**
- Use `%`-style lazy arguments, not f-strings: `logger.info("Simulator: added ticker %s", ticker)`
- Levels: `logger.info` for lifecycle events (start/stop, add/remove ticker, client connect/disconnect), `logger.debug` for per-tick detail (random events, poll counts), `logger.warning` for skipped data, `logger.error` for failed API calls, `logger.exception` inside `except` blocks where a traceback is useful
- No `print()` in `backend/app/`. Output goes through logging. The Rich demo in `backend/market_data_demo.py` is the only place that renders to the terminal directly, and it is not part of the app package.
- No emojis in log messages (project rule).

## Comments

**When to Comment:**
- Docstrings on every module, class, and public method, written as short imperative or descriptive sentences (`"""Get the latest price for a single ticker, or None if unknown."""`)
- Inline comments explain non-obvious math or constraints, not the obvious: `# 500ms expressed as a fraction of a trading year`, `# Massive timestamps are Unix milliseconds → convert to seconds`, `# Satisfy the _poll_once guard` (tests)
- Keep inline comments sparse (project rule: be sparing outside docstrings)

**JSDoc/TSDoc:**
- Not applicable (backend is Python). Python docstrings are the documentation mechanism.
- Docstring style: triple-double-quoted, one-line summary for simple functions; for classes and interfaces, a summary plus a short description of lifecycle or design. Example: `MarketDataSource` in `backend/app/market/interface.py` includes a `Lifecycle:` code block.
- Math docstrings show the formula inline, as in `GBMSimulator` (`S(t+dt) = S(t) * exp(...)`).

## Function Design

**Size:** Short functions. Most methods are under about 30 lines. `GBMSimulator.step` (~45 lines) is the largest and is the documented hot path. Split helpers out (`_add_ticker_internal`, `_rebuild_cholesky`) rather than growing methods.

**Parameters:**
- Keyword arguments with defaults for tunables: `update_interval: float = 0.5`, `event_probability: float = 0.001`, `poll_interval: float = 15.0`
- Dependencies are injected through constructors (`price_cache: PriceCache`), not module globals. `create_stream_router(price_cache)` is the factory-injection pattern used for FastAPI routes.
- Use keyword arguments at call sites when more than one argument is passed: `self._cache.update(ticker=ticker, price=price)`

**Return Values:**
- Explicit return type annotations on every function, including `-> None`
- Optional lookups return `None` rather than raising: `PriceCache.get`, `GBMSimulator.get_price`
- Return copies of mutable state: `PriceCache.get_all()` returns `dict(self._prices)`, `get_tickers()` returns `list(...)`

## Classes and Data Modeling

- Use `@dataclass(frozen=True, slots=True)` for immutable value objects (`PriceUpdate`). Derived values are `@property` methods, not stored fields (`change`, `change_percent`, `direction`).
- Serialize with an explicit `to_dict()` method returning a plain `dict` for JSON/SSE. Do not rely on `dataclasses.asdict`.
- Abstract interfaces use `abc.ABC` with `@abstractmethod`; concrete sources subclass it (`SimulatorDataSource(MarketDataSource)`, `MassiveDataSource(MarketDataSource)`).
- Use the Strategy pattern for swappable providers, selected by a factory reading the environment (`create_market_data_source` in `backend/app/market/factory.py`).
- Private state uses a single underscore prefix and is never accessed from outside the class (tests set `source._tickers` and `source._client` directly; this is the accepted exception in tests only).
- Thread safety uses `threading.Lock` with `with self._lock:` around every read and write in `PriceCache`.

## Async Conventions

- Background work runs as `asyncio.create_task(..., name="...")` with a descriptive name (`"simulator-loop"`, `"massive-poller"`).
- Blocking synchronous SDK calls run in a thread: `await asyncio.to_thread(self._fetch_snapshots)` in `backend/app/market/massive_client.py`.
- Long-lived generators are typed `AsyncGenerator[str, None]` (`backend/app/market/stream.py`).
- Stop methods cancel the task, await it inside `try/except asyncio.CancelledError`, set the handle to `None`, and are safe to call twice.

## Module Design

**Exports:** Each subpackage exposes its public API through `__init__.py` with `__all__`. Internal helpers stay unexported.

**Barrel Files:** Used in `backend/app/market/__init__.py`. Keep new subpackages consistent with this pattern.

**Configuration:**
- Constants that describe market data live in `backend/app/market/seed_prices.py` as module-level dicts and constants with explanatory comments.
- Runtime configuration comes from environment variables read at the factory layer (`MASSIVE_API_KEY` in `backend/app/market/factory.py`). Read them with `os.environ.get(...)` and normalize with `.strip()`. Never hardcode secrets.

## Project-Level Rules (from CLAUDE.md files)

- Use `uv` for all Python commands: `uv run ...`, `uv add ...`, `uv sync --extra dev`. Never `python3` or `pip install`.
- Prefer short modules, short methods, clear names.
- Favor concise docstrings; be sparing with other comments.
- No emojis in code, print statements, or logs.
- Use the latest library APIs.
- Do not overengineer or program defensively.

## Example: Module Skeleton for New Backend Code

```python
"""One-line summary of the module."""

from __future__ import annotations

import logging

from .cache import PriceCache

logger = logging.getLogger(__name__)


class ExampleService:
    """Short description of responsibility."""

    def __init__(self, price_cache: PriceCache) -> None:
        self._cache = price_cache

    async def run(self) -> None:
        """Do one unit of work."""
        logger.info("Running example service")
```

---

*Convention analysis: 2026-11-03*
