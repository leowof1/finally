from fastapi.testclient import TestClient

from app.main import DEFAULT_TICKERS, app
from app.market.simulator import SimulatorSource


def test_lifespan_starts_and_stops_market_source(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        source = app.state.market
        assert isinstance(source, SimulatorSource)
        assert source.tickers == set(DEFAULT_TICKERS)
        assert set(app.state.prices.snapshot()) == set(DEFAULT_TICKERS)
        assert source._task is not None
    assert source._task is None  # stopped on shutdown
