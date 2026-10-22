"""Massive (formerly Polygon.io) REST poller: the real market data source."""

import asyncio
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.market.cache import PriceCache
from app.market.source import (
    MarketDataSource,
    MarketDataUnavailableError,
    UnknownTickerError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.massive.com"
SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
DEFAULT_POLL_SECONDS = 15.0
MIN_POLL_SECONDS = 1.0
REQUEST_TIMEOUT = 10.0


@dataclass(frozen=True, slots=True)
class Quote:
    """One ticker's price, parsed from a snapshot entry."""

    ticker: str
    price: float
    reference_price: float | None  # previous day's close
    timestamp: datetime  # UTC


def ns_to_datetime(ns: int) -> datetime:
    """Nanoseconds since the epoch -> tz-aware UTC datetime (integer math, no float loss)."""
    seconds, rem = divmod(ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=rem // 1000)


def _bar_close(item: dict, key: str) -> float | None:
    bar = item.get(key) or {}
    return bar.get("c") or None  # 0 means "no bar yet" (snapshot reset overnight)


def parse_snapshot(item: dict, now: datetime | None = None) -> Quote | None:
    """Parse one entry of the snapshot `tickers` array; None if it carries no usable price.

    Price order: last trade -> current minute bar -> today's bar -> previous close.
    """
    last_trade = item.get("lastTrade") or {}
    price = (
        last_trade.get("p")
        or _bar_close(item, "min")
        or _bar_close(item, "day")
        or _bar_close(item, "prevDay")
    )
    if not price:
        return None
    updated = item.get("updated") or last_trade.get("t")
    timestamp = ns_to_datetime(updated) if updated else (now or datetime.now(UTC))
    return Quote(
        ticker=item["ticker"],
        price=float(price),
        reference_price=_bar_close(item, "prevDay"),
        timestamp=timestamp,
    )


class MassiveSource(MarketDataSource):
    """Polls the multi-ticker snapshot endpoint: one request per poll for all tickers."""

    def __init__(
        self,
        cache: PriceCache,
        api_key: str,
        poll_interval: float = DEFAULT_POLL_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(cache)
        self.poll_interval = poll_interval
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
        self._task: asyncio.Task | None = None

    async def start(self, tickers: Iterable[str]) -> None:
        if self._task:
            raise RuntimeError("MassiveSource already started")
        self._tickers = set(tickers)
        await self.poll()
        self._task = asyncio.create_task(self._run(), name="market-massive")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._client.aclose()

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers and ticker in self.cache:
            return
        try:
            items = await self._fetch([ticker])
        except httpx.HTTPError as exc:
            raise MarketDataUnavailableError(describe_error(exc)) from exc
        quote = next(
            (q for q in map(parse_snapshot, items) if q and q.ticker == ticker), None
        )
        if quote is None:
            raise UnknownTickerError(ticker)
        self._apply(quote)
        self._tickers.add(ticker)

    async def poll(self) -> None:
        """Fetch all tracked tickers once. Failures are logged; the next poll retries."""
        if not self._tickers:
            return
        try:
            items = await self._fetch(sorted(self._tickers))
        except httpx.HTTPError as exc:
            logger.warning("Massive snapshot poll failed: %s", describe_error(exc))
            return
        for item in items:
            quote = parse_snapshot(item)
            # A ticker removed while the request was in flight must not come back.
            if quote and quote.ticker in self._tickers:
                self._apply(quote)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval)
            try:
                await self.poll()
            except Exception:
                logger.exception("Massive poll crashed")

    async def _fetch(self, tickers: list[str]) -> list[dict]:
        response = await self._client.get(
            SNAPSHOT_PATH, params={"tickers": ",".join(tickers)}
        )
        response.raise_for_status()
        # A 200 that isn't a snapshot (proxy or CDN error page) counts as "unavailable",
        # raised as an httpx.HTTPError so callers handle it like a network failure.
        try:
            items = response.json().get("tickers") or []
        except (ValueError, AttributeError) as exc:
            raise httpx.DecodingError(f"Unexpected snapshot body: {exc}") from exc
        if not isinstance(items, list):
            raise httpx.DecodingError("Unexpected snapshot body: 'tickers' is not a list")
        return [i for i in items if isinstance(i, dict) and i.get("ticker")]

    def _apply(self, quote: Quote) -> None:
        """Write a quote to the cache unless it is no newer than the cached one."""
        old = self.cache.get(quote.ticker)
        if old and quote.timestamp <= old.timestamp:
            return
        self.cache.update(
            quote.ticker, quote.price, quote.timestamp, reference_price=quote.reference_price
        )


def describe_error(exc: httpx.HTTPError) -> str:
    """Short log text; never includes the API key (it travels in a header, not the URL)."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        hint = {
            401: "invalid MASSIVE_API_KEY",
            403: "plan does not include snapshots (Starter or higher needed)",
            429: "rate limit exceeded; raise MASSIVE_POLL_SECONDS",
        }.get(status, "")
        return f"HTTP {status} {hint}".strip()
    return f"{type(exc).__name__}: {exc}"
