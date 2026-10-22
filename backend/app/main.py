"""FastAPI app. Market data wiring only; database and other routers land separately."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.stream import router as stream_router
from app.market import PriceCache, create_market_source

# Local dev: read the project-root .env. Docker passes --env-file instead, and real
# environment variables always win over the file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def load_tracked_tickers() -> list[str]:
    """Placeholder until the database module exists: watchlist ∪ positions."""
    return DEFAULT_TICKERS


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()
    source = create_market_source(cache)
    await source.start(load_tracked_tickers())
    app.state.prices = cache
    app.state.market = source
    try:
        yield
    finally:
        await source.stop()


app = FastAPI(lifespan=lifespan)
app.include_router(stream_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
