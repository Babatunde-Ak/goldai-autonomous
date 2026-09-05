from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _require_aware(value: datetime, name: str = "timestamp") -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_positive_finite(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


def _require_optional_non_negative(value: float | None, name: str) -> None:
    if value is not None and (not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be non-negative and finite when supplied")


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @classmethod
    def parse(cls, value: str) -> Timeframe:
        try:
            return cls(value.strip().upper())
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"Unsupported timeframe: {value!r}") from exc

    @property
    def seconds(self) -> int:
        return {
            Timeframe.M1: 60,
            Timeframe.M5: 300,
            Timeframe.M15: 900,
            Timeframe.M30: 1_800,
            Timeframe.H1: 3_600,
            Timeframe.H4: 14_400,
            Timeframe.D1: 86_400,
        }[self]


class BarStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class MarketTick:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    source: str
    sequence: int | None = None
    last: float | None = None
    bid_volume: float | None = None
    ask_volume: float | None = None
    last_volume: float | None = None
    flags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        _require_aware(self.timestamp)
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))
        _require_positive_finite(self.bid, "bid")
        _require_positive_finite(self.ask, "ask")
        if self.bid > self.ask:
            raise ValueError("bid must be less than or equal to ask")
        if not self.source.strip():
            raise ValueError("source must not be blank")
        object.__setattr__(self, "source", self.source.strip())
        if self.sequence is not None and self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if self.last is not None:
            _require_positive_finite(self.last, "last")
        _require_optional_non_negative(self.bid_volume, "bid_volume")
        _require_optional_non_negative(self.ask_volume, "ask_volume")
        _require_optional_non_negative(self.last_volume, "last_volume")
        object.__setattr__(self, "flags", tuple(sorted(set(self.flags))))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "bid_volume": self.bid_volume,
            "ask_volume": self.ask_volume,
            "last_volume": self.last_volume,
            "source": self.source,
            "sequence": self.sequence,
            "flags": list(self.flags),
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    def semantic_key(self) -> tuple[object, ...]:
        """Source-neutral identity used for duplicate detection and parity checks."""
        return (
            self.symbol,
            self.timestamp,
            self.bid,
            self.ask,
            self.last,
            self.bid_volume,
            self.ask_volume,
            self.last_volume,
        )

    def semantic_dict(self) -> dict[str, Any]:
        """Return source-neutral market content for fingerprints and parity."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "bid_volume": self.bid_volume,
            "ask_volume": self.ask_volume,
            "last_volume": self.last_volume,
        }

    def semantic_json(self) -> str:
        return json.dumps(self.semantic_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, slots=True)
class MarketBar:
    symbol: str
    timeframe: Timeframe
    opened_at: datetime
    closed_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    source: str = "canonical"
    ask_open: float | None = None
    ask_high: float | None = None
    ask_low: float | None = None
    ask_close: float | None = None
    tick_count: int = 0
    spread_min: float | None = None
    spread_mean: float | None = None
    spread_max: float | None = None
    status: BarStatus = BarStatus.COMPLETE

    def __post_init__(self) -> None:
        _require_aware(self.opened_at, "opened_at")
        _require_aware(self.closed_at, "closed_at")
        object.__setattr__(self, "opened_at", self.opened_at.astimezone(UTC))
        object.__setattr__(self, "closed_at", self.closed_at.astimezone(UTC))
        if self.closed_at <= self.opened_at:
            raise ValueError("closed_at must be after opened_at")
        for name, value in (("open", self.open), ("high", self.high), ("low", self.low), ("close", self.close)):
            _require_positive_finite(value, name)
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC values are inconsistent")
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if not math.isfinite(self.volume) or self.volume < 0:
            raise ValueError("volume must be non-negative")
        ask_values = (self.ask_open, self.ask_high, self.ask_low, self.ask_close)
        if any(value is not None for value in ask_values):
            if any(value is None for value in ask_values):
                raise ValueError("ask OHLC values must be supplied together")
            ask_open, ask_high, ask_low, ask_close = ask_values
            assert ask_open is not None and ask_high is not None and ask_low is not None and ask_close is not None
            for name, value in (("ask_open", ask_open), ("ask_high", ask_high), ("ask_low", ask_low), ("ask_close", ask_close)):
                _require_positive_finite(value, name)
            if ask_high < max(ask_open, ask_close) or ask_low > min(ask_open, ask_close) or ask_high < ask_low:
                raise ValueError("ask OHLC values are inconsistent")
            if any(bid > ask for bid, ask in zip((self.open, self.high, self.low, self.close), ask_values, strict=True)):
                raise ValueError("bid OHLC must not exceed ask OHLC")
        if self.tick_count < 0:
            raise ValueError("tick_count must be non-negative")
        for name, value in (("spread_min", self.spread_min), ("spread_mean", self.spread_mean), ("spread_max", self.spread_max)):
            _require_optional_non_negative(value, name)
        supplied_spreads = tuple(value for value in (self.spread_min, self.spread_mean, self.spread_max) if value is not None)
        if supplied_spreads and len(supplied_spreads) != 3:
            raise ValueError("spread statistics must be supplied together")
        if len(supplied_spreads) == 3 and not (self.spread_min <= self.spread_mean <= self.spread_max):
            raise ValueError("spread statistics are inconsistent")

    @property
    def bid_open(self) -> float:
        return self.open

    @property
    def bid_high(self) -> float:
        return self.high

    @property
    def bid_low(self) -> float:
        return self.low

    @property
    def bid_close(self) -> float:
        return self.close

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat(),
            "bid_open": self.open,
            "bid_high": self.high,
            "bid_low": self.low,
            "bid_close": self.close,
            "ask_open": self.ask_open,
            "ask_high": self.ask_high,
            "ask_low": self.ask_low,
            "ask_close": self.ask_close,
            "volume": self.volume,
            "tick_count": self.tick_count,
            "spread_min": self.spread_min,
            "spread_mean": self.spread_mean,
            "spread_max": self.spread_max,
            "status": self.status.value,
            "source": self.source,
        }

    def semantic_dict(self) -> dict[str, Any]:
        """Return source-neutral content for historical/live parity checks."""
        value = self.to_dict()
        value.pop("source")
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, slots=True)
class SymbolSpecification:
    symbol: str
    digits: int
    point: float
    contract_size: float
    minimum_volume: float
    maximum_volume: float
    volume_step: float

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        if self.digits < 0 or self.point <= 0 or self.contract_size <= 0:
            raise ValueError("symbol precision and contract values must be valid")
        if self.minimum_volume <= 0 or self.maximum_volume < self.minimum_volume:
            raise ValueError("volume range is invalid")
        if self.volume_step <= 0:
            raise ValueError("volume_step must be positive")


@dataclass(frozen=True, slots=True)
class SpreadSnapshot:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float

    def __post_init__(self) -> None:
        _require_aware(self.timestamp)
        if self.bid <= 0 or self.ask <= 0 or self.bid > self.ask:
            raise ValueError("spread snapshot requires 0 < bid <= ask")

    @property
    def absolute(self) -> float:
        return self.ask - self.bid


class MarketSession(str, Enum):
    CLOSED = "CLOSED"
    ASIA = "ASIA"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP = "OVERLAP"


@dataclass(frozen=True, slots=True)
class MarketState:
    symbol: str
    timestamp: datetime
    session: MarketSession
    latest_tick: MarketTick | None = None
    latest_bars: dict[Timeframe, MarketBar] = field(default_factory=dict)
    stale: bool = True

    def __post_init__(self) -> None:
        _require_aware(self.timestamp)
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
