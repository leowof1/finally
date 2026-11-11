"""Tests for structured output parsing and the mock LLM."""

import pytest
from pydantic import ValidationError

from app.llm.client import ChatResponse, mock_response
from app.llm.prompt import build_messages


def test_parse_full_response():
    raw = '{"message": "ok", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 1.5}], "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}'
    parsed = ChatResponse.model_validate_json(raw)
    assert parsed.trades[0].quantity == 1.5
    assert parsed.watchlist_changes[0].action == "add"


def test_parse_empty_actions():
    parsed = ChatResponse.model_validate_json('{"message": "hi", "trades": [], "watchlist_changes": []}')
    assert parsed.trades == []


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"trades": [], "watchlist_changes": []}',
        '{"message": "x", "trades": [{"ticker": "AAPL", "side": "hold", "quantity": 1}], "watchlist_changes": []}',
    ],
)
def test_malformed_responses_rejected(raw):
    with pytest.raises(ValidationError):
        ChatResponse.model_validate_json(raw)


def test_mock_parses_commands():
    response = mock_response("buy 10 aapl, sell 2.5 shares of TSLA and remove NFLX")
    assert [(t.side, t.quantity, t.ticker) for t in response.trades] == [
        ("buy", 10.0, "AAPL"),
        ("sell", 2.5, "TSLA"),
    ]
    assert response.watchlist_changes[0].ticker == "NFLX"


def test_mock_plain_message():
    response = mock_response("how is my portfolio?")
    assert response.trades == [] and response.watchlist_changes == []
    assert "FinAlly" in response.message


def test_build_messages_order():
    messages = build_messages({"cash": 1}, [{"role": "user", "content": "a"}], "b")
    assert [m["role"] for m in messages] == ["system", "system", "user", "user"]
    assert messages[-1]["content"] == "b"
