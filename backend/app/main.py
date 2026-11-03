"""FastAPI application entrypoint: wiring, lifespan, static files."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR.parent / ".env")

from app import db  # noqa: E402
from app.api import health_router, portfolio_router, watchlist_router  # noqa: E402
from app.llm import chat_router  # noqa: E402
from app.market import PriceCache, create_market_data_source, create_stream_router  # noqa: E402
from app.portfolio import run_snapshot_loop  # noqa: E402

STATIC_DIR = BACKEND_DIR / "static"

price_cache = PriceCache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Init DB, start market data and the snapshot task; stop them on shutdown."""
    db.init_db()
    source = create_market_data_source(price_cache)
    await source.start([w["ticker"] for w in db.get_watchlist()])
    app.state.price_cache = price_cache
    app.state.market_source = source
    snapshot_task = asyncio.create_task(run_snapshot_loop(price_cache))
    yield
    snapshot_task.cancel()
    await source.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
app.include_router(health_router)
app.include_router(portfolio_router)
app.include_router(watchlist_router)
app.include_router(chat_router)
app.include_router(create_stream_router(price_cache))

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
