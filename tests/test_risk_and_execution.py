from datetime import UTC, datetime

import pytest

from goldai.config import ExecutionMode
from goldai.execution import DisabledMT5DemoExecutionAdapter, ExecutionRequest
from goldai.market import Timeframe
from goldai.risk import AccountType, RiskContext, authorize_execution
from goldai.strategies import Direction, StrategyDecision, StrategyState
from goldai.strategies.models import ExecutionAuthorization


def _decision() -> StrategyDecision:
    return StrategyDecision(
        "test",
        "1",
        "XAUUSD",
        Timeframe.M15,
        datetime(2026, 1, 2, tzinfo=UTC),
        StrategyState.READY,
        Direction.LONG,
        2_600,
        2_590,
        2_630,
        3.0,
    )


@pytest.mark.parametrize(
    "account_type",
    [AccountType.REAL, AccountType.FUNDED, AccountType.CONTEST, AccountType.UNKNOWN],
)
def test_unsafe_account_types_are_blocked(account_type: AccountType) -> None:
    result = authorize_execution(RiskContext(ExecutionMode.PAPER, account_type))
    assert not result.approved
    assert account_type.value in result.reason


def test_authorization_defaults_fail_closed() -> None:
    result = authorize_execution(RiskContext(ExecutionMode.OBSERVE_ONLY, AccountType.UNKNOWN))
    assert not result.approved


def test_demo_execution_is_disabled_in_m0() -> None:
    context = RiskContext(
        ExecutionMode.DEMO,
        AccountType.DEMO,
        ExecutionAuthorization.DEMO,
        spread_acceptable=True,
        data_fresh=True,
        duplicate_signal=False,
        strategy_conflict=False,
        session_allowed=True,
        macro_event_clear=True,
    )
    result = authorize_execution(context)
    assert not result.approved
    assert "Milestone 0" in result.reason


def test_paper_requires_every_control_to_pass() -> None:
    context = RiskContext(
        ExecutionMode.PAPER,
        AccountType.DEMO,
        ExecutionAuthorization.PAPER,
        spread_acceptable=True,
        data_fresh=True,
        duplicate_signal=False,
        strategy_conflict=False,
        session_allowed=True,
        macro_event_clear=True,
    )
    assert authorize_execution(context).approved


def test_disabled_mt5_adapter_cannot_execute() -> None:
    adapter = DisabledMT5DemoExecutionAdapter()
    with pytest.raises(PermissionError, match="disabled"):
        adapter.execute(ExecutionRequest("request-1", _decision(), 0.01))

