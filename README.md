# FinAlly — AI Trading Workstation

An AI-powered trading workstation: live streaming prices, a simulated $10k portfolio, and an LLM chat assistant that can analyze positions and execute trades. Built entirely by coding agents as a capstone for an agentic AI coding course.

## Quick Start

```bash
cp .env.example .env          # then set OPENROUTER_API_KEY
./scripts/start_mac.sh        # builds the image if needed, opens http://localhost:8000
./scripts/stop_mac.sh         # stops the container; data is kept
```

Windows: `.\scripts\start_windows.ps1` and `.\scripts\stop_windows.ps1`. Pass `--build` / `-Build` to force a rebuild.

Or with Docker Compose: `docker compose up --build`.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for AI chat |
| `MASSIVE_API_KEY` | No | Massive (Polygon.io) key for real market data; empty uses the simulator |
| `LLM_MOCK` | No | `true` for deterministic mock LLM responses (testing) |

## Architecture

One container on port 8000: FastAPI (Python/uv) serves the REST API, SSE price stream, and the Next.js static export. SQLite lives in the `finally-data` volume at `/app/db/finally.db`.

```
frontend/   Next.js + TypeScript + Tailwind (static export)
backend/    FastAPI uv project
planning/   Specs and agent contracts
test/       Playwright E2E tests
scripts/    Start/stop helpers
db/         SQLite volume mount (runtime)
```

## Tests

```bash
cd backend && uv run pytest                                   # backend unit tests
cd frontend && npm test                                       # frontend unit tests
docker compose -f test/docker-compose.test.yml up --build     # E2E (Playwright)
```

## License

See [LICENSE](LICENSE).
