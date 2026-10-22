"""SSE endpoint: GET /api/stream/prices."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.market.cache import PriceCache

STREAM_INTERVAL = 0.5
RETRY_MS = 1000

router = APIRouter()


async def price_events(
    cache: PriceCache,
    is_disconnected: Callable[[], Awaitable[bool]],
    interval: float = STREAM_INTERVAL,
) -> AsyncIterator[str]:
    """Yield one SSE event with the full snapshot every `interval` seconds."""
    yield f"retry: {RETRY_MS}\n\n"
    while not await is_disconnected():
        payload = {ticker: e.to_dict() for ticker, e in sorted(cache.snapshot().items())}
        yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
        await asyncio.sleep(interval)


@router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    return StreamingResponse(
        price_events(request.app.state.prices, request.is_disconnected),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
