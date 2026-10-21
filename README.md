# FinAlly — AI Trading Workstation

A Bloomberg-style trading terminal with an AI copilot. Stream live (or simulated) market prices, trade a $10,000 virtual portfolio, and chat with an LLM assistant that can analyze your positions and execute trades for you.

Built entirely by coding agents as the capstone project for an agentic AI coding course.

## Features

- Live price streaming over SSE with green/red flash animations and sparklines
- Market orders with instant fills, positions table, portfolio heatmap and P&L chart
- AI chat assistant (LiteLLM via OpenRouter, Cerebras inference) that trades and manages the watchlist
- Built-in market simulator by default; real data via the Massive (Polygon.io) API if a key is set

## Quick Start

```bash
cp .env.example .env        # add your OPENROUTER_API_KEY
./scripts/start_mac.sh      # build and run the container
```

Open http://localhost:8000. Stop with `./scripts/stop_mac.sh` (data persists in the `finally-data` volume).

Or run Docker directly:

```bash
docker build -t finally .
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

## Configuration

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Required for AI chat |
| `MASSIVE_API_KEY` | Optional; real market data instead of the simulator |
| `LLM_MOCK` | `true` for deterministic mock LLM responses (testing) |
| `DB_PATH` | Optional SQLite path (default `db/finally.db`) |

## Stack

Next.js (TypeScript, static export, Tailwind, Recharts) · FastAPI (Python, uv) · SQLite · Docker

## Project Layout

```
frontend/   Next.js app
backend/    FastAPI app (uv project)
planning/   Specification and agent docs (see planning/PLAN.md)
scripts/    Start/stop scripts
test/       Playwright E2E tests
```

## License

See [LICENSE](LICENSE).
