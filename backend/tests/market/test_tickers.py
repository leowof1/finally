import pytest

from app.market.tickers import InvalidTickerError, normalize_ticker


@pytest.mark.parametrize("raw,expected", [("aapl", "AAPL"), (" brk.b ", "BRK.B"), ("V", "V")])
def test_valid(raw, expected):
    assert normalize_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", ".AAPL", "AAPL1", "TOOLONGTICK", "AA PL", "BRK-B"])
def test_invalid(raw):
    with pytest.raises(InvalidTickerError):
        normalize_ticker(raw)
