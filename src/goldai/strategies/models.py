from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from goldai.market import Timeframe


class StrategyState(str, Enum):
    IDLE = "IDLE"
    FORMING = "FORMING"
    WAITING = "WAITING"
    READY = "READY"
    INVALIDATED = "INVALIDATED"
    COOLDOWN = "COOLDOWN"


class StrategyStatus(str, Enum):
    RESEARCH = "RESEARCH"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    DEMO = "DEMO"
    DISABLED = "DISABLED"


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    strategy_id: str
    strategy_version: str
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    state: StrategyState
    direction: Direction = Direction.NONE
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    risk_reward: float | None = None
    invalidation: str | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not self.strategy_id.strip() or not self.strategy_version.strip():
            raise ValueError("strategy identity must not be blank")
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        prices = (self.entry, self.stop, self.target)
        if any(price is not None and price <= 0 for price in prices):
            raise ValueError("entry, stop, and target must be positive when supplied")
        if self.risk_reward is not None and self.risk_reward <= 0:
            raise ValueError("risk_reward must be positive when supplied")
        if self.state is StrategyState.READY:
            if self.direction is Direction.NONE or any(price is None for price in prices):
                raise ValueError("READY decisions require direction, entry, stop, and target")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["timeframe"] = self.timeframe.value
        value["timestamp"] = self.timestamp.astimezone(UTC).isoformat()
        value["state"] = self.state.value
        value["direction"] = self.direction.value
        return value


class ExecutionAuthorization(str, Enum):
    NONE = "NONE"
    PAPER = "PAPER"
    DEMO = "DEMO"

