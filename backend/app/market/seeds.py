"""Seed prices and parameters for the simulator."""

from typing import NamedTuple

DEFAULT_DRIFT = 0.05  # annual drift (mu)
DEFAULT_SIGMA = 0.30  # annual volatility for unknown tickers
DEFAULT_SECTOR = "other"
UNKNOWN_PRICE_RANGE = (50.0, 300.0)


class TickerSpec(NamedTuple):
    price: float
    sigma: float
    sector: str
    drift: float = DEFAULT_DRIFT


SEEDS: dict[str, TickerSpec] = {
    "AAPL": TickerSpec(190.0, 0.25, "tech"),
    "GOOGL": TickerSpec(175.0, 0.28, "tech"),
    "MSFT": TickerSpec(420.0, 0.24, "tech"),
    "AMZN": TickerSpec(185.0, 0.30, "tech"),
    "TSLA": TickerSpec(250.0, 0.60, "auto"),
    "NVDA": TickerSpec(130.0, 0.50, "tech", drift=0.10),
    "META": TickerSpec(560.0, 0.35, "tech"),
    "JPM": TickerSpec(210.0, 0.20, "finance"),
    "V": TickerSpec(280.0, 0.20, "finance"),
    "NFLX": TickerSpec(700.0, 0.40, "media"),
}
