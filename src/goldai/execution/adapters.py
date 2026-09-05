from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from goldai.strategies.models import StrategyDecision


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    request_id: str
    decision: StrategyDecision
    volume: float


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    accepted: bool
    adapter: str
    message: str
    timestamp: datetime
    external_id: str | None = None


class PaperExecutionAdapter(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult: ...


class MT5ObserveAdapter(Protocol):
    def account_snapshot(self) -> dict[str, object]: ...

    def latest_tick(self, symbol: str) -> object: ...


class MT5DemoExecutionAdapter(Protocol):
    def execute(self, request: ExecutionRequest) -> ExecutionResult: ...


class DisabledMT5DemoExecutionAdapter:
    """Explicit non-operational boundary for Milestone 0."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise PermissionError("MT5 DEMO execution is disabled in Milestone 0")

