"""Ticker normalisation shared by the REST routes and the LLM action executor."""

import re

TICKER_RE = re.compile(r"^[A-Z][A-Z.]{0,9}$")


class InvalidTickerError(ValueError):
    """The ticker does not match ^[A-Z][A-Z.]{0,9}$ after uppercasing."""


def normalize_ticker(raw: str) -> str:
    """Strip and uppercase `raw`; raise InvalidTickerError if the format is wrong."""
    ticker = raw.strip().upper()
    if not TICKER_RE.fullmatch(ticker):
        raise InvalidTickerError(f"Invalid ticker: {raw!r}")
    return ticker
