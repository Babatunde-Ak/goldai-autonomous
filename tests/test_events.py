import json
from datetime import UTC, datetime

from goldai.events import Event, EventType


def test_event_serialization_is_deterministic() -> None:
    timestamp = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    first = Event.create(EventType.SYSTEM_STARTED, timestamp, "core", "run-1", {"mode": "OBSERVE_ONLY"})
    second = Event.create(EventType.SYSTEM_STARTED, timestamp, "core", "run-1", {"mode": "OBSERVE_ONLY"})
    assert first.event_id == second.event_id
    assert json.loads(first.to_json())["event_type"] == "SYSTEM_STARTED"


def test_event_id_changes_with_payload() -> None:
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)
    first = Event.create(EventType.MARKET_TICK, timestamp, "feed", "run-1", {"sequence": 1})
    second = Event.create(EventType.MARKET_TICK, timestamp, "feed", "run-1", {"sequence": 2})
    assert first.event_id != second.event_id

