from __future__ import annotations

from dataclasses import dataclass

from goldai.market import Timeframe
from goldai.strategies.models import ExecutionAuthorization, StrategyStatus


@dataclass(frozen=True, slots=True)
class StrategyRecord:
    strategy_id: str
    name: str
    version: str
    symbol: str
    timeframe: Timeframe
    status: StrategyStatus
    execution_authorization: ExecutionAuthorization
    research_status: str

    def __post_init__(self) -> None:
        if not all((self.strategy_id.strip(), self.name.strip(), self.version.strip())):
            raise ValueError("strategy identity fields must not be blank")
        if self.status is StrategyStatus.DEMO and self.execution_authorization is not ExecutionAuthorization.DEMO:
            raise ValueError("DEMO status requires explicit DEMO authorization")


class StrategyRegistry:
    def __init__(self) -> None:
        self._records: dict[str, StrategyRecord] = {}

    def register(self, record: StrategyRecord) -> None:
        if record.strategy_id in self._records:
            raise ValueError(f"Duplicate strategy ID: {record.strategy_id}")
        self._records[record.strategy_id] = record

    def get(self, strategy_id: str) -> StrategyRecord:
        try:
            return self._records[strategy_id]
        except KeyError as exc:
            raise KeyError(f"Unknown strategy ID: {strategy_id}") from exc

    def all(self) -> tuple[StrategyRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))


def default_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    definitions = (
        ("ema50_chandelier_m15_touch", "EMA50 + Chandelier M15 Touch", Timeframe.M15),
        ("poc_continuation_retest_long", "POC Continuation Retest Long", Timeframe.M15),
        ("pdh_pdl_breakout_retest", "PDH/PDL Breakout-Retest", Timeframe.M15),
        ("h1_structural_break_trend", "H1 Structural Break Trend", Timeframe.H1),
        ("m15_supply_demand", "M15 Supply/Demand", Timeframe.M15),
        ("liquidity_sweep_scalper", "Future Liquidity Sweep Scalper", Timeframe.M5),
        ("vwap_value_reversion_scalper", "Future VWAP/Value Reversion Scalper", Timeframe.M5),
    )
    for strategy_id, name, timeframe in definitions:
        registry.register(
            StrategyRecord(
                strategy_id=strategy_id,
                name=name,
                version="unimplemented",
                symbol="XAUUSD",
                timeframe=timeframe,
                status=StrategyStatus.RESEARCH,
                execution_authorization=ExecutionAuthorization.NONE,
                research_status="SCAFFOLDED",
            )
        )
    return registry

