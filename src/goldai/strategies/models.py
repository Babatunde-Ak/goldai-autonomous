from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
import math
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
class EntryIntent:
    """Unfilled quote-relative geometry. This is not an execution request."""
    semantics: str
    reward_r: float | None = None
    stop_distance: float | None = None
    target_distance: float | None = None
    max_hold_minutes: int | None = None

    def __post_init__(self) -> None:
        if self.semantics not in {'FIRST_QUOTE_AT_OR_AFTER_CLOSE', 'NEXT_BAR_EXECUTABLE_QUOTE'}:
            raise ValueError('unsupported entry semantics')
        for value in (self.reward_r, self.stop_distance, self.target_distance):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError('intent geometry must be positive and finite')
        if self.reward_r is None and (self.stop_distance is None or self.target_distance is None):
            raise ValueError('intent requires reward multiple or stop/target distances')

    def preview(self, direction: Direction, bid: float, ask: float, stop: float | None = None) -> tuple[float,float,float]:
        """Pure hypothetical price geometry, not a fill or order."""
        if direction is Direction.NONE or not all(math.isfinite(p) and p>0 for p in (bid,ask)) or bid>ask:
            raise ValueError('invalid direction or quote')
        sign = 1 if direction is Direction.LONG else -1
        entry = ask if sign==1 else bid
        stop = entry-sign*self.stop_distance if self.stop_distance is not None else stop
        if stop is None or not math.isfinite(stop) or stop<=0:
            raise ValueError('invalid stop')
        risk = sign*(entry-stop)
        if risk<=0:
            raise ValueError('invalid risk geometry')
        target = entry+sign*(self.target_distance if self.target_distance is not None else self.reward_r*risk)
        if target<=0 or not math.isfinite(target):
            raise ValueError('invalid target')
        return entry,stop,target


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
    entry_intent: EntryIntent | None = None
    setup_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not self.strategy_id.strip() or not self.strategy_version.strip():
            raise ValueError("strategy identity must not be blank")
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        prices = (self.entry, self.stop, self.target)
        if any(price is not None and (not math.isfinite(price) or price <= 0) for price in prices):
            raise ValueError("entry, stop, and target must be positive when supplied")
        if self.risk_reward is not None and (not math.isfinite(self.risk_reward) or self.risk_reward <= 0):
            raise ValueError("risk_reward must be positive when supplied")
        if self.state is StrategyState.READY:
            if self.direction is Direction.NONE or (self.entry_intent is None and any(price is None for price in prices)):
                raise ValueError("READY decisions require direction, entry, stop, and target")
            if self.entry_intent is not None and self.entry_intent.stop_distance is None and self.stop is None:
                raise ValueError('candidate requires an absolute stop or stop distance')
        if self.setup_timestamp is not None:
            if self.setup_timestamp.tzinfo is None or self.setup_timestamp.utcoffset() is None:
                raise ValueError('setup timestamp must be timezone-aware')
            if self.setup_timestamp > self.timestamp:
                raise ValueError('setup cannot be in the future')

    @property
    def signal_id(self) -> str | None:
        if self.state is not StrategyState.READY:
            return None
        content = [self.strategy_id, self.strategy_version, self.symbol, self.direction.value,
                   self.timeframe.value, (self.setup_timestamp or self.timestamp).astimezone(UTC).isoformat(),
                   self.timestamp.astimezone(UTC).isoformat(), self.entry, self.stop, self.target,
                   asdict(self.entry_intent) if self.entry_intent else None]
        return hashlib.sha256(json.dumps(content, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["timeframe"] = self.timeframe.value
        value["timestamp"] = self.timestamp.astimezone(UTC).isoformat()
        value["state"] = self.state.value
        value["direction"] = self.direction.value
        value['setup_timestamp'] = self.setup_timestamp.astimezone(UTC).isoformat() if self.setup_timestamp else None
        value['signal_id'] = self.signal_id
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'), allow_nan=False)


class ExecutionAuthorization(str, Enum):
    NONE = "NONE"
    PAPER = "PAPER"
    DEMO = "DEMO"
