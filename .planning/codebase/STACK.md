# Technology Stack

**Analysis Date:** 2026-11-03

## Languages

**Primary:**
- Python 3.12+ (declared `requires-python = ">=3.12"` in `backend/pyproject.toml`) - all backend code in `backend/app/` and `backend/tests/`
- Local venv in `backend/.venv` is built for CPython 3.14 (`backend/.venv/lib/python3.14/`, `__pycache__/*.cpython-314.pyc`)

**Secondary:**
- TypeScript / Node.js - planned for `frontend/` (Next.js). `frontend/` is currently empty; no TypeScript source exists yet.
- Shell / PowerShell - planned start/stop scripts in `scripts/` (per `planning/PLAN.md`); not yet present.

## Runtime

**Environment:**
- Python 3.12+ runtime for the backend (target `py312` in `backend/pyproject.toml` `[tool.ruff]`)
- Node 20 (planned, Docker build stage 1 for the Next.js static export, per `planning/PLAN.md` section 11); no Dockerfile exists yet
- Python 3.12 slim (planned, Docker stage 2)

**Package Manager:**
- `uv` (Astral) for Python - the project's required manager (per `CLAUDE.md`); `uv.lock` present at `backend/uv.lock` (lockfile version 1)
- Build backend: `hatchling` (`[build-system]` in `backend/pyproject.toml`), wheel packages `app`
- npm - planned for `frontend/` (not yet initialized; no `package.json`)
- Lockfile: present for Python (`backend/uv.lock`), missing for frontend

## Frameworks

**Core:**
- FastAPI `0.128.7` (locked; declared `>=0.115.0`) - HTTP API, routers, SSE via `StreamingResponse` in `backend/app/market/stream.py`
- Uvicorn `0.40.0` (locked; declared `uvicorn[standard]>=0.32.0`) - ASGI server (planned CMD in Docker, per PLAN.md)
- Next.js with TypeScript - planned frontend, built as static export (`output: 'export'`); not yet in repo

**Testing:**
- pytest `>=8.3.0` (dev extra) - test runner; config in `[tool.pytest.ini_options]` in `backend/pyproject.toml` (`testpaths = ["tests"]`, `asyncio_mode = "auto"`)
- pytest-asyncio `>=0.24.0` (dev extra) - async test support
- pytest-cov `>=5.0.0` (dev extra) - coverage; `[tool.coverage.run] source = ["app"]`
- Playwright - planned E2E tests in `test/` (directory has `playwright-report/` and `test-results/` artifacts, no config or specs yet)

**Build/Dev:**
- Ruff `>=0.7.0` (dev extra) - lint and format; `line-length = 100`, rules `E, F, I, N, W` in `backend/pyproject.toml`
- hatchling - Python build backend
- Rich `>=13.0.0` (locked 14.3.2) - terminal dashboard used by `backend/market_data_demo.py`

## Key Dependencies

**Critical (runtime, from `backend/pyproject.toml`):**
- `massive` `2.2.0` (locked; declared `>=1.0.0`) - Massive (Polygon.io successor) REST client; `from massive import RESTClient` and `massive.rest.models.SnapshotMarketType` in `backend/app/market/massive_client.py`
- `numpy` `2.4.2` (locked; declared `>=2.0.0`) - GBM math in the market simulator, `backend/app/market/simulator.py`
- `fastapi` `0.128.7` - web framework (see Frameworks)
- `pydantic` `2.12.5` (transitive via FastAPI)
- `anyio` `4.12.1` (transitive, async runtime used by FastAPI/Starlette)

**Dev-only (`[project.optional-dependencies] dev`):**
- `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff` (see above)

**Not yet present (planned by PLAN.md):**
- `litellm` - LLM calls via OpenRouter; NOT in `backend/uv.lock` (zero matches) and NOT in `backend/pyproject.toml`
- A SQLite driver - `sqlite3` is in the Python stdlib; no `aiosqlite` or ORM dependency is declared
- `sse-starlette` - not used; SSE is implemented with Starlette `StreamingResponse`

**Infrastructure:**
- `asyncio` (stdlib) - background market data task (`MassiveDataSource._poll_loop`, simulator task)
- `threading.Lock` (stdlib) - thread-safe `PriceCache` in `backend/app/market/cache.py`; Massive client runs its sync REST calls in a worker thread

## Configuration

**Environment:**
- Configuration is read from environment variables via `os.environ` (no settings library such as pydantic-settings is used)
  - `MASSIVE_API_KEY` read in `backend/app/market/factory.py` (empty or unset selects the simulator)
- Project-root `.env` file exists (`/Users/brunobudic/Learning/Programming/AI/AI Coder/projects/finally/.env`); contents intentionally not read. No `.env.example` exists yet, though PLAN.md section 5 specifies one.
- Planned variables per `planning/PLAN.md` section 5 (not yet consumed by code): `OPENROUTER_API_KEY`, `LLM_MOCK`
- No `.python-version` or `.nvmrc` present; Python version is governed by `requires-python` and `uv`

**Build:**
- `backend/pyproject.toml` - project metadata, dependencies, hatchling build, pytest, coverage, ruff config
- `backend/uv.lock` - pinned Python dependency graph
- `.gitignore` - ignores `__pycache__/`, `.venv`, caches, and (per PLAN.md) `db/finally.db`
- No `frontend/package.json`, `tsconfig.json`, `next.config.*`, or Dockerfile yet

**Prebuilt frontend artifact:**
- `backend/static/` contains a Next.js static export (`index.html`, `_next/static/chunks/*.js`, `__next.*.txt` RSC payloads, `icon.svg`). This is served as the static frontend per PLAN.md section 3; it is not produced by any build script in this repo yet.

## CI

- GitHub Actions in `.github/workflows/`:
  - `claude.yml` - `anthropics/claude-code-action@v1` on `ubuntu-latest`, triggered by `@claude` mentions
  - `claude-code-review.yml` - `anthropics/claude-code-action@v1` on `ubuntu-latest`
- No test, lint, or build workflow for the backend or frontend exists yet

## Platform Requirements

**Development:**
- Python 3.12+ and `uv` installed
- Run from `backend/`: `uv sync --extra dev`, then `uv run --extra dev pytest -v`, `uv run --extra dev ruff check app/ tests/`
- Demo: `uv run market_data_demo.py` (from `backend/`)
- Node 20 for frontend work (planned)

**Production:**
- Single Docker container, port 8000 (planned multi-stage Dockerfile: Node 20 slim frontend build, then Python 3.12 slim with uv); SQLite file at `db/finally.db` on a volume mount
- Deployment targets per PLAN.md: local Docker via `scripts/start_mac.sh` / `start_windows.ps1`; optional AWS App Runner, Render, or any container platform

---

*Stack analysis: 2026-11-03*
