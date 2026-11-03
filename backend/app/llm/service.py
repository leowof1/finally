"""Chat flow: call the LLM, auto-execute its actions, persist the conversation."""

from app import db
from app.llm.client import call_llm, is_mock, mock_response
from app.llm.prompt import build_messages
from app.llm.schema import ChatResponse, TradeAction, WatchlistChange
from app.market import MarketDataSource, PriceCache
from app.portfolio import TradeError, execute_trade


def run_trade(cache: PriceCache, trade: TradeAction) -> dict:
    """Execute one trade; return its result with status executed or failed."""
    result = {"ticker": trade.ticker.upper(), "side": trade.side, "quantity": trade.quantity}
    try:
        executed = execute_trade(cache, trade.ticker, trade.side, trade.quantity)
    except TradeError as e:
        return {**result, "status": "failed", "error": str(e)}
    return {**result, "status": "executed", "price": executed["price"]}


async def run_watchlist_change(source: MarketDataSource, change: WatchlistChange) -> dict:
    """Apply one watchlist change to the database and the market source."""
    ticker = change.ticker.strip().upper()
    result = {"ticker": ticker, "action": change.action}
    if change.action == "add":
        if db.add_watchlist(ticker) is None:
            return {**result, "status": "failed", "error": f"{ticker} already in watchlist"}
        await source.add_ticker(ticker)
    else:
        if not db.remove_watchlist(ticker):
            return {**result, "status": "failed", "error": f"{ticker} not in watchlist"}
        await source.remove_ticker(ticker)
    return {**result, "status": "executed"}


async def get_reply(cache: PriceCache, user_message: str) -> ChatResponse:
    """Get the structured reply from the mock or the real LLM."""
    if is_mock():
        return mock_response(user_message, list(cache.get_all()))
    history = db.get_chat_messages()
    return await call_llm(build_messages(cache, history, user_message))


async def handle_chat(cache: PriceCache, source: MarketDataSource, user_message: str) -> dict:
    """Run a full chat turn and return the contract response shape."""
    reply = await get_reply(cache, user_message)
    changes = [await run_watchlist_change(source, c) for c in reply.watchlist_changes]
    trades = [run_trade(cache, t) for t in reply.trades]
    actions = {"trades": trades, "watchlist_changes": changes}
    db.insert_chat_message("user", user_message, None)
    db.insert_chat_message("assistant", reply.message, actions)
    return {"message": reply.message, **actions}
