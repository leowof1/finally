"""Background task recording portfolio value snapshots."""

from __future__ import annotations

import asyncio

from app import db
from app.market import PriceCache

from .service import get_portfolio


async def run_snapshot_loop(cache: PriceCache, interval: float = 30.0) -> None:
    """Record the total portfolio value every `interval` seconds until cancelled."""
    while True:
        db.insert_snapshot(get_portfolio(cache)["total_value"])
        await asyncio.sleep(interval)
