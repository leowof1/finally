"""LLM calls via LiteLLM -> OpenRouter (Cerebras), plus a deterministic mock."""

from __future__ import annotations

import os
import re
from typing import Literal

from litellm import completion
from pydantic import BaseModel

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}


class TradeAction(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistAction(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class ChatResponse(BaseModel):
    message: str
    trades: list[TradeAction]
    watchlist_changes: list[WatchlistAction]


def is_mock() -> bool:
    """True when LLM_MOCK=true."""
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


def call_llm(messages: list[dict]) -> ChatResponse:
    """Call the model with structured output and parse the result."""
    response = completion(
        model=MODEL,
        messages=messages,
        response_format=ChatResponse,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
    )
    return ChatResponse.model_validate_json(response.choices[0].message.content)


TRADE_RE = re.compile(r"\b(buy|sell)\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)?([A-Za-z.]{1,10})\b", re.I)
WATCH_RE = re.compile(r"\b(add|remove)\s+([A-Za-z.]{1,10})\b", re.I)


def mock_response(user_message: str) -> ChatResponse:
    """Deterministic response for tests: parses 'buy 5 AAPL' / 'add PYPL' commands."""
    trades = [
        TradeAction(side=side.lower(), quantity=float(qty), ticker=ticker.upper())
        for side, qty, ticker in TRADE_RE.findall(user_message)
    ]
    changes = [
        WatchlistAction(action=action.lower(), ticker=ticker.upper())
        for action, ticker in WATCH_RE.findall(user_message)
    ]
    if trades or changes:
        message = "Done. I've processed your request."
    else:
        message = "I'm FinAlly, your trading assistant (mock mode). Ask me to buy, sell, or watch a ticker."
    return ChatResponse(message=message, trades=trades, watchlist_changes=changes)
