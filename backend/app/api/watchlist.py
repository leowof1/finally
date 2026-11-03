"""Watchlist endpoints, kept in sync with the market data source."""

import re

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import db

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")


class WatchlistAdd(BaseModel):
    """Request body for adding a ticker."""

    ticker: str


@router.get("")
def read_watchlist(request: Request) -> list[dict]:
    """Return watched tickers with their latest prices (null if unpriced)."""
    cache = request.app.state.price_cache
    return [_with_price(item, cache.get(item["ticker"])) for item in db.get_watchlist()]


def _with_price(item: dict, update) -> dict:
    """Merge a watchlist row with its cached price update."""
    return {
        "ticker": item["ticker"],
        "price": update.price if update else None,
        "previous_price": update.previous_price if update else None,
        "change_percent": update.change_percent if update else None,
        "direction": update.direction if update else None,
        "added_at": item["added_at"],
    }


@router.post("", status_code=201)
async def add_ticker(body: WatchlistAdd, request: Request) -> dict:
    """Add a ticker; 400 if invalid, 409 if already present."""
    ticker = body.ticker.strip().upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {body.ticker}")
    added = db.add_watchlist(ticker)
    if added is None:
        raise HTTPException(status_code=409, detail=f"{ticker} already in watchlist")
    await request.app.state.market_source.add_ticker(ticker)
    return added


@router.delete("/{ticker}", status_code=204)
async def remove_ticker(ticker: str, request: Request) -> Response:
    """Remove a ticker; 404 if absent."""
    ticker = ticker.upper()
    if not db.remove_watchlist(ticker):
        raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist")
    await request.app.state.market_source.remove_ticker(ticker)
    return Response(status_code=204)
