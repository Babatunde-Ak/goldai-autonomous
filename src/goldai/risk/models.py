from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from goldai.config.models import ExecutionMode
from goldai.strategies.models import ExecutionAuthorization, StrategyDecision


class AccountType(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"
    FUNDED = "FUNDED"
    CONTEST = "CONTEST"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RiskContext:
    execution_mode: ExecutionMode
    account_type: AccountType
    strategy_authorization: ExecutionAuthorization = ExecutionAuthorization.NONE
    spread_acceptable: bool = False
    data_fresh: bool = False
    duplicate_signal: bool = True
    strategy_conflict: bool = True
    session_allowed: bool = False
    macro_event_clear: bool = False


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reason: str


class RiskPolicy(Protocol):
    def evaluate(self, decision: StrategyDecision, context: RiskContext) -> RiskDecision: ...


def authorize_execution(context: RiskContext) -> RiskDecision:
    """Fail-closed authorization. Paper may be authorized, MT5 DEMO stays disabled."""
    if context.account_type in {
        AccountType.REAL,
        AccountType.FUNDED,
        AccountType.CONTEST,
        AccountType.UNKNOWN,
    }:
        return RiskDecision(False, f"Account type {context.account_type.value} is blocked")
    if context.execution_mode in {ExecutionMode.RESEARCH, ExecutionMode.OBSERVE_ONLY}:
        return RiskDecision(False, f"Mode {context.execution_mode.value} does not authorize execution")
    if context.execution_mode is ExecutionMode.DEMO:
        return RiskDecision(False, "MT5 DEMO execution is disabled in Milestone 0 and Milestone 1")
    if context.strategy_authorization is not ExecutionAuthorization.PAPER:
        return RiskDecision(False, "Strategy lacks PAPER authorization")
    checks = {
        "spread is unacceptable": context.spread_acceptable,
        "market data is stale": context.data_fresh,
        "duplicate signal detected": not context.duplicate_signal,
        "strategy conflict detected": not context.strategy_conflict,
        "session is blocked": context.session_allowed,
        "macro-event veto is active": context.macro_event_clear,
    }
    for reason, passed in checks.items():
        if not passed:
            return RiskDecision(False, reason)
    return RiskDecision(True, "PAPER execution authorized")
