# External Integrations

**Analysis Date:** 2026-11-03

## APIs & External Services

**Market Data:**
- Massive (Polygon.io successor) REST API - real-time/snapshot prices for the watchlist union
  - Implemented in: `backend/app/market/massive_client.py` (`MassiveDataSource`)
  - SDK/Client: `massive` package, `RESTClient(api_key=...)` and `SnapshotMarketType` from `massive.rest.models`
  - Auth: `MASSIVE_API_KEY` env var (read in `backend/app/market/factory.py`)
  - Access pattern: REST polling (not WebSocket). Default `poll_interval=15.0` s (free tier, 5 calls/min); paid tiers documented at 2-5 s. The sync SDK call runs in a worker thread so the asyncio loop is not blocked.
  - Failures are logged and the poll loop retries on the next interval (`_poll_once` does not re-raise).
  - Status: implemented and unit-tested (`backend/tests/market/test_massive.py`); not exercised against the live API in this repo.

**LLM Provider (planned, not implemented):**
- OpenRouter (via LiteLLM) - chat assistant backend
  - Target model per `planning/PLAN.md` section 9: `openrouter/openai/gpt-oss-120b` with Cerebras as the inference provider
  - SDK/Client: `litellm` - NOT yet declared in `backend/pyproject.toml` nor locked in `backend/uv.lock`
  - Auth: `OPENROUTER_API_KEY` env var (documented in PLAN.md section 5; a `.env` file exists at project root but its contents were not read)
  - Structured outputs requested for trade/watchlist JSON (schema in PLAN.md section 9)
  - Mock mode: `LLM_MOCK=true` returns deterministic responses (planned; no code yet)
  - Code: `backend/app/llm/` exists with only a `__pycache__/` directory (stale bytecode for `client`, `prompt`, `router`, `schema`, `service`); no source files present
  - Related skill for implementation: `cerebras-inference` (per PLAN.md)

## Data Storage

**Databases:**
- SQLite (single file) - planned, not implemented
  - Location: `db/finally.db` at project root (volume mount target `/app/db` in container, per PLAN.md section 11)
  - Connection: no connection string or env var; path is planned hard-coded
  - Client: Python stdlib `sqlite3` expected (no ORM or driver declared in `backend/pyproject.toml`)
  - Schema/seed: planned in `backend/db/` (per PLAN.md section 4); the directory `backend/app/db/` exists with only `__pycache__/` (stale)
  - Current repo state: `db/` top-level directory does not exist yet; no `finally.db` present

**File Storage:**
- Local filesystem only. Static frontend is served from `backend/static/` (prebuilt Next.js export).

**Caching:**
- In-memory price cache only: `PriceCache` in `backend/app/market/cache.py` (thread-safe, `threading.Lock`, monotonic `version` counter). No Redis or external cache.

## Authentication & Identity

**Auth Provider:**
- None - single-user, no login (per PLAN.md section 2)
  - Implementation: all tables planned with `user_id` defaulting to `"default"` for future multi-user support; no auth middleware or tokens exist.

## Monitoring & Observability

**Error Tracking:**
- None detected

**Logs:**
- Python stdlib `logging` module (`logger = logging.getLogger(__name__)` pattern in `backend/app/market/massive_client.py`); messages at info, debug, and error levels. No log configuration or external sink found.

## CI/CD & Deployment

**Hosting:**
- Not yet deployed. Planned: single Docker container on port 8000 (run locally via `scripts/start_mac.sh` / `scripts/start_windows.ps1`); optional AWS App Runner, Render, or any container platform (PLAN.md section 11). No Dockerfile, `docker-compose.yml`, or `scripts/` directory exists yet.

**CI Pipeline:**
- GitHub Actions (`.github/workflows/claude.yml`, `.github/workflows/claude-code-review.yml`) - both use `anthropics/claude-code-action@v1` on `ubuntu-latest` for Claude-assisted issue and PR review. No build, lint, or test workflow.

**E2E test infrastructure (planned):**
- `test/` directory with Playwright artifacts (`test/playwright-report/`, `test/test-results/`); `docker-compose.test.yml` planned but absent.

## Environment Configuration

**Required env vars (per PLAN.md section 5):**
- `OPENROUTER_API_KEY` - required for LLM chat (planned; not yet read by code)
- `MASSIVE_API_KEY` - optional; if set and non-empty, Massive REST market data is used; otherwise the built-in simulator (read in `backend/app/market/factory.py`)
- `LLM_MOCK` - optional; `true` enables deterministic mock LLM responses (planned)

**Secrets location:**
- Project-root `.env` file (gitignored; read by the backend or passed to Docker via `--env-file`). Contents not inspected for this document.
- No `.env.example` file is present yet; PLAN.md specifies one should be committed.

## Webhooks & Callbacks

**Incoming:**
- None. The only HTTP endpoints in the backend are the market SSE stream (`GET /api/stream/prices`, `backend/app/market/stream.py`); planned REST routes (`/api/portfolio*`, `/api/watchlist*`, `/api/chat`, `/api/health`) are not yet implemented. No `backend/app/main.py` exists yet.

**Outgoing:**
- Massive REST API polling (see above). Planned: OpenRouter chat completions via LiteLLM.
- None else detected.

---

*Integration audit: 2026-11-03*
