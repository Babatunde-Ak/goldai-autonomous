from __future__ import annotations

from dataclasses import dataclass, replace

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
    implementation_status: str = 'PLACEHOLDER'
    operational: bool = False

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
        ("poc_continuation_retest_long", "POC Continuation Retest Long", Timeframe.M5),
        ("pdh_pdl_breakout_retest", "PDH/PDL Breakout-Retest", Timeframe.M5),
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
                version="1.0.0" if 'scalper' not in strategy_id else "unimplemented",
                symbol="XAUUSD",
                timeframe=timeframe,
                status=StrategyStatus.RESEARCH,
                execution_authorization=ExecutionAuthorization.NONE,
                research_status="SYNTHETIC_SOURCE_PARITY_ONLY" if 'scalper' not in strategy_id else "SCAFFOLDED",
                implementation_status='MIGRATED_CANDIDATE_ONLY' if 'scalper' not in strategy_id else 'PLACEHOLDER',
                operational='scalper' not in strategy_id,
            )
        )
    return registry


def migration_registry() -> StrategyRegistry:
    """Expanded M2 catalog; keep the original seven-ID discovery API compatible."""
    registry = default_registry()
    for key,record in tuple(registry._records.items()):
        if not record.operational:
            registry._records[key]=replace(record,status=StrategyStatus.DISABLED)
    for strategy_id, name, tf, rejected in (
        ('xauusd_structural_break_trend_v1','Structural Break canonical source ID',Timeframe.H1,False),
        ('m15_supply_demand_2r','Supply/Demand independent 2R variant',Timeframe.M15,False),
        ('m5_supply_demand_rejected','M5 Supply/Demand rejected V1',Timeframe.M5,True),
        ('m5_ema_baseline_rejected','Old M5 EMA rejected baseline',Timeframe.M5,True),
        ('ny_orb_research','Future NY ORB',Timeframe.M5,False),
        ('ml_meta_label_gate','Future ML gate',Timeframe.M5,False),
    ):
        operational=strategy_id in ('xauusd_structural_break_trend_v1','m15_supply_demand_2r')
        registry.register(StrategyRecord(strategy_id,name,'1.0.0' if rejected or operational else 'unimplemented',
            'XAUUSD',tf,StrategyStatus.RESEARCH if operational else StrategyStatus.DISABLED,ExecutionAuthorization.NONE,
            'REJECTED' if rejected else 'SYNTHETIC_SOURCE_PARITY_ONLY' if operational else 'NOT_AUTHORIZED',
            'REJECTED' if rejected else 'MIGRATED_CANDIDATE_ONLY' if operational else 'PLACEHOLDER',operational))
    return registry
