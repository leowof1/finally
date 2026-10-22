"""In-memory cache of the latest price per ticker."""

from dataclasses import dataclass
from datetime import UTC, datetime


def iso_utc(ts: datetime) -> str:
    """Format as ISO 8601 UTC with milliseconds, e.g. 2026-10-14T13:30:00.500Z."""
    ts = ts.astimezone(UTC)
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


@dataclass(frozen=True, slots=True)
class PriceEntry:
    """Latest price state for one ticker."""

    price: float
    previous_price: float
    reference_price: float
    timestamp: datetime  # tz-aware UTC, time of the last update

    @property
    def direction(self) -> str:
        """'up', 'down' or 'flat', comparing prices as displayed (rounded to cents)."""
        now, before = round(self.price, 2), round(self.previous_price, 2)
        if now > before:
            return "up"
        if now < before:
            return "down"
        return "flat"

    @property
    def change_percent(self) -> float:
        """Percent change vs. reference_price (the 'daily change')."""
        if not self.reference_price:
            return 0.0
        pct = round((self.price - self.reference_price) / self.reference_price * 100, 2)
        return pct + 0.0  # turn -0.0 into 0.0

    def to_dict(self) -> dict:
        """SSE payload for this ticker (PLAN.md section 6)."""
        return {
            "price": round(self.price, 2),
            "previous_price": round(self.previous_price, 2),
            "change_percent": self.change_percent,
            "direction": self.direction,
            "timestamp": iso_utc(self.timestamp),
        }


class PriceCache:
    """Latest prices, written by the one active market data source.

    All access happens on the asyncio event loop, so no lock is needed.
    """

    def __init__(self) -> None:
        self._entries: dict[str, PriceEntry] = {}

    def update(
        self,
        ticker: str,
        price: float,
        timestamp: datetime,
        reference_price: float | None = None,
    ) -> PriceEntry:
        """Record a new price; the current price becomes previous_price.

        reference_price is kept from the existing entry unless a new one is given.
        On the first update it defaults to the price itself.
        """
        old = self._entries.get(ticker)
        if reference_price is None:
            reference_price = old.reference_price if old else price
        entry = PriceEntry(
            price=price,
            previous_price=old.price if old else price,
            reference_price=reference_price,
            timestamp=timestamp,
        )
        self._entries[ticker] = entry
        return entry

    def get(self, ticker: str) -> PriceEntry | None:
        """Latest entry, or None if no price has arrived yet."""
        return self._entries.get(ticker)

    def price(self, ticker: str) -> float | None:
        """Shortcut for the latest price, or None."""
        entry = self._entries.get(ticker)
        return entry.price if entry else None

    def remove(self, ticker: str) -> None:
        self._entries.pop(ticker, None)

    def snapshot(self) -> dict[str, PriceEntry]:
        """Shallow copy of all entries, safe to iterate while the source keeps writing."""
        return dict(self._entries)

    def __contains__(self, ticker: str) -> bool:
        return ticker in self._entries

    def __len__(self) -> int:
        return len(self._entries)
