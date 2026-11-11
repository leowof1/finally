"""Chat orchestration: context, LLM call, auto-execution of actions, persistence."""

from __future__ import annotations

import asyncio
import json
import logging

from app.db.database import DEFAULT_USER, new_id, now_iso, transaction
from app.llm.client import ChatResponse, call_llm, is_mock, mock_response
from app.llm.prompt import build_messages
from app.portfolio import service, watchlist

logger = logging.getLogger(__name__)
HISTORY_LIMIT = 20


async def handle_chat(state, user_message: str) -> dict:
    """Run one chat turn and return the assistant message with executed actions."""
    with transaction() as conn:
        context = build_context(conn, state.cache)
        history = load_history(conn)

    response = await get_response(build_messages(context, history, user_message), user_message)
    watchlist_results = [await apply_watchlist_change(state, c) for c in response.watchlist_changes]
    trade_results = [apply_trade(state.cache, t) for t in response.trades]

    message = response.message + failure_notes(watchlist_results + trade_results)
    actions = {"trades": trade_results, "watchlist_changes": watchlist_results}
    with transaction() as conn:
        save_message(conn, "user", user_message, None)
        save_message(conn, "assistant", message, actions)
        portfolio = service.get_portfolio(conn, state.cache)
    return {"message": message, "actions": actions, "portfolio": portfolio}


async def get_response(messages: list[dict], user_message: str) -> ChatResponse:
    """Mock or real LLM response; LLM failures become an apologetic message."""
    if is_mock():
        return mock_response(user_message)
    try:
        return await asyncio.to_thread(call_llm, messages)
    except Exception:
        logger.exception("LLM call failed")
        return ChatResponse(
            message="Sorry, I couldn't get a valid response from the AI service. Please try again.",
            trades=[],
            watchlist_changes=[],
        )


def build_context(conn, cache) -> dict:
    """Portfolio and watchlist snapshot given to the LLM."""
    portfolio = service.get_portfolio(conn, cache)
    prices = {t: cache.get_price(t) for t in watchlist.get_tickers(conn)}
    return {"portfolio": portfolio, "watchlist_prices": prices}


def load_history(conn) -> list[dict]:
    """Most recent chat messages, oldest first."""
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (DEFAULT_USER, HISTORY_LIMIT),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def save_message(conn, role: str, content: str, actions: dict | None) -> None:
    conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), DEFAULT_USER, role, content, json.dumps(actions) if actions else None, now_iso()),
    )


async def apply_watchlist_change(state, change) -> dict:
    """Add or remove a watchlist ticker, returning a result record."""
    result = {"ticker": change.ticker.upper(), "action": change.action}
    try:
        ticker = watchlist.normalize_ticker(change.ticker)
    except watchlist.WatchlistError as exc:
        return {**result, "status": "error", "error": str(exc)}
    with transaction() as conn:
        if change.action == "add":
            watchlist.add_ticker(conn, ticker)
            held = True
        else:
            watchlist.remove_ticker(conn, ticker)
            held = ticker in service.held_tickers(conn)
    if change.action == "add":
        await state.source.add_ticker(ticker)
    elif not held:
        await state.source.remove_ticker(ticker)
    return {**result, "status": "ok"}


def apply_trade(cache, trade) -> dict:
    """Execute one trade, returning the executed trade or the validation error."""
    result = {"ticker": trade.ticker.upper(), "side": trade.side, "quantity": trade.quantity}
    with transaction() as conn:
        try:
            executed = service.execute_trade(conn, cache, trade.ticker, trade.side, trade.quantity)
        except service.TradeError as exc:
            return {**result, "status": "error", "error": str(exc)}
    return {**result, "status": "ok", "price": executed["price"]}


def failure_notes(results: list[dict]) -> str:
    """Text appended to the reply describing failed actions."""
    errors = [r["error"] for r in results if r["status"] == "error"]
    return "".join(f"\n\nNote: {e}" for e in errors)
