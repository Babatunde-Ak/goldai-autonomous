from datetime import UTC, datetime, timedelta

import pytest

from goldai.market import MarketBar, MarketTick, Timeframe


NOW = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)


def test_market_tick_accepts_valid_bid_ask() -> None:
    tick = MarketTick("XAUUSD", NOW, bid=2_600.10, ask=2_600.35, source="histdata", sequence=1)
    assert tick.spread == pytest.approx(0.25)
    assert tick.to_dict()["timestamp"].endswith("+00:00")


@pytest.mark.parametrize(
    ("bid", "ask"),
    [(2_600.0, 2_599.9), (0.0, 2_600.0), (2_600.0, -1.0)],
)
def test_market_tick_rejects_invalid_prices(bid: float, ask: float) -> None:
    with pytest.raises(ValueError):
        MarketTick("XAUUSD", NOW, bid=bid, ask=ask, source="test")


def test_market_tick_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketTick("XAUUSD", datetime(2026, 1, 1), bid=1.0, ask=1.1, source="test")


@pytest.mark.parametrize("raw", ["m1", " M15 ", "h4"])
def test_timeframe_parsing(raw: str) -> None:
    parsed = Timeframe.parse(raw)
    assert parsed.value == raw.strip().upper()
    assert parsed.seconds > 0


def test_timeframe_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        Timeframe.parse("M7")


def test_market_bar_validates_ohlc() -> None:
    bar = MarketBar(
        symbol="XAUUSD",
        timeframe=Timeframe.M5,
        opened_at=NOW,
        closed_at=NOW + timedelta(minutes=5),
        open=2_600,
        high=2_605,
        low=2_598,
        close=2_603,
    )
    assert bar.high == 2_605


def test_market_bar_rejects_inconsistent_ohlc() -> None:
    with pytest.raises(ValueError, match="inconsistent"):
        MarketBar("XAUUSD", Timeframe.M5, NOW, NOW + timedelta(minutes=5), 10, 9, 8, 10)

