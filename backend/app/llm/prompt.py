"""Prompt construction: system prompt, portfolio context and chat history."""

import json

from app.db import get_watchlist
from app.market import PriceCache
from app.portfolio import get_portfolio

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation.
The user trades a simulated portfolio with virtual cash. Market orders only, filled instantly at the current price.

Your job:
- Analyze portfolio composition, risk concentration and P&L.
- Suggest trades with brief reasoning.
- Execute trades when the user asks or agrees, by listing them in "trades".
- Manage the watchlist proactively via "watchlist_changes" (action "add" or "remove").
- Be concise and data-driven. Use numbers from the context.

Always respond with valid JSON matching the schema: "message" (text shown to the user),
"trades" (list of {ticker, side: "buy"|"sell", quantity}), "watchlist_changes" (list of {ticker, action}).
Use empty lists when no action is needed. Only trade tickers that have a live price."""


def watchlist_context(cache: PriceCache) -> list[dict]:
    """Watchlist tickers with their latest price (None if not priced yet)."""
    return [{"ticker": w["ticker"], "price": cache.get_price(w["ticker"])} for w in get_watchlist()]


def portfolio_context(cache: PriceCache) -> str:
    """Current portfolio and watchlist as a JSON string for the LLM."""
    context = {"portfolio": get_portfolio(cache), "watchlist": watchlist_context(cache)}
    return json.dumps(context, default=str)


def build_messages(cache: PriceCache, history: list[dict], user_message: str) -> list[dict]:
    """Assemble the LLM message list: system, history, live context, then the new user message.

    Context goes after history so the model treats it as the state after all past trades.
    """
    context = (
        "Live portfolio state right now (already includes every trade executed earlier "
        f"in this conversation):\n{portfolio_context(cache)}"
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": user_message})
    return messages
