from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from goldai.data import CanonicalCandleAggregator, MultiTimeframeAggregator
from goldai.data.aggregation import timeframe_boundary
from goldai.market import BarStatus, MarketTick, Timeframe


def _tick(timestamp: datetime, bid: float, ask: float, source: str = "test", sequence: int = 0) -> MarketTick:
    return MarketTick("XAUUSD", timestamp, bid, ask, source, sequence, last_volume=1.0)


@pytest.mark.parametrize("timeframe", list(Timeframe))
def test_every_required_timeframe_uses_deterministic_utc_boundaries(timeframe: Timeframe) -> None:
    timestamp = datetime(2026, 3, 8, 7, 7, 31, tzinfo=UTC)
    opened = timeframe_boundary(timestamp, timeframe)
    assert opened.tzinfo is UTC
    assert int(opened.timestamp()) % timeframe.seconds == 0


@pytest.mark.parametrize("timeframe", list(Timeframe))
def test_every_required_timeframe_emits_completed_bar_only_after_boundary(timeframe: Timeframe) -> None:
    opened = datetime(2026, 1, 1, tzinfo=UTC)
    aggregator = CanonicalCandleAggregator(timeframe)
    assert aggregator.push(_tick(opened, 100.0, 100.2)) == ()
    before_close = opened + timedelta(seconds=timeframe.seconds - 1)
    assert aggregator.push(_tick(before_close, 101.0, 101.3, sequence=1)) == ()
    bars = aggregator.push(_tick(opened + timedelta(seconds=timeframe.seconds), 102.0, 102.2, sequence=2))
    assert len(bars) == 1
    bar = bars[0]
    assert bar.status is BarStatus.COMPLETE
    assert bar.opened_at == opened
    assert bar.closed_at == opened + timedelta(seconds=timeframe.seconds)
    assert (bar.open, bar.high, bar.low, bar.close) == (100.0, 101.0, 100.0, 101.0)
    assert (bar.ask_open, bar.ask_high, bar.ask_low, bar.ask_close) == (100.2, 101.3, 100.2, 101.3)
    assert bar.tick_count == 2
    assert bar.volume == 2.0


def test_incomplete_bar_is_not_released_by_early_finalize() -> None:
    opened = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    aggregator = CanonicalCandleAggregator(Timeframe.M5)
    aggregator.push(_tick(opened, 100.0, 100.2))
    assert aggregator.finalize(opened + timedelta(minutes=4, seconds=59)) == ()
    assert len(aggregator.finalize(opened + timedelta(minutes=5))) == 1


def test_aggregation_is_deterministic_and_source_neutral() -> None:
    opened = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    sequence = [
        (opened, 100.0, 100.2),
        (opened + timedelta(minutes=2), 101.0, 101.2),
        (opened + timedelta(minutes=5), 102.0, 102.2),
    ]
    results = []
    for source in ("histdata", "mt5"):
        aggregator = CanonicalCandleAggregator(Timeframe.M5)
        emitted = []
        for index, (timestamp, bid, ask) in enumerate(sequence):
            emitted.extend(aggregator.push(_tick(timestamp, bid, ask, source=source, sequence=index)))
        results.append([bar.semantic_dict() for bar in emitted])
    assert results[0] == results[1]


def test_offset_timestamp_is_converted_to_utc_before_day_aggregation() -> None:
    offset = timezone(timedelta(hours=1))
    timestamp = datetime(2026, 1, 2, 0, 30, tzinfo=offset)
    assert timeframe_boundary(timestamp, Timeframe.D1) == datetime(2026, 1, 1, tzinfo=UTC)


def test_out_of_order_tick_is_rejected() -> None:
    now = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    aggregator = CanonicalCandleAggregator(Timeframe.M1)
    aggregator.push(_tick(now, 100.0, 100.2))
    with pytest.raises(ValueError, match="chronological"):
        aggregator.push(_tick(now - timedelta(seconds=1), 100.0, 100.2))


def test_multi_timeframe_aggregator_uses_the_same_tick_stream() -> None:
    now = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    aggregator = MultiTimeframeAggregator((Timeframe.M1, Timeframe.M5))
    assert aggregator.push(_tick(now, 100.0, 100.2)) == {}
    emitted = aggregator.push(_tick(now + timedelta(minutes=1), 101.0, 101.2, sequence=1))
    assert tuple(emitted) == (Timeframe.M1,)
    emitted = aggregator.push(_tick(now + timedelta(minutes=5), 102.0, 102.2, sequence=2))
    assert set(emitted) == {Timeframe.M1, Timeframe.M5}
