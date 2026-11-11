# Testing Patterns

**Analysis Date:** 2026-11-03

## Scope

Only the backend market data subsystem has tests. All tests live under `backend/tests/market/`. There are no frontend tests (`frontend/` is empty) and no E2E tests yet; `test/` at the repo root contains only ignored build artifacts (`node_modules`, `playwright-report`, `test-results`) and no test sources.

## Test Framework

**Runner:**
- pytest (`pytest>=8.3.0`, declared in the `dev` extra of `backend/pyproject.toml`)
- Config: `backend/pyproject.toml` under `[tool.pytest.ini_options]`
- `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_classes = ["Test*"]`, `python_functions = ["test_*"]`
- `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"`

**Async support:**
- pytest-asyncio (`pytest-asyncio>=0.24.0`)
- Async test classes are marked `@pytest.mark.asyncio` (see `backend/tests/market/test_simulator_source.py`, `backend/tests/market/test_massive.py`). Because `asyncio_mode = "auto"` is set, the marker is redundant for `async def` tests; keep it for consistency within a class.

**Assertion Library:**
- Plain `assert` statements (pytest rewriting). No third-party assertion library.
- Float comparisons on exact values are used where the code rounds (`assert update.change == 0.50`, `assert cache.get_price("AAPL") == 190.50`). For GBM math, prefer range/sign checks (`assert prices["AAPL"] > 0`).

**Coverage:**
- pytest-cov (`pytest-cov>=5.0.0`). Configured in `[tool.coverage.run]` (`source = ["app"]`, `omit = ["tests/*"]`) and `[tool.coverage.report]` (excludes `pragma: no cover`, `__repr__`, `NotImplementedError`, `TYPE_CHECKING`, `__main__` blocks).

**Run Commands:**
```bash
cd backend
uv sync --extra dev                              # Install dev dependencies
uv run --extra dev pytest -v                     # Run all tests
uv run --extra dev pytest tests/market/test_cache.py   # Run one file
uv run --extra dev pytest -k "direction"         # Run tests matching a name
uv run --extra dev pytest --cov=app              # Coverage summary
uv run --extra dev pytest --cov=app --cov-report=html  # HTML coverage (see backend/README.md)
uv run --extra dev ruff check app/ tests/        # Lint tests with ruff
```
Watch mode is not configured.

## Test File Organization

**Location:**
- Separate tree: tests are in `backend/tests/`, not co-located with source. Mirror the source subpackage: `app/market/cache.py` maps to `tests/market/test_cache.py`.
- `backend/tests/conftest.py` holds shared fixtures (currently only an `event_loop_policy` fixture).

**Naming:**
- Files: `test_<module>.py`
- Integration-style tests for a class that wraps another component get a `_source` suffix: `test_simulator_source.py` tests `SimulatorDataSource` (the async, cache-writing wrapper), while `test_simulator.py` tests `GBMSimulator` (pure math/state).
- Classes: `Test<Subject>` (`TestPriceCache`, `TestGBMSimulator`, `TestMassiveDataSource`, `TestFactory`, `TestPriceUpdate`)
- Functions: `test_<behavior>` in snake_case, with a one-line docstring: `"""Test that polling updates the cache."""`

**Structure:**
```
backend/tests/
├── __init__.py
├── conftest.py
└── market/
    ├── __init__.py
    ├── test_cache.py            # PriceCache (13 tests)
    ├── test_factory.py          # create_market_data_source env selection (7 tests)
    ├── test_massive.py          # MassiveDataSource with mocked REST client (13 tests)
    ├── test_models.py           # PriceUpdate (11 tests)
    ├── test_simulator.py        # GBMSimulator math and state (17 tests)
    └── test_simulator_source.py # SimulatorDataSource lifecycle with real asyncio (10 tests)
```
Counts are from `planning/MARKET_DATA_SUMMARY.md`; re-verify with `uv run --extra dev pytest --collect-only -q` if they matter.

## Test Structure

**Suite Organization:**
```python
"""Tests for PriceCache."""

from app.market.cache import PriceCache


class TestPriceCache:
    """Unit tests for the PriceCache."""

    def test_update_and_get(self):
        """Test updating and getting a price."""
        cache = PriceCache()
        update = cache.update("AAPL", 190.50)
        assert update.ticker == "AAPL"
        assert cache.get("AAPL") == update
```

**Patterns:**
- Group tests in a class per unit under test; plain functions are not used in `backend/tests/market/`.
- Each test constructs its own collaborators. No shared mutable state between tests. Construct a fresh `PriceCache()` per test.
- Setup is inline at the top of each test; there are no `setup_method` or `setup` hooks.
- Teardown for async sources is an explicit `await source.stop()` at the end of the test body. There is no `yield` fixture for cleanup. Tests that assert on a failing path that could skip teardown should still call stop; double-stop is itself tested (`test_stop_is_clean`).
- Assertions are single-concept per test; multiple related asserts are fine.

**Async Tests:**
```python
@pytest.mark.asyncio
class TestSimulatorDataSource:
    async def test_start_populates_cache(self):
        """Test that start() immediately populates the cache."""
        cache = PriceCache()
        source = SimulatorDataSource(price_cache=cache, update_interval=0.1)
        await source.start(["AAPL", "GOOGL"])

        assert cache.get("AAPL") is not None

        await source.stop()
```
- Use short `update_interval` values (0.05 to 0.1 s) in tests so real loops run quickly.
- Use `await asyncio.sleep(0.3)` to let a few update cycles run, then assert on a monotonic signal such as `cache.version` rather than exact prices.
- Long intervals (`poll_interval=60.0`) prevent the background poll loop from firing during a test that calls `_poll_once()` directly.

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `patch`, `patch.dict`). No pytest-mock plugin.

**Patterns:**

Patch an instance method with `patch.object` and a return value or side effect:
```python
with patch.object(source, "_fetch_snapshots", return_value=mock_snapshots):
    await source._poll_once()

with patch.object(source, "_fetch_snapshots", side_effect=Exception("network error")):
    await source._poll_once()  # Should not raise
```

Build a fake SDK object as a `MagicMock` with the attributes the code reads:
```python
def _make_snapshot(ticker: str, price: float, timestamp_ms: int) -> MagicMock:
    """Create a mock Massive snapshot object."""
    snap = MagicMock()
    snap.ticker = ticker
    snap.last_trade = MagicMock()
    snap.last_trade.price = price
    snap.last_trade.timestamp = timestamp_ms
    return snap
```

Force a malformed object to exercise error handling by setting an attribute to `None` (`bad_snap.last_trade = None` triggers `AttributeError` on `.price`).

Control environment variables with `patch.dict(os.environ, {...}, clear=True)`:
```python
with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key"}, clear=True):
    source = create_market_data_source(cache)
assert isinstance(source, MassiveDataSource)
```

Satisfy internal guards by setting private attributes directly when a test targets a single method:
```python
source._tickers = ["AAPL", "GOOGL"]
source._client = MagicMock()  # Satisfy the _poll_once guard
```
This pattern is used in `backend/tests/market/test_massive.py`. It couples tests to private names; prefer going through `start()` or the public API when practical.

**What to Mock:**
- External SDK clients: the `massive` `RESTClient` is never called in tests. Mock `_fetch_snapshots` or set `_client` to a `MagicMock`.
- Environment variables, via `patch.dict`.
- Failures from the outside world (network errors, malformed payloads).

**What NOT to Mock:**
- `PriceCache`. Use the real thread-safe implementation; it is cheap and in-memory.
- `GBMSimulator` and `SimulatorDataSource`. Tests run the real simulator with real asyncio tasks and short intervals.
- `PriceUpdate`. Construct real instances with explicit timestamps (`timestamp=1234567890.0`) to keep tests deterministic.
- `numpy` Cholesky math. Test through `GBMSimulator` behavior.

## Fixtures and Factories

**Test Data:**
- Inline literals for tickers and prices (`"AAPL"`, `190.50`) are the norm.
- Factory helpers are module-private functions at the top of the test file: `_make_snapshot(...)` in `backend/tests/market/test_massive.py`.
- Timestamps in Massive tests use real-looking Unix milliseconds (`1707580800000`).
- Seed data is imported from the source of truth when a test needs it: `from app.market.seed_prices import SEED_PRICES` in `backend/tests/market/test_simulator.py`.

**Fixtures:**
- `backend/tests/conftest.py` defines `event_loop_policy` returning `asyncio.DefaultEventLoopPolicy()`. This is a legacy pattern for pytest-asyncio. Do not add new uses of `event_loop_policy`; with `asyncio_mode = "auto"` and the function-scoped loop setting, it is not needed.
- No `@pytest.fixture` is used in the market tests today. Prefer a small module-level helper or a fixture only when three or more tests need the same setup.

**Location:**
- Shared fixtures go in `backend/tests/conftest.py`.
- Subsystem helpers stay in the test module that uses them.

## Coverage

**Requirements:** No threshold is enforced in configuration. The market data summary reports 84% overall (`planning/MARKET_DATA_SUMMARY.md`).

**Known gaps (from the summary):**
- `backend/app/market/massive_client.py`: about 56%. The REST methods are mocked, so the real `RESTClient` integration is untested.
- `backend/app/market/stream.py`: the SSE generator has no dedicated test file.

**View Coverage:**
```bash
cd backend
uv run --extra dev pytest --cov=app --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Pure objects: `PriceUpdate` (`test_models.py`), `PriceCache` (`test_cache.py`), `GBMSimulator` (`test_simulator.py`), factory selection (`test_factory.py`).
- Scope: one class, no event loop unless the method is async.

**Integration Tests:**
- Async lifecycle of the simulator with real tasks: `backend/tests/market/test_simulator_source.py`. Despite the docstring, these exercise `SimulatorDataSource` plus `PriceCache` together.
- Massive client with mocked network: `backend/tests/market/test_massive.py`.

**E2E Tests:**
- Not implemented. PLAN.md specifies Playwright tests in `test/` with a `docker-compose.test.yml` and `LLM_MOCK=true`. When added, keep them in `test/` at the repo root, separate from unit tests.

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
class TestMassiveDataSource:
    async def test_poll_updates_cache(self):
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)
        source._tickers = ["AAPL", "GOOGL"]
        source._client = MagicMock()
        with patch.object(source, "_fetch_snapshots", return_value=[...]):
            await source._poll_once()
        assert cache.get_price("AAPL") == 190.50
```

**Error Testing:**
```python
async def test_api_error_does_not_crash(self):
    with patch.object(source, "_fetch_snapshots", side_effect=Exception("network error")):
        await source._poll_once()  # Should not raise
    assert cache.get_price("AAPL") is None
```
Use `pytest.raises` only when the code is expected to raise; the market code mostly swallows and logs errors, so tests assert the absence of a side effect instead.

**Statistical / Property Testing:**
```python
def test_prices_are_positive(self):
    sim = GBMSimulator(tickers=["AAPL"])
    for _ in range(10_000):
        assert sim.step()["AAPL"] > 0
```
Loop-based property checks run many iterations without a seed. Keep iteration counts modest so the suite stays fast.

**Guidance for new tests:**
- Name tests for the behavior, not the implementation.
- Use real `PriceCache` and `GBMSimulator` objects; mock only external SDKs and env vars.
- For any new async source, add a lifecycle test (start, add, remove, stop twice) mirroring `test_simulator_source.py`.
- For any new HTTP route (`/api/*`), use FastAPI's `TestClient` (or `httpx.AsyncClient` with `ASGITransport`) against an app built with the real factories; check status codes, response shape, and error paths.
- New tests for PLAN.md areas not yet built (portfolio P&L, trade validation, LLM response parsing, watchlist and SSE routes) should follow the same class-per-unit layout under `backend/tests/<area>/`.

---

*Testing analysis: 2026-11-03*
