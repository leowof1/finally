"""Prompt construction for the FinAlly assistant."""

from __future__ import annotations

import json

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation.
The user trades a virtual portfolio with fake money, so you may act decisively.

You can:
- Analyze portfolio composition, risk concentration and P&L
- Suggest trades with brief reasoning
- Execute market orders (buy/sell) when the user asks or agrees, via "trades"
- Add or remove watchlist tickers proactively, via "watchlist_changes"

Rules:
- Be concise and data-driven. Use numbers from the portfolio context.
- Only include trades the user asked for or agreed to. Quantities are share counts (fractions allowed).
- Buys need enough cash; sells need enough shares. Check the context before trading.
- To trade a ticker not on the watchlist, also add it in watchlist_changes.
- Always respond with valid JSON matching the schema: message, trades, watchlist_changes.
  Use empty lists when there are no actions."""


def build_messages(context: dict, history: list[dict], user_message: str) -> list[dict]:
    """Assemble system prompt, portfolio context, history and the new message."""
    context_text = "Current portfolio and market context (JSON):\n" + json.dumps(context, indent=1)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_text},
    ]
    messages.extend({"role": m["role"], "content": m["content"]} for m in history)
    messages.append({"role": "user", "content": user_message})
    return messages
