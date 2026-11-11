# Codebase Concerns

**Analysis Date:** 2026-11-03

## Tech Debt

**Build/test artifacts committed to git (`test/node_modules`, Playwright reports):**
- Issue: 212 files under `test/node_modules/` (Playwright, `@types/node`, TypeScript) and 2 files under `test/playwright-report/` / `test/test-results/` are tracked in git. The root `.gitignore` does not exclude `node_modules/` or the test output directories, and `test/` has no `package.json` in git.
- Files: `test/node_modules/`, `test/playwright-report/`, `test/test-results/`, `.gitignore`
- Impact: Bloats the repo, creates platform-specific binaries churn (e.g. `@typescript/typescript-darwin-arm64`), and makes diffs noisy. The E2E harness has no tracked source, so the `node_modules` is the only thing present.
- Fix approach: `git rm -r --cached test/node_modules test/playwright-report test/test-results`, add `node_modules/`, `playwright-report/`, `test-results/` to `.gitignore`, then commit the E2E `package.json`/config once it exists.

**Next.js build output committed under `backend/static/`:**
- Issue: 24 files of a Next.js/Turbopack static export (`backend/static/index.html`, `backend/static/_next/static/chunks/*.js`, `*.txt` RSC payloads) are tracked. There is no `frontend/` source in the repo (`frontend/` is an empty directory), so these artifacts have no source of truth.
- Files: `backend/static/`, `frontend/`
- Impact: Stale, unreviewable bundles; the PLAN's Docker flow copies a freshly built export into `static/`, so committed files will be silently overwritten or mismatched. Hashed chunk names make diffs meaningless.
- Fix approach: Remove `backend/static/` from git until `frontend/` exists; have the Dockerfile's Node stage produce it. Add `backend/static/` to `.gitignore`.

**No application entry point yet, so the market subsystem is unmounted:**
- Issue: There is no `backend/app/main.py`. `create_stream_router` and `create_market_data_source` are only exercised by tests and `backend/market_data_demo.py`. Nothing starts the FastAPI app, the market data source, or the lifespan hooks.
- Files: `backend/app/__init__.py` (empty), `backend/app/market/__init__.py`, `backend/market_data_demo.py`
- Impact: The SSE endpoint `/api/stream/prices` cannot be served; the PLAN's `/api/*` routes, DB initialization, and static mount are all absent. Integration risk is deferred until the first app wiring.
- Fix approach: Add `backend/app/main.py` with a lifespan that creates one `PriceCache`, calls `create_market_data_source(cache)`, `start(tickers)`, and `stop()` on shutdown, and mounts `create_stream_router(cache)`. Keep this as the single wiring point.

**Missing repo scaffolding from the PLAN:**
- Issue: No `Dockerfile`, no `docker-compose.yml`, no `scripts/` (start/stop), no `.env.example`, no `db/.gitkeep`, no `frontend/` source, and no `backend/db/` schema or seed module. `README.md` references none of these.
- Files: repository root (`planning/PLAN.md` section 4 lists them)
- Impact: The "single command" first-launch experience in the PLAN cannot run. `.env.example` is absent, so the required `OPENROUTER_API_KEY` and `MASSIVE_API_KEY` names are only discoverable from the PLAN.
- Fix approach: Add these in the phases that own them; add `.env.example` early since it costs nothing and documents the contract.

**Global mutable router in `create_stream_router`:**
- Issue: `create_stream_router` decorates a module-level `router` (`app/market/stream.py`) on every call. Each call appends another `/api/stream/prices` route whose closure captures that call's `price_cache`.
- Files: `backend/app/market/stream.py` (`router`, `create_stream_router`)
- Impact: Verified: calling the factory twice yields `['/api/stream/prices', '/api/stream/prices']` on the shared router. FastAPI serves the first registered route, so a second app or test instance silently streams from the first cache. This contradicts the docstring's "without globals" claim.
- Fix approach: Create the `APIRouter` inside `create_stream_router` (move `router = APIRouter(...)` into the function body) so each call returns an independent router.

**Simulator accepts un-normalized ticker symbols:**
- Issue: `GBMSimulator` stores tickers exactly as given, while `MassiveDataSource.add_ticker` and `remove_ticker` call `.upper().strip()`. Verified: `GBMSimulator(['aapl', 'AAPL'])` keeps both `'aapl'` and `'AAPL'` as separate tickers, each with its own price series.
- Files: `backend/app/market/simulator.py` (`GBMSimulator._add_ticker_internal`, `SimulatorDataSource.add_ticker`), `backend/app/market/massive_client.py` (`add_ticker`, `remove_ticker`)
- Impact: The two implementations behave differently for the same input. Watchlist code that does not normalize would create duplicate tickers in dev and not in prod (or vice versa). Unknown tickers also get a random seed price in `[50, 300]` with no validation, which produces fake prices for typos.
- Fix approach: Normalize with `.upper().strip()` at the `MarketDataSource` boundary (or in a shared helper) before both implementations see the value. Decide whether unknown symbols are rejected at the watchlist API layer.

**Shared mutable parameter dicts:**
- Issue: `GBMSimulator._add_ticker_internal` assigns `TICKER_PARAMS.get(ticker, dict(DEFAULT_PARAMS))`. For known tickers this is the shared module-level dict itself, not a copy.
- Files: `backend/app/market/simulator.py` (`_add_ticker_internal`), `backend/app/market/seed_prices.py`
- Impact: Any future code that mutates a simulator's `_params[ticker]` would also change the global defaults for every simulator instance. Low risk today because nothing mutates it.
- Fix approach: Use `dict(TICKER_PARAMS.get(ticker, DEFAULT_PARAMS))`.

**Unused runtime dependency in the production group:**
- Issue: `rich>=13.0.0` is a core dependency in `backend/pyproject.toml`, but it is only imported by `backend/market_data_demo.py`.
- Files: `backend/pyproject.toml`, `backend/market_data_demo.py`
- Impact: Ships a terminal-UI library into the production container. Small, but it's the kind of drift that accumulates.
- Fix approach: Move `rich` to the `dev` optional group or a `demo` group, and run the demo with `uv run --extra demo`.

**Deprecated test fixture:**
- Issue: `backend/tests/conftest.py` defines an `event_loop_policy` fixture returning `asyncio.DefaultEventLoopPolicy()`. The test run emits a DeprecationWarning from this file for every test module (73 warnings in the suite).
- Files: `backend/tests/conftest.py`
- Impact: Noise now; will break when Python 3.16 removes the API. `pytest-asyncio` already runs with `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"` in `backend/pyproject.toml`, so the fixture is likely redundant.
- Fix approach: Delete the fixture and rely on the pytest-asyncio config; re-run the suite to confirm.

## Known Bugs

**Removed Massive tickers can reappear in the cache after an in-flight poll:**
- Symptoms: After `remove_ticker("X")`, `X` can be written back into `PriceCache` by a poll that started before the removal. The SSE stream then keeps sending a removed watchlist ticker until the next removal.
- Files: `backend/app/market/massive_client.py` (`_poll_once`, `_fetch_snapshots`, `remove_ticker`)
- Trigger: `_poll_once` reads `self._tickers` inside `_fetch_snapshots` on a worker thread (`asyncio.to_thread`). A `remove_ticker` call during the HTTP round trip runs `self._cache.remove(ticker)`, then the poll resumes and calls `self._cache.update(...)` for every snapshot it received. Not reproduced by a test; inferred from code ordering (needs a targeted test to confirm).
- Workaround: None. Re-removing the ticker clears it.

**Simulator `add_ticker` before `start()` is silently dropped:**
- Symptoms: `SimulatorDataSource.add_ticker` does nothing if `self._sim` is `None`. The ticker is not tracked and no error is raised.
- Files: `backend/app/market/simulator.py` (`SimulatorDataSource.add_ticker`)
- Trigger: Calling `add_ticker` on an unstarted source. `MarketDataSource.add_ticker` documents "the next update cycle will include this ticker", which is false in this case.
- Workaround: Call `start()` first. The Massive implementation does not have this problem because it stores the ticker in a list.

**Many per-tick direction flags are "flat" because of cent rounding:**
- Symptoms: The UI's green/red flash is driven by `PriceUpdate.direction`, which compares prices already rounded to cents. Measured on AAPL over 2,000 simulator ticks with events disabled: `{'down': 685, 'flat': 647, 'up': 668}`, so about a third of ticks show no movement. Cheaper or lower-volatility tickers will be flat more often.
- Files: `backend/app/market/cache.py` (`PriceCache.update`, `round(price, 2)`), `backend/app/market/models.py` (`direction`), `backend/app/market/simulator.py` (`step`, `DEFAULT_DT`)
- Trigger: Normal operation with the default simulator. Not a crash, but it affects the PLAN's flash-on-change requirement.
- Workaround: None in code. Decide whether direction should compare unrounded values or whether a flash should use a tolerance.

**Massive per-ticker parse failures log a warning on every poll:**
- Symptoms: Any ticker with `last_trade` missing (common outside market hours or for halted names) raises `AttributeError` that is caught and logged as a warning on every poll cycle, with no backoff or suppression.
- Files: `backend/app/market/massive_client.py` (`_poll_once`, the per-snapshot `except (AttributeError, TypeError)`)
- Trigger: A watched ticker with no last trade in the snapshot response. Not reproduced against the live API (no key used during analysis).
- Workaround: None. Log noise only.

## Security Considerations

**Secrets file present at repository root:**
- Risk: A `.env` file exists at the repo root (`/Users/.../finally/.env`). It is correctly listed in `.gitignore` (line 138) and is not tracked, but there is no `.env.example` to document its keys. Its contents were not read during this analysis.
- Files: `.env` (root, gitignored), `.gitignore`
- Current mitigation: `.env` is gitignored; `backend/` reads the key only via `os.environ` in `backend/app/market/factory.py`.
- Recommendations: Add a committed `.env.example` with placeholder values. Make sure the Dockerfile does not `COPY` the `.env` into the image (use `--env-file` at run time, as the PLAN specifies).

**Market data client has no key validation or error redaction:**
- Risk: `MassiveDataSource._poll_once` logs `str(e)` on any failure. Massive client exceptions may echo request URLs, and the API key is passed as a constructor argument, so a future change that logs the client or request object could leak it.
- Files: `backend/app/market/massive_client.py` (`_poll_once`, `start`)
- Current mitigation: Logs only the exception message; the key is not logged directly.
- Recommendations: Keep logging exception types and messages only, never the client object. Add a test asserting the key does not appear in log output.

**No authentication or rate limiting on the planned API:**
- Risk: The PLAN explicitly has no login, and the SSE endpoint `/api/stream/prices` is unauthenticated. Once the app is served on `0.0.0.0:8000` in Docker, anyone on the network can open unlimited SSE connections; each connection runs its own loop.
- Files: `backend/app/market/stream.py` (`stream_prices`, `_generate_events`)
- Current mitigation: Single-user local app per the PLAN. No connection cap exists.
- Recommendations: Bind to `127.0.0.1` in the start script by default, or add a simple connection cap before exposing the container beyond localhost.

**Planned LLM endpoint will auto-execute trades with no confirmation:**
- Risk: The PLAN specifies auto-execution of LLM-proposed trades and watchlist changes. There is no code yet, so the validation boundary is undefined. Prompt-injected or malformed LLM output could trade arbitrary tickers or quantities.
- Files: Not yet implemented (planned `POST /api/chat`)
- Current mitigation: PLAN requires the same validation as manual trades (cash and share sufficiency).
- Recommendations: When implemented, validate trade side, ticker (against a known set), quantity bounds, and integer/fractional rules server-side, independent of the LLM output. Parse structured output strictly and reject unknown fields.

## Performance Bottlenecks

**SSE sends the full price map to every client on every change:**
- Problem: `_generate_events` calls `price_cache.get_all()` (a dict copy under lock) and re-serializes every ticker to JSON each time the cache version changes. With the simulator, that is every 0.5 s.
- Files: `backend/app/market/stream.py` (`_generate_events`), `backend/app/market/cache.py` (`get_all`)
- Cause: Each connected client runs its own polling loop at 0.5 s and re-serializes the whole map. Cost scales with clients times tickers.
- Improvement path: Acceptable for single-user. If needed, serialize once per version in a shared broadcaster and fan out to subscribers, or send only changed tickers.

**Massive polling latency and rate-limit sensitivity:**
- Problem: On the free tier (5 calls/min) the poller uses a 15 s interval, so prices can be up to 15 s stale. `add_ticker` does not trigger an immediate poll, so a newly added ticker waits up to one full interval to get a price.
- Files: `backend/app/market/massive_client.py` (`poll_interval`, `add_ticker`, `_poll_loop`)
- Cause: Fixed-interval poll with no on-demand refresh; the interval is hard-coded at construction.
- Improvement path: Trigger a one-off poll from `add_ticker` (rate-limit aware), and read the interval from configuration rather than the constructor default.

**Simulator recomputes the full Cholesky decomposition on every add or remove:**
- Problem: `GBMSimulator._rebuild_cholesky` rebuilds an O(n²) correlation matrix and decomposition each time a ticker is added or removed.
- Files: `backend/app/market/simulator.py` (`_rebuild_cholesky`, `add_ticker`, `remove_ticker`)
- Cause: The matrix is rebuilt from scratch rather than extended.
- Improvement path: Not a real problem at the stated n < 50. Leave as-is unless the watchlist grows substantially.

## Fragile Areas

**Cholesky decomposition with no positive-definiteness fallback:**
- Files: `backend/app/market/simulator.py` (`_rebuild_cholesky`, `_pairwise_correlation`), `backend/app/market/seed_prices.py` (`INTRA_TECH_CORR`, `INTRA_FINANCE_CORR`, `CROSS_GROUP_CORR`, `TSLA_CORR`)
- Why fragile: `np.linalg.cholesky` raises `LinAlgError` if the correlation matrix is not positive definite. The current constants (0.3 to 0.6) keep it valid, but changing them, or adding a large number of tickers with mixed correlations, can break it. Any `LinAlgError` escapes `add_ticker`/`remove_ticker` and is not caught there. The step loop does catch exceptions, so the failure would stop price updates silently after a log entry.
- Safe modification: Keep correlation constants below about 0.6 and run `tests/market/test_simulator.py` after changes. Consider validating the matrix in `_rebuild_cholesky` and failing loudly on insert.
- Test coverage: `backend/tests/market/test_simulator.py` checks that the decomposition is rebuilt on add (`test_cholesky_rebuilds_on_add`), but no test asserts positive-definiteness or covers the failure path.

**Global RNG state in the simulator:**
- Files: `backend/app/market/simulator.py` (`step`, `_add_ticker_internal`) using `np.random.standard_normal` and the `random` module
- Why fragile: Both use process-global random state, so simulator output cannot be seeded per instance. Tests that depend on price sequences can become order-dependent.
- Safe modification: Inject a `np.random.Generator` and a `random.Random` into `GBMSimulator` and use them everywhere.
- Test coverage: Tests assert statistical or structural properties rather than exact sequences, which mitigates this.

**Cache and simulator own separate sources of truth for tickers:**
- Files: `backend/app/market/simulator.py` (`GBMSimulator._tickers`, `_prices`), `backend/app/market/cache.py` (`PriceCache._prices`), `backend/app/market/massive_client.py` (`_tickers`)
- Why fragile: The active ticker set lives in the data source and the cache separately. `remove_ticker` must update both, and `add_ticker` only seeds the cache if the source is started. Any path that updates one but not the other leaves a ghost ticker in the SSE output.
- Safe modification: Route all watchlist changes through the `MarketDataSource` methods, never directly through `PriceCache`.

**Interface contract is documented but not enforced:**
- Files: `backend/app/market/interface.py` (`start` docstring: "Calling start() twice is undefined behavior")
- Why fragile: `SimulatorDataSource.start` overwrites `_sim` and creates another task, leaking the previous `_run_loop` task. `MassiveDataSource.start` does the same with `_task`.
- Safe modification: Guard `start()` with a flag and raise on double start, or make it idempotent.

## Scaling Limits

**Single in-process price cache and single event loop:**
- Current capacity: One process, one `PriceCache`, one simulator/poller task, one SSE loop per client. Tested with 10 default tickers.
- Limit: Multiple uvicorn workers would each run their own simulator and cache, so clients on different workers see different prices. Adding workers or horizontal scaling will break price consistency.
- Scaling path: Keep one worker (`uvicorn --workers 1`) as the PLAN assumes, or move the cache to a shared store before scaling out.

**Massive free-tier rate limit:**
- Current capacity: 5 calls per minute on the free tier. The poller makes one snapshot call per interval for all tickers, so capacity does not depend on watchlist size up to the URL limit.
- Limit: Very large watchlists produce a long `tickers=` query string on `get_snapshot_all`; no chunking exists. Paid-tier throttling (429) is only logged.
- Scaling path: Chunk tickers if needed; add backoff on 429 responses.

## Dependencies at Risk

**`massive` SDK surface used directly:**
- Risk: `backend/app/market/massive_client.py` depends on `massive.RESTClient`, `massive.rest.models.SnapshotMarketType`, and attributes `snap.last_trade.price` and `snap.last_trade.timestamp`. Those are internal attribute paths of a third-party SDK at `massive>=1.0.0`.
- Impact: An SDK change to the snapshot model would be caught only at runtime, since `_poll_once` swallows `AttributeError` as a warning and the cache silently stops updating.
- Migration plan: Pin the version in `backend/uv.lock` (already locked) and add a contract test using a recorded response. The current `tests/market/test_massive.py` mocks the client, so it would not catch SDK drift.

**`pytest-asyncio` and `asyncio` deprecation:**
- Risk: The deprecated `asyncio.DefaultEventLoopPolicy` fixture (see Tech Debt) is a forward-compatibility risk.
- Impact: Test warnings now; breakage when the API is removed.
- Migration plan: Remove the fixture as described above.

## Missing Critical Features

**Portfolio, trade execution, and watchlist persistence:**
- Problem: No SQLite schema, no `backend/db/` module, no lazy initialization, no portfolio/trade endpoints, no `portfolio_snapshots` background task. The watchlist exists only in memory inside the market data source.
- Blocks: Trade execution, P&L chart, positions table, watchlist persistence across restarts, and the LLM context loader (which needs cash and positions).

**LLM chat integration:**
- Problem: No LiteLLM/OpenRouter client, no `POST /api/chat`, no structured-output schema, no `LLM_MOCK` path, and no `chat_messages` table.
- Blocks: The AI assistant, auto-trade execution, and all mocked E2E chat tests in the PLAN.

**Frontend:**
- Problem: `frontend/` is an empty directory. No Next.js project, no `EventSource` client, no charts, no trade bar.
- Blocks: Any visible deliverable and all E2E tests in `test/`, which currently have no source files tracked.

## Test Coverage Gaps

**Massive poller race and failure paths:**
- What's not tested: Removal during an in-flight poll (see Known Bugs), double `start()`, `stop()` during `to_thread`, and 429 behavior.
- Files: `backend/app/market/massive_client.py`, `backend/tests/market/test_massive.py`
- Risk: The ghost-ticker bug above would ship unnoticed.
- Priority: High

**SSE endpoint behavior:**
- What's not tested: No tests under `backend/tests/` import `app/market/stream.py` or exercise `/api/stream/prices`. Duplicate-route registration and disconnect handling are untested.
- Files: `backend/app/market/stream.py`, no matching file in `backend/tests/market/`
- Risk: The shared-router bug and any framing error in the SSE output would not be caught before the frontend depends on it.
- Priority: High

**Ticker normalization across implementations:**
- What's not tested: Simulator with lowercase or whitespace tickers; cross-implementation parity for `add_ticker`/`remove_ticker`.
- Files: `backend/tests/market/test_simulator_source.py`, `backend/tests/market/test_massive.py`
- Risk: Watchlist behavior diverges between simulator (default) and Massive (optional) modes, and the divergence is only seen in production with a real key.
- Priority: Medium

**Cholesky failure and matrix validity:**
- What's not tested: Behavior when the correlation matrix is not positive definite, and the matrix for mixed or large watchlists.
- Files: `backend/app/market/simulator.py`
- Risk: A future constant change could stop the simulator silently.
- Priority: Medium

**Frontend and E2E:**
- What's not tested: All of it. No frontend tests, no Playwright specs, no `docker-compose.test.yml`.
- Files: `frontend/`, `test/`
- Risk: Nothing validates the first-launch experience in the PLAN.
- Priority: High once the frontend exists

---

*Concerns audit: 2026-11-03*
