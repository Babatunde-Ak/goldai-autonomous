from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def _require_aware(value: datetime, name: str = "timestamp") -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


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


@dataclass(frozen=True, slots=True)
class MarketTick:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    source: str
    sequence: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        _require_aware(self.timestamp)
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError("bid and ask must be positive")
        if self.bid > self.ask:
            raise ValueError("bid must be less than or equal to ask")
        if not self.source.strip():
            raise ValueError("source must not be blank")
        if self.sequence is not None and self.sequence < 0:
            raise ValueError("sequence must be non-negative")

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["timestamp"] = self.timestamp.astimezone(UTC).isoformat()
        return value


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

    def __post_init__(self) -> None:
        _require_aware(self.opened_at, "opened_at")
        _require_aware(self.closed_at, "closed_at")
        if self.closed_at <= self.opened_at:
            raise ValueError("closed_at must be after opened_at")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC values must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC values are inconsistent")
        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")


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

