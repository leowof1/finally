# Codebase Structure

**Analysis Date:** 2026-11-03

## Directory Layout

```
finally/                          # repo root
├── .github/workflows/          # Claude Code GitHub Actions (review, claude)
├── .planning/codebase/         # Generated codebase maps (this document)
├── backend/                    # FastAPI uv project (only implemented code)
│   ├── app/                    # Application package
│   │   ├── market/             # Market data subsystem (implemented)
│   │   ├── api/                # Planned REST/SSE routes (empty, pycache only)
│   │   ├── db/                 # Planned SQLite schema/seed (empty, pycache only)
│   │   ├── llm/                # Planned LLM client/schema (empty, pycache only)
│   │   └── portfolio/          # Planned trade/P&L logic (empty, pycache only)
│   ├── static/                 # Next.js static export output (committed build artifacts)
│   ├── tests/                  # pytest suite (market tests only)
│   │   ├── market/
│   │   └── conftest.py
│   ├── market_data_demo.py     # Rich terminal demo script
│   ├── pyproject.toml          # uv/hatch project config, pytest, ruff settings
│   ├── uv.lock                 # Locked dependencies
│   ├── CLAUDE.md               # Backend developer guide (market API usage)
│   └── README.md               # Backend structure and test commands
├── frontend/                   # Planned Next.js project (empty directory)
├── planning/                   # Project spec and agent reference docs
│   ├── PLAN.md                 # Project specification (source of truth)
│   ├── MARKET_DATA_SUMMARY.md  # Completed market data component summary
│   └── archive/                # Superseded market data design docs
├── test/                       # Planned Playwright E2E area
│   ├── node_modules/           # Committed dependencies (Playwright, TypeScript)
│   ├── playwright-report/      # Committed report output
│   └── test-results/           # Committed run output
├── CLAUDE.md                   # Project instructions (includes PLAN.md)
├── README.md                   # Project overview
├── LICENSE
└── .gitignore
```

Not present yet, though `planning/PLAN.md` specifies them: `db/` (runtime SQLite mount), `scripts/` (start/stop scripts), `Dockerfile`, `docker-compose.yml`, `.env.example`.

## Directory Purposes

**`backend/app/market/`:**
- Purpose: Market data producers, price cache, SSE transport.
- Contains: `models.py`, `cache.py`, `interface.py`, `simulator.py`, `massive_client.py`, `factory.py`, `stream.py`, `seed_prices.py`, `__init__.py`.
- Key files: `backend/app/market/__init__.py` (public exports), `backend/app/market/factory.py` (provider selection).

**`backend/app/api/`, `backend/app/db/`, `backend/app/llm/`, `backend/app/portfolio/`:**
- Purpose: Intended homes for the planned API routes, database layer, LLM integration, and portfolio logic.
- Contents: No `.py` source. Each contains only a stale `__pycache__/` from an earlier build.
- Treat as empty. Do not infer behavior from the `.pyc` files.

**`backend/tests/`:**
- Purpose: pytest tests for the backend.
- Contains: `conftest.py`, `market/test_cache.py`, `market/test_factory.py`, `market/test_massive.py`, `market/test_models.py`, `market/test_simulator.py`, `market/test_simulator_source.py`.
- Test directories contain `__init__.py` files.

**`backend/static/`:**
- Purpose: Output of the Next.js static export (`index.html`, `404.html`, `_next/`, route `.txt` payloads).
- Generated: Yes (from a Next.js build). Committed: Yes.
- Note: The planned Dockerfile copies frontend build output into a `static/` directory. No `frontend/` source exists to regenerate it.

**`frontend/`:**
- Purpose: Planned Next.js TypeScript project (static export, Tailwind CSS).
- Contents: Empty.

**`planning/`:**
- Purpose: Shared agent contract and reference docs.
- Key files: `planning/PLAN.md` (spec), `planning/MARKET_DATA_SUMMARY.md` (completed component status), `planning/archive/*.md` (old design notes, read only when needed).

**`test/`:**
- Purpose: Planned Playwright E2E tests and docker-compose test setup.
- Contents: Only Playwright tooling in `node_modules/`, a report, and last-run results. No test specs or `docker-compose.test.yml` yet.

**`.github/workflows/`:**
- Purpose: CI automation for Claude Code review (`claude-code-review.yml`, `claude.yml`).

## Key File Locations

**Entry Points:**
- `backend/app/market/__init__.py`: public import surface for the market package.
- `backend/market_data_demo.py`: standalone demo runnable with `uv run`.
- Planned `backend/app/main.py`: FastAPI app and uvicorn target. Not present.

**Configuration:**
- `backend/pyproject.toml`: dependencies, dev extras, pytest options (`asyncio_mode = "auto"`), ruff (`line-length = 100`, rules `E,F,I,N,W`), coverage.
- `backend/uv.lock`: locked dependency versions.
- `.gitignore`: ignores `.env`, `.venv`, `__pycache__/`, `db.sqlite3`.
- `.env`: present at repo root. Contains secrets. Never read or copy its contents.

**Core Logic:**
- `backend/app/market/simulator.py`: GBM simulator and simulator data source.
- `backend/app/market/massive_client.py`: Massive REST poller.
- `backend/app/market/cache.py`: shared price cache.
- `backend/app/market/seed_prices.py`: default ticker seed prices and GBM parameters.

**Testing:**
- `backend/tests/conftest.py`: shared pytest fixtures.
- `backend/tests/market/`: unit and integration tests for the market package.

## Naming Conventions

**Files:**
- Python modules: `snake_case.py`, one concept per module (`massive_client.py`, `seed_prices.py`).
- Test files: `test_<module>.py` under `backend/tests/<package>/`, mirroring `backend/app/<package>/`.
- Planning and codebase docs: `UPPERCASE.md` (`PLAN.md`, `MARKET_DATA_SUMMARY.md`).

**Directories:**
- Python packages: lowercase single words (`market`, `portfolio`, `llm`, `db`, `api`).
- Each Python package has an `__init__.py` with an explicit `__all__` where it exports public names (see `backend/app/market/__init__.py`).

**Classes and functions:**
- Classes: `PascalCase` (`PriceCache`, `SimulatorDataSource`, `MarketDataSource`).
- Factory functions: `create_<thing>` (`create_market_data_source`, `create_stream_router`).
- Private helpers: leading underscore (`_run_loop`, `_generate_events`, `_rebuild_cholesky`).

## Where to Add New Code

**New market data provider:**
- Implementation: `backend/app/market/<provider>.py`, subclassing `MarketDataSource` from `backend/app/market/interface.py`.
- Wire it into the selection logic in `backend/app/market/factory.py`.
- Tests: `backend/tests/market/test_<provider>.py`, following `test_massive.py` (mocks the SDK client).
- Export from `backend/app/market/__init__.py` only if other packages need it.

**New REST or SSE route (planned API layer):**
- Implementation: `backend/app/api/<area>.py` (for example `portfolio.py`, `watchlist.py`, `chat.py`, `health.py`). Mirror the router-factory pattern in `backend/app/market/stream.py`.
- Mount it in the application module `backend/app/main.py` (to be created).
- Tests: `backend/tests/api/test_<area>.py`.

**Database schema, seed, or repository code (planned):**
- Implementation: `backend/app/db/` (schema SQL and seed logic, per `planning/PLAN.md` section 4 "backend/db/").
- Tests: `backend/tests/db/test_db.py`.

**Portfolio logic (planned):**
- Implementation: `backend/app/portfolio/`. Keep trade validation and P&L math here so routes and the LLM flow share it.
- Tests: `backend/tests/portfolio/`.

**LLM integration (planned):**
- Implementation: `backend/app/llm/` (client, prompt, schema, service).
- Tests: `backend/tests/llm/`.

**Utilities:**
- Shared helpers: add to the owning package. There is no top-level `utils` package yet.

**Frontend (planned):**
- Implementation: `frontend/` (Next.js TypeScript, static export). Build output goes to `backend/static/`.

**E2E tests (planned):**
- Implementation: `test/` with Playwright specs and `docker-compose.test.yml`.

## Special Directories

**`backend/static/`:**
- Purpose: Next.js static export served by FastAPI.
- Generated: Yes.
- Committed: Yes.

**`test/node_modules/`, `test/playwright-report/`, `test/test-results/`:**
- Purpose: Playwright tooling and output.
- Generated: Yes.
- Committed: Yes (tracked in git despite typical ignore rules).

**`backend/.pytest_cache/`, `backend/.ruff_cache/`, `backend/app/**/__pycache__/`:**
- Purpose: Tool caches.
- Generated: Yes.
- Committed: No (ignored by `.gitignore` patterns for `__pycache__`; caches present locally).

**`db/` (planned runtime mount):**
- Purpose: SQLite file `db/finally.db` mounted into the container at `/app/db`.
- Generated: Yes, at runtime.
- Committed: Directory only, with `.gitkeep`, per the plan. Not yet created.

---

*Structure analysis: 2026-11-03*
