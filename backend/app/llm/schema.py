"""Structured output schema the LLM must return."""

from typing import Literal

from pydantic import BaseModel, Field


class TradeAction(BaseModel):
    """A market order the assistant wants to execute."""

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    """A watchlist modification the assistant wants to make."""

    ticker: str
    action: Literal["add", "remove"]


class ChatResponse(BaseModel):
    """Full structured LLM reply: message plus actions to auto-execute."""

    message: str
    trades: list[TradeAction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)
