from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class EventType(str, Enum):
    SYSTEM_STARTED = "SYSTEM_STARTED"
    SYSTEM_STOPPED = "SYSTEM_STOPPED"
    MARKET_TICK = "MARKET_TICK"
    BAR_CLOSED = "BAR_CLOSED"
    STRATEGY_FORMING = "STRATEGY_FORMING"
    STRATEGY_READY = "STRATEGY_READY"
    STRATEGY_INVALIDATED = "STRATEGY_INVALIDATED"
    STRATEGY_CONFLICT = "STRATEGY_CONFLICT"
    RISK_REJECTED = "RISK_REJECTED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    MT5_CONNECTED = "MT5_CONNECTED"
    MT5_DISCONNECTED = "MT5_DISCONNECTED"
    SPREAD_ABNORMAL = "SPREAD_ABNORMAL"
    NEWS_APPROACHING = "NEWS_APPROACHING"
    DAILY_REPORT_REQUESTED = "DAILY_REPORT_REQUESTED"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    event_type: EventType
    timestamp: datetime
    source: str
    correlation_id: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not all((self.event_id, self.source, self.correlation_id)):
            raise ValueError("event identifiers and source must not be blank")

    @classmethod
    def create(
        cls,
        event_type: EventType,
        timestamp: datetime,
        source: str,
        correlation_id: str,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        body = {
            "event_type": event_type.value,
            "timestamp": timestamp.astimezone(UTC).isoformat(),
            "source": source,
            "correlation_id": correlation_id,
            "payload": payload or {},
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
        event_id = hashlib.sha256(encoded).hexdigest()[:32]
        return cls(event_id, event_type, timestamp, source, correlation_id, payload or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.astimezone(UTC).isoformat(),
            "source": self.source,
            "correlation_id": self.correlation_id,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)

