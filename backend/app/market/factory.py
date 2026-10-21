"""Pick the market data source from the environment."""

import logging
import os

from app.market.cache import PriceCache
from app.market.massive import DEFAULT_POLL_SECONDS, MassiveSource
from app.market.simulator import SimulatorSource
from app.market.source import MarketDataSource

logger = logging.getLogger(__name__)


def create_market_source(cache: PriceCache) -> MarketDataSource:
    """MassiveSource if MASSIVE_API_KEY is set and non-empty, otherwise SimulatorSource."""
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not api_key:
        logger.info("Market data: simulator")
        return SimulatorSource(cache)
    interval = float(os.environ.get("MASSIVE_POLL_SECONDS") or DEFAULT_POLL_SECONDS)
    logger.info("Market data: Massive, polling every %.0fs", interval)
    return MassiveSource(cache, api_key, poll_interval=interval)
