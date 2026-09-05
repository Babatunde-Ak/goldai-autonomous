from datetime import UTC, datetime

import pytest

from goldai.market import Timeframe
from goldai.strategies import (
    Direction,
    StrategyDecision,
    StrategyRecord,
    StrategyRegistry,
    StrategyState,
    StrategyStatus,
    default_registry,
)
from goldai.strategies.models import ExecutionAuthorization


NOW = datetime(2026, 1, 2, tzinfo=UTC)


def test_strategy_states_are_explicit() -> None:
    assert {item.value for item in StrategyState} == {
        "IDLE",
        "FORMING",
        "WAITING",
        "READY",
        "INVALIDATED",
        "COOLDOWN",
    }


def test_strategy_decision_serialization() -> None:
    decision = StrategyDecision(
        strategy_id="test",
        strategy_version="1.0.0",
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        timestamp=NOW,
        state=StrategyState.READY,
        direction=Direction.LONG,
        entry=2_600,
        stop=2_590,
        target=2_630,
        risk_reward=3.0,
        reason="test fixture",
    )
    value = decision.to_dict()
    assert value["state"] == "READY"
    assert value["timeframe"] == "M15"
    assert value["direction"] == "LONG"


def test_ready_decision_requires_prices_and_direction() -> None:
    with pytest.raises(ValueError, match="READY decisions"):
        StrategyDecision("test", "1", "XAUUSD", Timeframe.M5, NOW, StrategyState.READY)


def _record(strategy_id: str = "one") -> StrategyRecord:
    return StrategyRecord(
        strategy_id=strategy_id,
        name="Test",
        version="unimplemented",
        symbol="XAUUSD",
        timeframe=Timeframe.M15,
        status=StrategyStatus.RESEARCH,
        execution_authorization=ExecutionAuthorization.NONE,
        research_status="SCAFFOLDED",
    )


def test_registry_registers_and_gets_record() -> None:
    registry = StrategyRegistry()
    registry.register(_record())
    assert registry.get("one").symbol == "XAUUSD"


def test_registry_rejects_duplicate_strategy_ids() -> None:
    registry = StrategyRegistry()
    registry.register(_record())
    with pytest.raises(ValueError, match="Duplicate strategy ID"):
        registry.register(_record())


def test_default_registry_has_seven_unauthorized_research_entries() -> None:
    records = default_registry().all()
    assert len(records) == 7
    assert all(item.status is StrategyStatus.RESEARCH for item in records)
    assert all(item.execution_authorization is ExecutionAuthorization.NONE for item in records)

