"""GBM market simulator: the default market data source."""

import asyncio
import logging
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.market.cache import PriceCache
from app.market.seeds import (
    DEFAULT_DRIFT,
    DEFAULT_SECTOR,
    DEFAULT_SIGMA,
    SEEDS,
    UNKNOWN_PRICE_RANGE,
)
from app.market.source import MarketDataSource

logger = logging.getLogger(__name__)

TICK_SECONDS = 0.5
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
DT = TICK_SECONDS / TRADING_SECONDS_PER_YEAR  # one tick, in trading years (~8.5e-8)

# Correlation and events
MARKET_WEIGHT = 0.3  # share of shock variance from the market factor
SECTOR_WEIGHT = 0.3  # share from the sector factor
EVENT_PROBABILITY = 0.001  # per ticker per tick
EVENT_MIN, EVENT_MAX = 0.02, 0.05


@dataclass
class TickerState:
    """Simulated state of one ticker."""

    price: float
    sigma: float
    sector: str
    drift: float = DEFAULT_DRIFT


class GBMModel:
    """Geometric Brownian motion over a set of tickers. Pure math: no I/O, no clock.

    S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)

    With market_weight = sector_weight = event_probability = 0 this is plain,
    independent GBM.
    """

    def __init__(
        self,
        rng: random.Random | None = None,
        *,
        market_weight: float = MARKET_WEIGHT,
        sector_weight: float = SECTOR_WEIGHT,
        event_probability: float = EVENT_PROBABILITY,
        dt: float = DT,
    ) -> None:
        if market_weight < 0 or sector_weight < 0 or market_weight + sector_weight > 1:
            raise ValueError("weights must be >= 0 and sum to at most 1")
        self.rng = rng or random.Random()
        self.states: dict[str, TickerState] = {}
        self.dt = dt
        self.event_probability = event_probability
        self._w_market = math.sqrt(market_weight)
        self._w_sector = math.sqrt(sector_weight)
        self._w_idio = math.sqrt(1 - market_weight - sector_weight)

    def add(self, ticker: str) -> float:
        """Start simulating `ticker` (no-op if present) and return its current price."""
        if ticker not in self.states:
            spec = SEEDS.get(ticker)
            if spec:
                state = TickerState(spec.price, spec.sigma, spec.sector, spec.drift)
            else:
                price = round(self.rng.uniform(*UNKNOWN_PRICE_RANGE), 2)
                state = TickerState(price, DEFAULT_SIGMA, DEFAULT_SECTOR)
            self.states[ticker] = state
        return self.states[ticker].price

    def remove(self, ticker: str) -> None:
        self.states.pop(ticker, None)

    def step(self) -> dict[str, float]:
        """Advance every ticker by one tick and return the new prices."""
        market = self.rng.gauss(0, 1)
        sectors: dict[str, float] = {}
        sqrt_dt = math.sqrt(self.dt)
        for state in self.states.values():
            if state.sector not in sectors:
                sectors[state.sector] = self.rng.gauss(0, 1)
            z = (
                self._w_market * market
                + self._w_sector * sectors[state.sector]
                + self._w_idio * self.rng.gauss(0, 1)
            )
            state.price *= math.exp(
                (state.drift - state.sigma**2 / 2) * self.dt + state.sigma * sqrt_dt * z
            )
            if self.event_probability and self.rng.random() < self.event_probability:
                jump = self.rng.uniform(EVENT_MIN, EVENT_MAX)
                state.price *= 1 + self.rng.choice((-1, 1)) * jump
        return {ticker: state.price for ticker, state in self.states.items()}


class SimulatorSource(MarketDataSource):
    """Simulated prices for every tracked ticker, updated every 500ms."""

    def __init__(
        self,
        cache: PriceCache,
        model: GBMModel | None = None,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        super().__init__(cache)
        self.model = model or GBMModel()
        self.tick_seconds = tick_seconds
        self._task: asyncio.Task | None = None

    async def start(self, tickers: Iterable[str]) -> None:
        for ticker in tickers:
            await self.add_ticker(ticker)
        self._task = asyncio.create_task(self._run(), name="market-simulator")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            return
        price = self.model.add(ticker)
        self.cache.update(ticker, price, datetime.now(UTC), reference_price=price)
        self._tickers.add(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.model.remove(ticker)
        await super().remove_ticker(ticker)

    def tick(self) -> None:
        """Step the model once and write all prices with one shared timestamp."""
        now = datetime.now(UTC)
        for ticker, price in self.model.step().items():
            self.cache.update(ticker, price, now)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                self.tick()
            except Exception:
                logger.exception("Simulator tick failed")
