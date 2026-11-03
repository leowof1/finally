# Team Contract

Shared agreement for the agent team. PLAN.md is the spec; this file pins down ownership and interfaces.
If you need to change an interface below, edit this file AND message the affected teammates.

## Ownership (only edit files you own; ask the owner otherwise)

| Member | Owns |
|---|---|
| database-engineer | `backend/app/db/` (schema.sql, connection, init+seed, repository functions), `backend/tests/db/` |
| backend-engineer | `backend/app/main.py`, `backend/app/api/` (portfolio, watchlist, health routers), `backend/app/portfolio/` (trade execution, valuation, snapshot task), static file serving, `backend/tests/api/`, `backend/tests/portfolio/`, `backend/pyproject.toml` deps |
| llm-engineer | `backend/app/llm/` (schema, prompt, LiteLLM client, mock, chat service, chat router), `backend/tests/llm/` |
| frontend-engineer | `frontend/` (everything) |
| devops-engineer | `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `scripts/`, `.env.example`, `.gitignore`, `db/.gitkeep`, root `README.md` |
| integration-tester | `test/` (Playwright E2E, `docker-compose.test.yml`) |

Existing, done: `backend/app/market/` (see `planning/MARKET_DATA_SUMMARY.md`). Do not modify without reason.

## Backend module interfaces

All Python uses `uv`. User id is always `"default"`.

**Database (`app.db`)** — sqlite3 stdlib, DB path from env `DB_PATH` (default `<project root>/db/finally.db`; container `/app/db/finally.db`).
- `init_db()` — create tables if missing, seed default user ($10,000) + 10 tickers. Idempotent.
- `get_cash() -> float`, `set_cash(amount)`
- `get_watchlist() -> list[dict]` (`ticker`, `added_at`; oldest first), `add_watchlist(ticker) -> dict | None` (`{ticker, added_at}`, None if already present), `remove_watchlist(ticker) -> bool`
- Callers pass tickers already uppercased. Each function opens/commits/closes its own connection (no shared transaction across calls).
- `get_positions() -> list[dict]` (`ticker`, `quantity`, `avg_cost`, `updated_at`), `get_position(ticker) -> dict | None`, `upsert_position(ticker, quantity, avg_cost)`, `delete_position(ticker)`
- `insert_trade(ticker, side, quantity, price) -> dict`, `get_trades() -> list[dict]`
- `insert_snapshot(total_value)`, `get_snapshots() -> list[dict]` (`total_value`, `recorded_at`)
- `insert_chat_message(role, content, actions: dict | None)`, `get_chat_messages(limit=20) -> list[dict]` (oldest first)

**Portfolio service (`app.portfolio`)** — owned by backend-engineer, used by llm-engineer.
- `execute_trade(cache, ticker, side, quantity) -> dict` — validates (price available, quantity > 0, cash for buys, shares for sells), updates cash/position, logs trade, records snapshot. Raises `TradeError(message)` on validation failure.
- `get_portfolio(cache) -> dict` — shape of `GET /api/portfolio` below.

**App wiring (`app.main`)** — `app = FastAPI(lifespan=...)`. Lifespan: `init_db()`, create `PriceCache`, start market source with watchlist tickers, start 30s snapshot task. Shared objects on `app.state.price_cache` and `app.state.market_source`. Includes the market stream router, backend routers, and `app.llm` chat router (imported as `from app.llm import chat_router`; an `APIRouter` with full `/api/chat` paths, reading `request.app.state.price_cache` / `market_source`). Serves `backend/static/` (Next.js export) at `/` with `html=True`, mounted LAST.
- Watchlist add/remove must also call `market_source.add_ticker/remove_ticker`.

## HTTP API (JSON)

```
GET  /api/health                 -> {"status": "ok"}
GET  /api/stream/prices          -> SSE, each event: data: {"AAPL": {ticker, price, previous_price, timestamp, change, change_percent, direction}, ...}
                                    (change_percent is tick-to-tick; the frontend computes session change vs first price seen)

GET  /api/portfolio              -> {cash_balance, total_value, unrealized_pnl,
                                     positions: [{ticker, quantity, avg_cost, current_price, market_value, unrealized_pnl, pnl_percent}]}
POST /api/portfolio/trade        body {ticker, quantity, side: "buy"|"sell"}
                                 -> 200 {trade: {ticker, side, quantity, price, executed_at}, portfolio: <as above>}
                                 -> 400 {detail: "<reason>"}
GET  /api/portfolio/history      -> [{total_value, recorded_at}]   (oldest first)

GET  /api/watchlist              -> [{ticker, price, previous_price, change_percent, direction, added_at}]  (price fields null if not priced yet)
POST /api/watchlist              body {ticker} -> 201 {ticker, added_at}; 409 if already present; 400 if invalid
DELETE /api/watchlist/{ticker}   -> 204; 404 if absent

POST /api/chat                   body {message}
                                 -> 200 {message, trades: [{ticker, side, quantity, status: "executed"|"failed", price?, error?}],
                                         watchlist_changes: [{ticker, action: "add"|"remove", status: "executed"|"failed", error?}]}
GET  /api/chat/history           -> [{role, content, actions, created_at}]  (oldest first)
```

Tickers are uppercased by the backend. Use `{"detail": ...}` (FastAPI HTTPException) for all errors.

## LLM

LiteLLM -> OpenRouter `openrouter/openai/gpt-oss-120b`, Cerebras provider, structured outputs (see `.claude/skills/cerebras/SKILL.md`).
`LLM_MOCK=true` -> deterministic mock: a message containing "buy" buys 1 share of the first ticker mentioned (default AAPL) and returns
"Mock: bought 1 AAPL"; otherwise returns "Mock response" with no actions. Integration tests rely on this.

## Frontend

Next.js + TypeScript + Tailwind, `output: 'export'`, build output `frontend/out/` (DevOps copies it to `backend/static/`).
Dev: run `next dev` with a rewrite/proxy of `/api/*` to `http://localhost:8000` (dev only; production is same origin).
Stable `data-testid`s for E2E: `watchlist-row-{TICKER}`, `price-{TICKER}`, `cash-balance`, `total-value`, `connection-status`,
`trade-ticker`, `trade-quantity`, `trade-buy`, `trade-sell`, `positions-table`, `position-row-{TICKER}`, `heatmap`, `pnl-chart`,
`chat-input`, `chat-send`, `chat-message`, `chat-loading`, `watchlist-add-input`, `watchlist-add-button`, `watchlist-remove-{TICKER}`.
E2E attributes: `connection-status` has `data-status="connected|reconnecting|disconnected"`; each `chat-message` has
`data-role="user|assistant"` and inline action confirmations (with ticker text) render inside the assistant message.
Money values in `cash-balance`/`total-value` render as plain text like `$10,000.00`.

## Issue reporting

integration-tester reports failures directly to the owning member via message (repro steps + failing test + observed vs expected).
Owners fix, then reply to integration-tester to re-run.
