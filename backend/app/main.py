"""FastAPI app. Market data wiring only; database and other routers land separately."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.stream import router as stream_router
from app.market import PriceCache, create_market_source

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
