# FinAlly — Summary of Everything

A short overview of the whole project: what it is, how it is built, and where it stands today.
For full detail see `PLAN.md` (the spec) and the other docs in `planning/`.

---

## 1. What It Is

**FinAlly (Finance Ally)** is an AI trading workstation that looks like a Bloomberg terminal.

- Streams live (or simulated) stock prices
- Lets you trade a **$10,000 virtual portfolio**
- Has an **AI chat assistant** that analyzes your portfolio and **can make trades for you**
- No login, single user, runs with one Docker command at `http://localhost:8000`
- Capstone project for an agentic AI coding course, built entirely by coding agents

## 2. Main Features

| Feature | Details |
|---|---|
| Watchlist | 10 default tickers (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX), add/remove any |
| Live prices | Green/red flash on change, sparklines built from the stream |
| Main chart | Bigger chart for the selected ticker |
| Trading | Market orders only, instant fill, no fees, fractional shares |
| Portfolio | Positions table, heatmap (treemap) by weight and P&L, P&L chart over time |
| AI chat | Natural-language analysis, trades and watchlist changes, executed automatically |
| Header | Total value, cash, connection dot (green / yellow / red) |

**Look:** dark theme (`#0d1117`), dense, desktop-first. Colors: yellow `#ecad0a`, blue `#209dd7`, purple `#753991` (buttons).

## 3. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js + TypeScript (static export), Tailwind, Recharts | One origin, no CORS |
| Backend | FastAPI (Python), managed with `uv` | Fast, modern, lockfile |
| Database | SQLite (`db/finally.db`, Docker volume `finally-data`) | Zero config, single user |
| Real-time | Server-Sent Events (SSE) | One-way push is all we need |
| AI | LiteLLM → OpenRouter → `gpt-oss-120b` on Cerebras, structured outputs | Fast responses |
| Deploy | One Docker container, one port (8000) | One command to run |

## 4. Market Data

- **Two sources, one interface** (`MarketDataSource`). Everything else reads a shared in-memory `PriceCache`.
  - **Simulator (default):** geometric Brownian motion, a tick every 500ms, realistic seed prices, correlated moves (sector + market) and random 2–5% "events". Unknown tickers get a random $50–$300 price.
  - **Massive API (formerly Polygon.io):** used if `MASSIVE_API_KEY` is set. Polls one multi-ticker snapshot every 15s. Needs a **Starter plan or higher** (the free plan has no snapshots).
- **Tracked tickers** = watchlist ∪ open positions.
- **Ticker format:** uppercase, `^[A-Z][A-Z.]{0,9}$`.
- **SSE** `GET /api/stream/prices`: the full snapshot every ~500ms, per ticker `price`, `previous_price`, `change_percent`, `direction`, `timestamp`.
- All timestamps are ISO 8601 UTC, e.g. `2026-10-14T13:30:00.500Z`.

## 5. Database (SQLite, created automatically on first run)

Every table has `user_id = "default"`, ready for multi-user later.

| Table | Holds |
|---|---|
| `users_profile` | Cash balance (starts at $10,000) |
| `watchlist` | Watched tickers |
| `positions` | Holdings: quantity, average cost |
| `trades` | Append-only trade log |
| `portfolio_snapshots` | Total value at startup, every 30s and after each trade |
| `chat_messages` | Chat history with action results |

## 6. API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/stream/prices` | SSE price stream |
| GET | `/api/portfolio` | Positions, cash, total value, P&L |
| POST | `/api/portfolio/trade` | Trade `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Value snapshots for the P&L chart |
| GET / POST | `/api/watchlist` | List / add a ticker |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |
| POST | `/api/chat` | Send a message, get the reply and executed actions |
| GET | `/api/chat/history` | Stored conversation |
| GET | `/api/health` | Health check |

**Trade rules:** quantity > 0; the ticker must have a price; a buy needs enough cash, a sell needs enough shares; the average cost is a weighted average on buys. Errors look like `{"detail": "..."}`.

## 7. AI Assistant

1. Loads the portfolio, the watchlist and the last 20 messages
2. Calls the LLM and asks for JSON: `{message, trades[], watchlist_changes[]}`
3. Runs watchlist changes first, then trades, through the same rules as manual trades
4. Saves and returns the result. 502 if the LLM fails, 503 if there is no API key

**Mock mode** (`LLM_MOCK=true`): fixed answers for tests ("buy" → buys 1 AAPL).

## 8. Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Required for AI chat |
| `MASSIVE_API_KEY` | Optional, real market data |
| `MASSIVE_POLL_SECONDS` | Optional poll interval (default 15, minimum 1) |
| `LLM_MOCK` | `true` for mock LLM replies |
| `DB_PATH` | Optional SQLite path |

## 9. Testing Plan

- **Backend:** pytest unit tests (market data, portfolio math, LLM parsing, API routes)
- **Frontend:** component tests (rendering, price flash, watchlist, chat)
- **E2E:** Playwright in `test/` with `docker-compose.test.yml`, run with `LLM_MOCK=true`

## 10. Current Status (2026-10-22)

| Part | Status |
|---|---|
| Spec and planning docs | ✅ Done |
| Market data backend (cache, simulator, Massive, factory, SSE) | ✅ Done, reviewed, all review findings fixed |
| Backend tests | ✅ **81 passing** |
| `uv.lock`, `.env` loading, logging | ✅ Done |
| Database module | ⏳ Not started (`main.py` uses a placeholder ticker list) |
| Portfolio, watchlist and chat routes | ⏳ Not started |
| LLM integration | ⏳ Not started |
| Frontend (`frontend/`) | ⏳ Not started |
| Dockerfile, `scripts/`, E2E tests (`test/`) | ⏳ Not started |

**Next steps:** database → watchlist and trade routes (see `MARKET_DATA_DESIGN.md` §11.3–11.4) → LLM chat → frontend → Docker and E2E.

## 11. What Each File Is For

| File | Contents |
|---|---|
| `planning/PLAN.md` | The main spec. Everything else follows it |
| `planning/MARKET_DATA_DESIGN.md` | Final market-data design with full code, **the one to implement from** |
| `planning/MARKET_INTERFACE.md` | First draft of the market-data API |
| `planning/MARKET_SIMULATOR.md` | GBM math, seed prices, checked numbers |
| `planning/MASSIVE_API.md` | Massive API reference: endpoints, plans, errors |
| `planning/MARKET_DATA_REVIEW.md` | Code review of the market backend and how each finding was fixed |
| `backend/app/market/` | Market data code (`cache`, `source`, `simulator`, `massive`, `factory`, `seeds`, `tickers`) |
| `backend/app/api/stream.py` | SSE endpoint |
| `backend/app/main.py` | FastAPI app, startup/shutdown, `/api/health` |
| `backend/tests/` | Unit tests |
| `.claude/skills/cerebras/` | How to call the LLM through Cerebras |
| `.github/workflows/` | Claude Code GitHub Actions (PR assistant and review) |

**Local dev tip:** if `uv sync` hangs, run `uv sync --python /usr/bin/python3.14`.
