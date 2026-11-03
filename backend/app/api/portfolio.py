"""Portfolio endpoints: valuation, trading, history."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import db
from app.portfolio import TradeError, execute_trade, get_portfolio

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    """Market order request body."""

    ticker: str
    quantity: float
    side: Literal["buy", "sell"]


@router.get("")
def read_portfolio(request: Request) -> dict:
    """Return cash, positions and totals at current prices."""
    return get_portfolio(request.app.state.price_cache)


@router.post("/trade")
def trade(body: TradeRequest, request: Request) -> dict:
    """Execute a market order; 400 on validation failure."""
    cache = request.app.state.price_cache
    try:
        executed = execute_trade(cache, body.ticker, body.side, body.quantity)
    except TradeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"trade": executed, "portfolio": get_portfolio(cache)}


@router.get("/history")
def history() -> list[dict]:
    """Return portfolio value snapshots, oldest first."""
    return db.get_snapshots()
