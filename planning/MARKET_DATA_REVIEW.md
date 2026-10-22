# Market Data Backend — Code Review

Review of the market data backend added in commit `3fd3af1` ("Add market data backend: cache, simulator, Massive source, factory, SSE stream, tests"), checked against `PLAN.md` (§6, §8, §12), `MARKET_DATA_DESIGN.md` (the design to implement from), `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md` and `MASSIVE_API.md`.

Reviewed on 2026-10-22.

**Scope:** `backend/app/market/*`, `backend/app/api/stream.py`, `backend/app/main.py`, `backend/pyproject.toml`, `backend/tests/**`.

---

## 1. Summary

The implementation is clean, small and follows `MARKET_DATA_DESIGN.md` almost line for line. The core logic is correct: the cache semantics, GBM math, correlation and event model, Massive parsing and fallback order, the SSE payload and the factory selection. The test suite is well designed: it is deterministic, uses no network, fakes Massive with `httpx.MockTransport`, and checks the statistics.

The suite does not pass as delivered: **1 of 61 tests fails**, because no lockfile is committed and a newer FastAPI was resolved (see §3). The failure is in the test, not in the endpoint, which works correctly when the server runs.

Beyond that, the review found one problem that matters in practice and a few robustness gaps:

| # | Severity | Finding |
|---|---|---|
| F1 | **Medium** | Server shutdown hangs while any SSE client is connected. `docker stop` waits 10s, then kills the process, and the lifespan teardown (`source.stop()`) never runs |
| F2 | **Medium** | No `uv.lock` committed. Dependency versions float, which already caused the failing test |
| F3 | **Medium** | A malformed Massive 200 response makes `start()` raise, so the app won't boot. `add_ticker` also raises unmapped exceptions (500 instead of 503) |
| F4 | Low | `MASSIVE_POLL_SECONDS` is not validated: `0` or a negative value makes a busy request loop, and `abc` crashes startup |
| F5 | Low | `_apply` accepts a quote older than the cached one, so the timestamp and price can go backwards |
| F6 | Low | Calling `start()` twice leaks a background task (both sources) |
| F7 | Low | INFO logs, such as "Market data: simulator", are never shown. No logging config |
| F8 | Low | `.env` is not loaded in local dev (PLAN §5). `MASSIVE_API_KEY` in `.env` is ignored outside Docker |
| T1–T5 | Tests | One test breaks on newer FastAPI. There are also gaps: route headers, malformed responses, lifespan, and a misnamed test |

**Verdict:** a good foundation and close to done. Fix the failing test and commit `uv.lock` before merging further work. Fix F1 and F3 before the Docker/E2E stage. The rest are small hardening items.

---

## 2. Test Results

Command: `cd backend && uv run pytest -v`. Environment: Python 3.13.17, uv 0.13.4. Resolved versions: FastAPI 0.159.1, Starlette 1.9.0, httpx 0.28.1.

```
1 failed, 60 passed in ~1.7s
FAILED tests/api/test_stream.py::test_route_is_registered_on_contract_path - StopIteration
```

- I ran the suite 8 times and got the same result every time. No flakiness seen. The timing-based tests (`test_background_loop_ticks`, `test_loop_survives_tick_error`) take about 50ms each.
- The slowest tests are the statistics tests: correlation (0.63s) and realised volatility (0.44s). Both are fine.
- The suite has 61 tests. The design doc mentions 46, so the implementer added coverage, which is good.

### Live checks (beyond unit tests)

I ran the server with `uv run uvicorn app.main:app` and checked these by hand:

- `GET /api/health` → `{"status":"ok"}` ✅
- `GET /api/stream/prices` → `200`, `content-type: text/event-stream; charset=utf-8`, `cache-control: no-cache`, `x-accel-buffering: no`, then `retry: 1000` and full-snapshot `data:` events every ~500ms for the 10 default tickers. The payload shape matches PLAN §6 exactly ✅
- Shutdown with no clients: about 0.2s ✅. Shutdown with one SSE client open: **still running after 12s** ❌ (F1)

---

## 3. Why the One Test Fails

`tests/api/test_stream.py::test_route_is_registered_on_contract_path` searches `app.routes` for an `APIRoute` with path `/api/stream/prices`. In FastAPI 0.159 (Starlette 1.x), `include_router` adds a single `_IncludedRouter` wrapper to `app.routes` instead of copying the routes into it, so the search finds nothing.

```
app.routes → [Route /openapi.json, Route /docs, ..., _IncludedRouter]
router.routes → [APIRoute /api/stream/prices]
```

The endpoint itself works (live check above). Only the test's introspection is version-specific. `pyproject.toml` allows `fastapi>=0.115`, there is no lockfile, and so `uv` resolved the latest release, not the 0.156 the design was prototyped on.

**Fix**, using public API that works on both versions (verified on 0.159.1):

```python
def test_route_is_registered_on_contract_path():
    app = FastAPI()
    app.include_router(router)
    assert "get" in app.openapi()["paths"]["/api/stream/prices"]
```

`app.url_path_for("stream_prices") == "/api/stream/prices"` also works.

---

## 4. Findings

### F1 — Medium: shutdown hangs while an SSE client is connected

**Where:** `app/api/stream.py` together with uvicorn's graceful shutdown.

**Reproduced:** start uvicorn, open `curl -N /api/stream/prices`, send `SIGTERM`. Uvicorn logs `Waiting for connections to close. (CTRL+C to force quit)` and never exits. `price_events` only stops when the *client* disconnects. Uvicorn waits for open connections before it runs the lifespan shutdown, so `source.stop()` is never reached either.

**Impact:** whenever a browser tab is open (the normal case), `scripts/stop_mac.sh` / `docker stop` waits for the full 10s timeout and then the process is SIGKILLed. Local dev with `--reload` is also affected: every reload waits for open tabs. Nothing is lost today, because the market data is all in memory. Later, a SIGKILL could interrupt the 30s portfolio-snapshot task or a SQLite write.

**Fix options (pick one):**
1. Simplest: run uvicorn with `--timeout-graceful-shutdown 2` (or `timeout_graceful_shutdown=2`) in the Dockerfile `CMD` and the dev command.
2. Make the generator stop on server shutdown: a module-level `asyncio.Event` won't work because the lifespan shutdown runs too late. Use `sse-starlette`'s `EventSourceResponse`, which handles uvicorn's exit signal.

Add a note to `MARKET_DATA_DESIGN.md` §11.2 either way.

### F2 — Medium: no lockfile committed

`backend/uv.lock` is not in the repo. Running the tests created one locally; it is untracked and I left it in place. PLAN §3 and §11 depend on a reproducible lockfile (`uv sync` in the Dockerfile). Without it, every build resolves the newest versions. This has already broken a test (§3), and a future FastAPI/Starlette/httpx major release could break runtime code the same way.

**Fix:** commit `backend/uv.lock`, and consider adding `.python-version` (the Dockerfile targets 3.14 and this machine runs 3.13).

### F3 — Medium: a malformed Massive response escapes the error handling

**Where:** `massive.py` `_fetch` / `parse_snapshot` / `poll` / `add_ticker`.

`poll()` and `add_ticker()` only catch `httpx.HTTPError`. A 2xx response whose body isn't the expected shape raises a different exception:

| Response | Exception | Probe result |
|---|---|---|
| HTML body with 200 (proxy, captive portal, CDN error page) | `json.JSONDecodeError` | `start()` raised |
| JSON that isn't an object (`[1]`) | `AttributeError` (`.get` on list) | `start()` raised |
| An item missing `"ticker"` | `KeyError` (`item["ticker"]`) | `start()` raised |

Consequences:
- `start()` raises, so **the lifespan fails and the app doesn't boot**. This breaks design decision #6: "start() never raises because the upstream is unreachable".
- `add_ticker()` raises an exception the route doesn't map (§11.3 maps only `UnknownTickerError` / `MarketDataUnavailableError`), so `POST /api/watchlist` returns **500** instead of 503.
- In the background loop, `_run`'s broad `except Exception` catches it, so the loop survives. Only startup and add are affected.

**Fix:** treat a bad body as "unavailable", in one place:

```python
async def _fetch(self, tickers: list[str]) -> list[dict]:
    response = await self._client.get(SNAPSHOT_PATH, params={"tickers": ",".join(tickers)})
    response.raise_for_status()
    try:
        items = response.json().get("tickers") or []
    except (ValueError, AttributeError) as exc:
        raise httpx.DecodingError(f"Unexpected snapshot body: {exc}") from exc  # an httpx.HTTPError
    return [i for i in items if isinstance(i, dict) and i.get("ticker")]
```

Then add tests: HTML 200, non-object JSON, and an item without `ticker`. Each should leave `start()` succeeding and make `add_ticker()` raise `MarketDataUnavailableError`.

### F4 — Low: `MASSIVE_POLL_SECONDS` is not validated

`factory.py:20` → `float(os.environ.get("MASSIVE_POLL_SECONDS") or DEFAULT_POLL_SECONDS)`.

| Value | Result |
|---|---|
| `0` | `poll_interval=0.0`, so the loop polls back-to-back (hundreds of requests/s until 429) |
| `-5` | same (`asyncio.sleep` with a negative value returns immediately) |
| `abc`, `15s` | `ValueError`, so the app doesn't start, with an unclear traceback |

**Fix:** parse defensively, clamp to a floor (e.g. `max(interval, 1.0)`; PLAN says paid plans use 2–15s), and log a warning that falls back to 15s on bad input.

### F5 — Low: the cache can go backwards in time

`MassiveSource._apply` skips a quote only when `old.timestamp == quote.timestamp`. A quote *older* than the cached one is still written. Probe: applying a newer quote and then an older one leaves the older price in the cache, `timestamp` moves backwards, and `previous_price`/`direction` are computed against the newer price.

This can happen when a slow poll response comes back after an `add_ticker` refetch for the same ticker (the "tracked but unpriced" path, design decision #9), or if Massive serves a stale replica. The frontend dedupes on `timestamp` *changes*, so a backwards step looks like a new tick.

**Fix:** `if old and quote.timestamp <= old.timestamp: return`. Add a test that applies a newer quote, then an older one.

### F6 — Low: calling `start()` twice leaks a task

Both `SimulatorSource.start` and `MassiveSource.start` overwrite `self._task` without checking it. Probe: `start(); start(); stop()` leaves one `market-simulator` task running forever, which doubles the tick rate. Nothing calls `start()` twice today, but it is an easy guard to add: `if self._task: raise RuntimeError("already started")`, or return early.

### F7 — Low: INFO logs are never shown

`main.py` configures no logging. Uvicorn only configures its own `uvicorn.*` loggers, so the root logger stays at WARNING. The factory's `"Market data: simulator"` / `"Massive, polling every 15s"` lines are therefore dropped (confirmed: absent from the server log). Massive WARNINGs still appear, but through Python's last-resort handler, with no timestamp or logger name. For a project whose debugging story is "the log says why" (design §9.4), add `logging.basicConfig(level=logging.INFO, format=...)` in `main.py`.

### F8 — Low: `.env` not loaded in local development

PLAN §5: "In local development, the backend loads `.env` from the project root." Design §10 suggests `python-dotenv` in `main.py`. This isn't implemented, and `python-dotenv` isn't a dependency. As a result, `MASSIVE_API_KEY` in `.env` is silently ignored under `uv run uvicorn` and the simulator is used. This may belong to the backend/API agent, but it decides which market source runs, so it is listed here.

---

## 5. Test Suite Review

**Strengths:**
- Determinism: a seeded `random.Random` for the simulator, `MockTransport` for Massive, and no sleeps except two short loop tests.
- Statistics are checked properly: realised vol within 5% of σ over 100k steps; correlation 0.6 / 0.3 ± 0.05 over 50k steps; events bounded at 2–5% with `dt=0`.
- The conformance test is parametrized over both sources, as `PLAN.md` §12 requires.
- Security check: the API key is never in the URL (`FakeMassive` asserts this) and never in the logs.
- It goes beyond the design: refetch when tracked but unpriced, 401/403/429 log hints, empty start with no request, and the empty-cache SSE event.

**Gaps and issues:**

| # | Issue | Suggestion |
|---|---|---|
| T1 | `test_route_is_registered_on_contract_path` breaks on FastAPI ≥ 0.159 | Use `app.openapi()["paths"]` (§3) |
| T2 | No test exercises the real route (status, `text/event-stream`, `Cache-Control`, `X-Accel-Buffering`) | Call `stream_prices(request)` with a fake `Request` (`app.state.prices` set, `is_disconnected` returning True after one event), or use `httpx.ASGITransport` and read the first chunk |
| T3 | No tests for malformed Massive bodies (F3) or out-of-order quotes (F5) | Add them with the fixes |
| T4 | `main.py` lifespan is untested (start/stop wiring, `app.state.prices` / `app.state.market`) | `with TestClient(app) as c: c.get("/api/health")`, then check `app.state.market.tickers == set(DEFAULT_TICKERS)` |
| T5 | `test_stop_is_idempotent_for_task` calls `stop()` only once; `test_tickers_is_read_only` only checks the type | Call `stop()` twice. Assert that `src.tickers` doesn't change after modifying a copy, or that there is no `add` attribute |
| — | `describe_error` for non-status errors (timeouts/connect errors) isn't covered | Small parametrized test with `httpx.ConnectTimeout` |

---

## 6. Conformance to the Specification

| Requirement | Status | Notes |
|---|---|---|
| Two sources, one interface (`MarketDataSource` ABC) | ✅ | `source.py`; conformance test covers both |
| `MASSIVE_API_KEY` set/non-empty → Massive, else simulator (whitespace counts as empty) | ✅ | `factory.py`; tested with unset / `""` / `"   "` |
| Cache holds `price`, `previous_price`, `reference_price`, `timestamp` | ✅ | Frozen, slotted `PriceEntry` |
| `reference_price` = seed (sim) / `prevDay.c` (Massive) | ✅ | |
| Ticker normalisation `^[A-Z][A-Z.]{0,9}$`, uppercased | ✅ | `tickers.py`, with `fullmatch` and `strip` |
| Simulator: GBM, ~500ms, realistic seeds, unknown → $50–300 at σ=0.30 | ✅ | Matches MARKET_SIMULATOR.md; per-ticker drift added (design #8) |
| Increment 2: correlated moves + 2–5% events | ✅ | Constructor knobs; tests pass |
| Massive: one multi-ticker snapshot per poll, never per ticker | ✅ | Sorted, comma-joined; tested |
| Massive: no data on add → `UnknownTickerError` (→ 400) | ✅ | Upstream failure → `MarketDataUnavailableError` (→ 503) |
| Massive: unchanged snapshots not rewritten (timestamp only moves on real updates) | ✅ / ⚠️ | Equal timestamps are skipped; older timestamps are not (F5) |
| Key sent in header, not URL | ✅ | Tested |
| `start()` never raises because of the upstream | ⚠️ | True for HTTP errors; not for malformed 2xx bodies (F3) |
| `stop()` awaits the task, is idempotent, closes the HTTP client | ✅ | Massive `stop()` twice verified OK |
| SSE `GET /api/stream/prices`, full snapshot every ~500ms, exact payload, ISO `Z` timestamps | ✅ | Verified live |
| `direction` vs previous (as displayed), `change_percent` vs reference, no `-0.0` | ✅ | |
| Backend loads `.env` in local dev | ❌ | F8 |
| Reproducible lockfile | ❌ | F2 |
| Not yet in scope (routes owned by later work): watchlist routes, `untrack_if_unused`, trade fill, DB-backed `load_tracked_tickers` | — | `main.py` uses a placeholder `DEFAULT_TICKERS`, labelled clearly |

---

## 7. Code Quality Notes

These are not defects. They are worth knowing for the agents who build on this code.

- **Structure is good:** pure parts (`GBMModel`, `parse_snapshot`, `price_events`) are kept separate from asyncio/I-O parts, which makes testing easy. The public API is re-exported from `app.market`, and nothing outside the package imports `simulator` or `massive`.
- **Concurrency reasoning holds:** everything runs on one event loop, the simulator `tick()` has no `await`, Massive writes after its `await` returns, entries are immutable, and `snapshot()` is a copy. No locks are needed.
- `PriceEntry.change_percent` / `direction` are recomputed on every SSE event for every client. That is negligible at 10–50 tickers and a few clients, so no action is needed.
- In the simulator, a removed ticker that is re-added restarts from its seed (known tickers) or a new random price (unknown tickers), and gets a new `reference_price`. This is acceptable and consistent with the "since server start" meaning, but it is a visible jump if a user sells their last share of a non-watched ticker and adds it back. Worth a line in the design doc.
- `parse_snapshot` treats a price of `0` as missing (`or` chains). This is intentional for the overnight reset and correct for equities.
- `main.py`'s `/api/health` lives in the market-wiring module. Fine for now; move it when the API routers land.

---

## 8. Recommended Actions (in order)

1. Fix T1 (one-line test change) and commit `backend/uv.lock` (F2), so the suite is green and reproducible.
2. F3: harden `_fetch` against malformed bodies and add tests.
3. F1: set `--timeout-graceful-shutdown` in the Dockerfile/dev command (or switch to `sse-starlette`) and document it.
4. F4, F5, F6: small guards, each with a test.
5. F7, F8: logging config and `.env` loading in `main.py` when the backend/API agent wires up the rest of the app.
6. T2, T4, T5: fill the remaining test gaps.

---

## 9. Resolution (2026-10-22, branch `fix/market-data-review`)

All findings are fixed. `uv run pytest` now runs **81 passed** on Python 3.14.4 (and on 3.13), stable across repeated runs.

| # | Fix | Tests |
|---|---|---|
| F1 | `stream.py` uses `sse_starlette.EventSourceResponse` with a `shutdown_event`, so the generator ends cleanly when uvicorn exits. Live check: SIGTERM with an SSE client connected now shuts down in ~0.2–0.4s, with no ASGI error and the client stream closing normally (it hung indefinitely before). Design §11.2 updated | `test_stream_route_headers_and_first_events` |
| F2 | `backend/uv.lock` committed (`be39914`). No `.python-version`: pyenv also reads that file, and on this machine pyenv has no 3.14, so the `python3` shim hangs inside `backend/`. The Dockerfile pins 3.14; locally, create the venv with `uv sync --python /usr/bin/python3.14` | — |
| F3 | `_fetch` raises `httpx.DecodingError` for non-snapshot 200 bodies and drops items without `ticker` | `test_malformed_body_is_unavailable` (4 cases), `test_malformed_body_on_add_is_unavailable_not_500` |
| F4 | `poll_interval_from_env()`: bad values → 15s with a warning; `<1s`/`nan` → 1s floor with a warning | `test_factory_poll_interval_is_validated` (7 cases) |
| F5 | `_apply` skips quotes with `timestamp <= cached timestamp` | `test_older_quote_does_not_overwrite_newer` |
| F6 | `start()` raises `RuntimeError` if already started (both sources) | `test_start_twice_raises` (both sources + Massive) |
| F7 | `logging.basicConfig(level=INFO)` in `main.py`; "Market data: simulator" now appears in the server log | live check |
| F8 | `main.py` loads the project-root `.env` via `python-dotenv` (`override=False`) | live probe |
| T1 | Route test uses `app.openapi()["paths"]` | `test_route_is_registered_on_contract_path` |
| T2 | Real route tested: media type, `Cache-Control`, `X-Accel-Buffering`, first events | `test_stream_route_headers_and_first_events` |
| T3 | See F3/F5 | — |
| T4 | Lifespan wiring tested with `TestClient` (start, `app.state`, stop on exit) | `tests/test_main.py` |
| T5 | `stop()` called twice; `tickers` immutability checked properly; `describe_error` for transport errors | `test_stop_is_idempotent_for_task`, `test_tickers_is_read_only`, `test_describe_error_for_transport_errors` |

New runtime dependencies: `sse-starlette`, `python-dotenv`.

Local dev note: on this machine uv's interpreter discovery can hang on a pyenv shim when it searches for a Python. If `uv sync` stalls with no output, pass the interpreter explicitly: `uv sync --python /usr/bin/python3.14`.
