"""Pick the market data source from the environment."""

import logging
import math
import os

from app.market.cache import PriceCache
from app.market.massive import DEFAULT_POLL_SECONDS, MIN_POLL_SECONDS, MassiveSource
from app.market.simulator import SimulatorSource
from app.market.source import MarketDataSource

logger = logging.getLogger(__name__)


def create_market_source(cache: PriceCache) -> MarketDataSource:
    """MassiveSource if MASSIVE_API_KEY is set and non-empty, otherwise SimulatorSource."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not api_key:
        logger.info("Market data: simulator")
        return SimulatorSource(cache)
    interval = poll_interval_from_env()
    logger.info("Market data: Massive, polling every %.0fs", interval)
    return MassiveSource(cache, api_key, poll_interval=interval)


def poll_interval_from_env() -> float:
    """MASSIVE_POLL_SECONDS, defaulting to 15s on bad input and clamped to a 1s floor."""
    raw = os.environ.get("MASSIVE_POLL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_POLL_SECONDS
    try:
        interval = float(raw)
    except ValueError:
        logger.warning(
            "MASSIVE_POLL_SECONDS=%r is not a number; using %.0fs", raw, DEFAULT_POLL_SECONDS
        )
        return DEFAULT_POLL_SECONDS
    if not math.isfinite(interval) or interval < MIN_POLL_SECONDS:
        logger.warning(
            "MASSIVE_POLL_SECONDS=%r is below %.0fs; using %.0fs",
            raw, MIN_POLL_SECONDS, MIN_POLL_SECONDS,
        )
        return MIN_POLL_SECONDS
    return interval
