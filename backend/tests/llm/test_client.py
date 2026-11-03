"""Tests for response parsing and mock mode."""

from app.llm.client import FALLBACK_MESSAGE, is_mock, mock_response, parse_response


def test_parse_full_response():
    raw = (
        '{"message": "Done", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 2.5}],'
        ' "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}'
    )
    reply = parse_response(raw)
    assert reply.message == "Done"
    assert reply.trades[0].quantity == 2.5
    assert reply.watchlist_changes[0].action == "add"


def test_parse_message_only_defaults_to_empty_actions():
    reply = parse_response('{"message": "Hi"}')
    assert reply.trades == [] and reply.watchlist_changes == []


def test_parse_invalid_json_falls_back():
    assert parse_response("not json").message == FALLBACK_MESSAGE


def test_parse_invalid_side_falls_back():
    raw = '{"message": "x", "trades": [{"ticker": "AAPL", "side": "hold", "quantity": 1}]}'
    reply = parse_response(raw)
    assert reply.message == FALLBACK_MESSAGE and reply.trades == []


def test_parse_missing_message_falls_back():
    assert parse_response('{"trades": []}').message == FALLBACK_MESSAGE


def test_is_mock(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    assert is_mock()
    monkeypatch.setenv("LLM_MOCK", "false")
    assert not is_mock()


def test_mock_without_buy():
    reply = mock_response("How is my portfolio?", ["AAPL"])
    assert reply.message == "Mock response" and reply.trades == []


def test_mock_buy_defaults_to_aapl():
    reply = mock_response("Buy something", ["AAPL", "NVDA"])
    assert reply.message == "Mock: bought 1 AAPL"
    assert reply.trades[0].model_dump() == {"ticker": "AAPL", "side": "buy", "quantity": 1}


def test_mock_buy_first_ticker_mentioned():
    reply = mock_response("please buy nvda and tsla", ["AAPL", "NVDA", "TSLA"])
    assert reply.message == "Mock: bought 1 NVDA"
    assert reply.trades[0].ticker == "NVDA"
