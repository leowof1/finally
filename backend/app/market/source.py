"""The abstract market data source shared by the simulator and Massive."""

from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.market.cache import PriceCache


class MarketDataError(Exception):
    """Base class for market data errors."""


class UnknownTickerError(MarketDataError):
    """The data source has no data for this ticker."""


class MarketDataUnavailableError(MarketDataError):
    """The data source could not be reached (network error, auth error, rate limit)."""


class MarketDataSource(ABC):
    """Produces prices for a set of tracked tickers and writes them to a PriceCache."""

    def __init__(self, cache: PriceCache) -> None:
        self.cache = cache
        self._tickers: set[str] = set()

    @property
    def tickers(self) -> frozenset[str]:
        """Tickers currently tracked (watchlist ∪ open positions)."""
        return frozenset(self._tickers)

    @abstractmethod
    async def start(self, tickers: Iterable[str]) -> None:
        """Seed the cache for `tickers` and start the background update task.

        Must not raise because the upstream is unreachable: log and keep going.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background task and release resources. Safe to call twice."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Start tracking `ticker` and put a first price in the cache before returning.

        Does nothing if the ticker is already tracked and priced.
        Raises UnknownTickerError if the source has no data for it, and
        MarketDataUnavailableError if the source could not be reached.
        """

    async def remove_ticker(self, ticker: str) -> None:
        """Stop tracking `ticker` and drop it from the cache. Unknown tickers are ignored."""
        self._tickers.discard(ticker)
        self.cache.remove(ticker)
