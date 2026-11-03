"""LLM client: LiteLLM -> OpenRouter (Cerebras), plus a deterministic mock."""

import os
import re

from litellm import acompletion
from pydantic import ValidationError

from app.llm.schema import ChatResponse, TradeAction

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
FALLBACK_MESSAGE = "Sorry, I could not understand the model response. Please try again."


def is_mock() -> bool:
    """True when LLM_MOCK=true."""
    return os.environ.get("LLM_MOCK", "").lower() == "true"


def parse_response(raw: str) -> ChatResponse:
    """Parse the LLM JSON; malformed output becomes a plain fallback message."""
    try:
        return ChatResponse.model_validate_json(raw)
    except ValidationError:
        return ChatResponse(message=FALLBACK_MESSAGE)


def mock_response(user_message: str, tickers: list[str]) -> ChatResponse:
    """Deterministic reply: 'buy' buys 1 share of the first known ticker mentioned (default AAPL)."""
    if "buy" not in user_message.lower():
        return ChatResponse(message="Mock response")
    words = re.findall(r"[A-Za-z.]+", user_message.upper())
    ticker = next((w for w in words if w in tickers), "AAPL")
    return ChatResponse(
        message=f"Mock: bought 1 {ticker}",
        trades=[TradeAction(ticker=ticker, side="buy", quantity=1)],
    )


async def call_llm(messages: list[dict]) -> ChatResponse:
    """Call the model with structured output and parse the reply."""
    response = await acompletion(
        model=MODEL,
        messages=messages,
        response_format=ChatResponse,
        reasoning_effort="low",
        extra_body=EXTRA_BODY,
    )
    return parse_response(response.choices[0].message.content)
