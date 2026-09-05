from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from goldai.market import BarStatus, MarketBar, MarketTick, Timeframe


def timeframe_boundary(timestamp: datetime, timeframe: Timeframe) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    utc_timestamp = timestamp.astimezone(UTC)
    epoch_seconds = int(utc_timestamp.timestamp())
    opened_seconds = epoch_seconds - (epoch_seconds % timeframe.seconds)
    return datetime.fromtimestamp(opened_seconds, tz=UTC)


@dataclass(slots=True)
class _WorkingBar:
    symbol: str
    timeframe: Timeframe
    opened_at: datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float
    ask_low: float
    ask_close: float
    tick_count: int
    volume: float
    spread_min: float
    spread_max: float
    spread_sum: float

    @classmethod
    def from_tick(cls, tick: MarketTick, timeframe: Timeframe, opened_at: datetime) -> _WorkingBar:
        volume = tick.last_volume if tick.last_volume is not None else 0.0
        return cls(
            symbol=tick.symbol,
            timeframe=timeframe,
            opened_at=opened_at,
            bid_open=tick.bid,
            bid_high=tick.bid,
            bid_low=tick.bid,
            bid_close=tick.bid,
            ask_open=tick.ask,
            ask_high=tick.ask,
            ask_low=tick.ask,
            ask_close=tick.ask,
            tick_count=1,
            volume=volume,
            spread_min=tick.spread,
            spread_max=tick.spread,
            spread_sum=tick.spread,
        )

    def update(self, tick: MarketTick) -> None:
        self.bid_high = max(self.bid_high, tick.bid)
        self.bid_low = min(self.bid_low, tick.bid)
        self.bid_close = tick.bid
        self.ask_high = max(self.ask_high, tick.ask)
        self.ask_low = min(self.ask_low, tick.ask)
        self.ask_close = tick.ask
        self.tick_count += 1
        self.volume += tick.last_volume if tick.last_volume is not None else 0.0
        self.spread_min = min(self.spread_min, tick.spread)
        self.spread_max = max(self.spread_max, tick.spread)
        self.spread_sum += tick.spread

    def complete(self) -> MarketBar:
        return MarketBar(
            symbol=self.symbol,
            timeframe=self.timeframe,
            opened_at=self.opened_at,
            closed_at=self.opened_at + timedelta(seconds=self.timeframe.seconds),
            open=self.bid_open,
            high=self.bid_high,
            low=self.bid_low,
            close=self.bid_close,
            volume=self.volume,
            source="canonical",
            ask_open=self.ask_open,
            ask_high=self.ask_high,
            ask_low=self.ask_low,
            ask_close=self.ask_close,
            tick_count=self.tick_count,
            spread_min=self.spread_min,
            spread_mean=self.spread_sum / self.tick_count,
            spread_max=self.spread_max,
            status=BarStatus.COMPLETE,
        )


class CanonicalCandleAggregator:
    """Deterministic UTC tick aggregation that emits completed bars only."""

    def __init__(self, timeframe: Timeframe | str) -> None:
        self.timeframe = Timeframe.parse(timeframe) if isinstance(timeframe, str) else timeframe
        self._current: _WorkingBar | None = None
        self._last_timestamp: datetime | None = None

    @property
    def current_opened_at(self) -> datetime | None:
        return self._current.opened_at if self._current else None

    def push(self, tick: MarketTick) -> tuple[MarketBar, ...]:
        if self._last_timestamp is not None and tick.timestamp < self._last_timestamp:
            raise ValueError("ticks must be supplied in chronological order")
        self._last_timestamp = tick.timestamp
        opened_at = timeframe_boundary(tick.timestamp, self.timeframe)
        if self._current is None:
            self._current = _WorkingBar.from_tick(tick, self.timeframe, opened_at)
            return ()
        if tick.symbol != self._current.symbol:
            raise ValueError("one aggregator instance accepts one symbol")
        if opened_at < self._current.opened_at:
            raise ValueError("tick belongs to an earlier candle")
        if opened_at == self._current.opened_at:
            self._current.update(tick)
            return ()
        completed = self._current.complete()
        self._current = _WorkingBar.from_tick(tick, self.timeframe, opened_at)
        return (completed,)

    def finalize(self, observed_until: datetime) -> tuple[MarketBar, ...]:
        """Close the current bar only when its full boundary has been observed."""
        if observed_until.tzinfo is None or observed_until.utcoffset() is None:
            raise ValueError("observed_until must be timezone-aware")
        if self._current is None:
            return ()
        boundary = self._current.opened_at + timedelta(seconds=self.timeframe.seconds)
        if observed_until.astimezone(UTC) < boundary:
            return ()
        completed = self._current.complete()
        self._current = None
        return (completed,)


class MultiTimeframeAggregator:
    def __init__(self, timeframes: tuple[Timeframe, ...] | None = None) -> None:
        selected = timeframes or tuple(Timeframe)
        self._aggregators = {timeframe: CanonicalCandleAggregator(timeframe) for timeframe in selected}

    def push(self, tick: MarketTick) -> dict[Timeframe, tuple[MarketBar, ...]]:
        return {
            timeframe: bars
            for timeframe, aggregator in self._aggregators.items()
            if (bars := aggregator.push(tick))
        }

    def finalize(self, observed_until: datetime) -> dict[Timeframe, tuple[MarketBar, ...]]:
        return {
            timeframe: bars
            for timeframe, aggregator in self._aggregators.items()
            if (bars := aggregator.finalize(observed_until))
        }
