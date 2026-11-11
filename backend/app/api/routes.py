"""REST endpoints for portfolio, watchlist, chat and health."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.database import transaction
from app.portfolio import service, watchlist

from .chat import handle_chat

router = APIRouter(prefix="/api")


class TradeRequest(BaseModel):
    ticker: str
    quantity: float = Field(gt=0)
    side: Literal["buy", "sell"]


class WatchlistRequest(BaseModel):
    ticker: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/portfolio")
def get_portfolio(request: Request) -> dict:
    with transaction() as conn:
        return service.get_portfolio(conn, request.app.state.cache)


@router.post("/portfolio/trade")
def trade(body: TradeRequest, request: Request) -> dict:
    cache = request.app.state.cache
    with transaction() as conn:
        try:
            executed = service.execute_trade(conn, cache, body.ticker, body.side, body.quantity)
        except service.TradeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"trade": executed, "portfolio": service.get_portfolio(conn, cache)}


@router.get("/portfolio/history")
def history() -> list[dict]:
    with transaction() as conn:
        return service.get_history(conn)


@router.get("/watchlist")
def get_watchlist(request: Request) -> list[dict]:
    with transaction() as conn:
        tickers = watchlist.get_tickers(conn)
    return [watchlist_entry(request, t) for t in tickers]


@router.post("/watchlist", status_code=201)
async def add_to_watchlist(body: WatchlistRequest, request: Request) -> dict:
    ticker = parse_ticker(body.ticker)
    with transaction() as conn:
        added = watchlist.add_ticker(conn, ticker)
    if not added:
        raise HTTPException(status_code=409, detail=f"{ticker} is already on the watchlist")
    await request.app.state.source.add_ticker(ticker)
    return watchlist_entry(request, ticker)


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, request: Request) -> dict:
    ticker = parse_ticker(ticker)
    with transaction() as conn:
        removed = watchlist.remove_ticker(conn, ticker)
        held = ticker in service.held_tickers(conn)
    if not removed:
        raise HTTPException(status_code=404, detail=f"{ticker} is not on the watchlist")
    if not held:
        await request.app.state.source.remove_ticker(ticker)
    return {"ticker": ticker, "removed": True}


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> dict:
    return await handle_chat(request.app.state, body.message)


def parse_ticker(raw: str) -> str:
    try:
        return watchlist.normalize_ticker(raw)
    except watchlist.WatchlistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def watchlist_entry(request: Request, ticker: str) -> dict:
    update = request.app.state.cache.get(ticker)
    if update:
        return update.to_dict()
    return {"ticker": ticker, "price": None}
