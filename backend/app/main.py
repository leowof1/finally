"""FastAPI application: API routes, SSE stream, background tasks and static frontend."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.db.database import init_db, transaction
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.portfolio import service, watchlist

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logging.basicConfig(level=logging.INFO)

SNAPSHOT_INTERVAL = 30
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parents[1] / "static"))

cache = PriceCache()


async def snapshot_loop() -> None:
    """Record the portfolio value every SNAPSHOT_INTERVAL seconds."""
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL)
        with transaction() as conn:
            service.record_snapshot(conn, cache)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with transaction() as conn:
        tickers = sorted(set(watchlist.get_tickers(conn)) | service.held_tickers(conn))
    source = create_market_data_source(cache)
    await source.start(tickers)
    app.state.cache = cache
    app.state.source = source
    snapshots = asyncio.create_task(snapshot_loop())
    yield
    snapshots.cancel()
    await source.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
app.include_router(api_router)
app.include_router(create_stream_router(cache))

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
