from datetime import UTC, datetime, timedelta

from app.market.cache import PriceCache, iso_utc

T0 = datetime(2026, 10, 14, 13, 30, 0, 500_000, tzinfo=UTC)


def test_first_update_sets_all_prices_equal():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0)
    e = cache.get("AAPL")
    assert e.price == e.previous_price == e.reference_price == 190.0
    assert e.direction == "flat"
    assert e.change_percent == 0.0


def test_second_update_moves_previous_and_keeps_reference():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0, reference_price=188.0)
    cache.update("AAPL", 191.0, T0 + timedelta(seconds=1))
    e = cache.get("AAPL")
    assert (e.previous_price, e.price, e.reference_price) == (190.0, 191.0, 188.0)
    assert e.direction == "up"
    assert e.change_percent == 1.6


def test_direction_uses_displayed_cents():
    cache = PriceCache()
    cache.update("AAPL", 190.001, T0)
    cache.update("AAPL", 190.004, T0)
    assert cache.get("AAPL").direction == "flat"
    cache.update("AAPL", 189.99, T0)
    assert cache.get("AAPL").direction == "down"


def test_missing_and_removed():
    cache = PriceCache()
    assert cache.get("XYZ") is None
    assert cache.price("XYZ") is None
    cache.update("XYZ", 10.0, T0)
    assert cache.price("XYZ") == 10.0
    assert len(cache) == 1
    cache.remove("XYZ")
    cache.remove("XYZ")
    assert "XYZ" not in cache


def test_snapshot_is_a_copy():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0)
    snap = cache.snapshot()
    cache.update("MSFT", 420.0, T0)
    assert set(snap) == {"AAPL"}


def test_new_reference_price_replaces_old():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0, reference_price=188.0)
    cache.update("AAPL", 189.9, T0, reference_price=190.3)
    assert cache.get("AAPL").reference_price == 190.3


def test_zero_reference_gives_zero_change():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0, reference_price=0.0)
    assert cache.get("AAPL").change_percent == 0.0


def test_to_dict_matches_sse_contract():
    cache = PriceCache()
    cache.update("AAPL", 190.05, T0, reference_price=189.45)
    cache.update("AAPL", 190.1234, T0)
    assert cache.get("AAPL").to_dict() == {
        "price": 190.12,
        "previous_price": 190.05,
        "change_percent": 0.36,
        "direction": "up",
        "timestamp": "2026-10-14T13:30:00.500Z",
    }


def test_iso_utc_converts_other_timezones():
    est = datetime(2026, 10, 14, 9, 30, tzinfo=UTC).astimezone()
    assert iso_utc(est) == "2026-10-14T09:30:00.000Z"


def test_tiny_drop_is_not_negative_zero():
    cache = PriceCache()
    cache.update("AAPL", 190.0, T0)
    cache.update("AAPL", 189.999, T0)
    assert str(cache.get("AAPL").change_percent) == "0.0"
