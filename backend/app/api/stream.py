"""SSE endpoint: GET /api/stream/prices.

EventSourceResponse (sse-starlette) rather than StreamingResponse: it ends open
streams when uvicorn begins shutting down. With a plain StreamingResponse uvicorn
waits for every SSE client to disconnect, so `docker stop` hangs until SIGKILL.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

import anyio
from fastapi import APIRouter, Request
from sse_starlette import EventSourceResponse

from app.market.cache import PriceCache

STREAM_INTERVAL = 0.5
RETRY_MS = 1000
SHUTDOWN_GRACE = STREAM_INTERVAL * 2  # long enough for the generator to wake and finish

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


async def _encoded(events: AsyncIterator[str]) -> AsyncIterator[bytes]:
    """Pass pre-formatted SSE text through as bytes (sse-starlette would re-wrap str)."""
    async for event in events:
        yield event.encode()


@router.get("/api/stream/prices")
async def stream_prices(request: Request) -> EventSourceResponse:
    # Set by sse-starlette when uvicorn starts shutting down, so the generator ends
    # cleanly instead of being cancelled mid-response.
    shutdown = anyio.Event()

    async def should_stop() -> bool:
        return shutdown.is_set() or await request.is_disconnected()

    return EventSourceResponse(
        _encoded(price_events(request.app.state.prices, should_stop)),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        ping=0,  # a full snapshot every 500ms already keeps the connection alive
        shutdown_event=shutdown,
        shutdown_grace_period=SHUTDOWN_GRACE,
    )
