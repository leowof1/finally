"""Tests for the chat flow with a patched LLM."""

import pytest

from app import db
from app.llm import service
from app.llm.prompt import SYSTEM_PROMPT, build_messages
from app.llm.schema import ChatResponse, TradeAction, WatchlistChange


@pytest.fixture
def reply_with(monkeypatch):
    """Patch call_llm to return a given ChatResponse."""

    def set_reply(reply: ChatResponse):
        async def fake_call(messages):
            return reply

        monkeypatch.setattr(service, "call_llm", fake_call)

    return set_reply


async def test_mock_mode_buys_and_persists(monkeypatch, cache, source):
    monkeypatch.setenv("LLM_MOCK", "true")
    result = await service.handle_chat(cache, source, "buy NVDA")
    assert result["message"] == "Mock: bought 1 NVDA"
    assert result["trades"] == [
        {"ticker": "NVDA", "side": "buy", "quantity": 1, "status": "executed", "price": 100.0}
    ]
    assert db.get_position("NVDA")["quantity"] == 1
    history = db.get_chat_messages()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["actions"]["trades"][0]["status"] == "executed"


async def test_mock_mode_plain_message(monkeypatch, cache, source):
    monkeypatch.setenv("LLM_MOCK", "true")
    result = await service.handle_chat(cache, source, "hello")
    assert result == {"message": "Mock response", "trades": [], "watchlist_changes": []}


async def test_insufficient_cash_trade_fails(reply_with, cache, source):
    reply_with(ChatResponse(message="ok", trades=[TradeAction(ticker="AAPL", side="buy", quantity=1000)]))
    result = await service.handle_chat(cache, source, "buy lots")
    trade = result["trades"][0]
    assert trade["status"] == "failed" and "error" in trade
    assert db.get_cash() == 10000.0


async def test_sell_without_shares_fails(reply_with, cache, source):
    reply_with(ChatResponse(message="ok", trades=[TradeAction(ticker="TSLA", side="sell", quantity=1)]))
    result = await service.handle_chat(cache, source, "sell")
    assert result["trades"][0]["status"] == "failed"


async def test_unpriced_ticker_fails_but_others_execute(reply_with, cache, source):
    reply_with(
        ChatResponse(
            message="ok",
            trades=[
                TradeAction(ticker="ZZZZ", side="buy", quantity=1),
                TradeAction(ticker="aapl", side="buy", quantity=2),
            ],
        )
    )
    result = await service.handle_chat(cache, source, "buy")
    assert [t["status"] for t in result["trades"]] == ["failed", "executed"]
    assert result["trades"][1]["ticker"] == "AAPL"
    assert db.get_cash() == 10000.0 - 400.0


async def test_watchlist_add_then_trade_new_ticker(reply_with, cache, source):
    reply_with(
        ChatResponse(
            message="ok",
            trades=[TradeAction(ticker="PYPL", side="buy", quantity=1)],
            watchlist_changes=[WatchlistChange(ticker="pypl", action="add")],
        )
    )
    result = await service.handle_chat(cache, source, "add and buy PYPL")
    assert result["watchlist_changes"] == [{"ticker": "PYPL", "action": "add", "status": "executed"}]
    assert result["trades"][0]["status"] == "executed"
    assert source.added == ["PYPL"]
    assert "PYPL" in [w["ticker"] for w in db.get_watchlist()]


async def test_watchlist_failures(reply_with, cache, source):
    reply_with(
        ChatResponse(
            message="ok",
            watchlist_changes=[
                WatchlistChange(ticker="AAPL", action="add"),
                WatchlistChange(ticker="ZZZZ", action="remove"),
            ],
        )
    )
    result = await service.handle_chat(cache, source, "edit watchlist")
    assert [c["status"] for c in result["watchlist_changes"]] == ["failed", "failed"]
    assert source.added == [] and source.removed == []


async def test_watchlist_remove(reply_with, cache, source):
    reply_with(ChatResponse(message="ok", watchlist_changes=[WatchlistChange(ticker="TSLA", action="remove")]))
    result = await service.handle_chat(cache, source, "drop TSLA")
    assert result["watchlist_changes"][0]["status"] == "executed"
    assert source.removed == ["TSLA"]


def test_build_messages_includes_context_and_history(cache):
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    messages = build_messages(cache, history, "what now?")
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1:3] == history
    assert messages[3]["role"] == "system"
    assert "cash_balance" in messages[3]["content"] and "AAPL" in messages[3]["content"]
    assert messages[4] == {"role": "user", "content": "what now?"}
