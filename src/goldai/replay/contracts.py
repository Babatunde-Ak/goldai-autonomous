from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from goldai.replay import ENGINE_VERSION, STRATEGIES


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def source_hash(strategy_only=False) -> str:
    root = Path(__file__).parents[1]
    return fingerprint({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(root.rglob("*.py"))
                        if not strategy_only or p.relative_to(root).parts[0] in {"strategies", "indicators"}})


@dataclass(frozen=True)
class CostModel:
    commission_r: float = 0.0
    swap_r_per_day: float = 0.0
    adverse_slippage: float = 0.0
    entry_delay_ticks: int = 0
    entry_delay_seconds: float = 0.0
    spread_multiplier: float = 1.0

    def __post_init__(self):
        for value in asdict(self).values():
            if not math.isfinite(value) or value < 0:
                raise ValueError("costs must be finite and nonnegative")
        if type(self.entry_delay_ticks) is not int:
            raise ValueError("tick delay must be an integer")
        if self.spread_multiplier != 1:
            raise ValueError("true Bid/Ask already contains spread")


@dataclass(frozen=True)
class ReplayConfig:
    strategy_id: str
    data_fingerprint: str
    data_manifest_sha: str
    code_commit: str
    data_usage: str = "SYNTHETIC"
    exit_mode: str = "ACCEPTED"
    costs: CostModel = field(default_factory=CostModel)
    symbol: str = "XAUUSD"

    def __post_init__(self):
        if self.strategy_id not in STRATEGIES:
            raise ValueError("strategy is disabled or not replay capable")
        if self.symbol != "XAUUSD":
            raise ValueError("M3 supports XAUUSD only")
        if not all((self.data_fingerprint, self.data_manifest_sha, self.code_commit)):
            raise ValueError("data and code identities are required")
        if self.data_usage not in {"SYNTHETIC", "DEVELOPMENT", "ROBUSTNESS", "EVALUATION", "PREVIOUSLY_CONSUMED"}:
            raise ValueError("locked or unclassified data cannot be replayed")
        if self.exit_mode not in {"ACCEPTED", "FIXED_R", "SOURCE_CONTROL"}:
            raise ValueError("unsupported exit mode")
        if self.exit_mode == "SOURCE_CONTROL" and self.strategy_id not in {
                STRATEGIES[0], STRATEGIES[3]}:
            raise ValueError("exact source exit control unavailable")

    @property
    def resolved_exit_mode(self):
        if self.exit_mode != "ACCEPTED":
            return self.exit_mode
        if self.strategy_id == STRATEGIES[3]:
            return "SOURCE_CONTROL"
        if self.strategy_id.startswith("m15_supply"):
            return "FIXED_R_RESTING_TARGET"
        return "FIXED_R"

    @property
    def position_limit(self):
        return None if self.strategy_id == STRATEGIES[0] else 1


@dataclass
class TradeRecord:
    trade_id: str
    signal_id: str
    strategy_id: str
    strategy_version: str
    direction: str
    timeframe: str
    setup_timestamp: str
    signal_timestamp: str
    intent: dict
    source_metadata: dict
    signal_cursor: int
    state: str = "PENDING_ENTRY"
    eligible_cursor: int | None = None
    entry_timestamp: str | None = None
    entry_cursor: int | None = None
    entry_price: float | None = None
    entry_quote: float | None = None
    entry_side: str | None = None
    entry_delay_ticks: int | None = None
    entry_delay_seconds: float | None = None
    stop: float | None = None
    target: float | None = None
    initial_risk: float | None = None
    exit_timestamp: str | None = None
    exit_cursor: int | None = None
    exit_price: float | None = None
    exit_quote: float | None = None
    exit_side: str | None = None
    exit_reason: str | None = None
    slippage_to_level: float | None = None
    pnl_price: float | None = None
    gross_r: float | None = None
    realized_r: float | None = None
    cost_adjusted_r: float | None = None
    mfe_price: float = 0.0
    mae_price: float = 0.0
    mfe_r: float = 0.0
    mae_r: float = 0.0
    time_to_mfe_seconds: float = 0.0
    time_to_mae_seconds: float = 0.0
    holding_seconds: float = 0.0
    flags: list[str] = field(default_factory=list)

    @property
    def sign(self):
        return 1 if self.direction == "LONG" else -1

    def elapsed(self, timestamp: datetime):
        return (timestamp - datetime.fromisoformat(self.entry_timestamp)).total_seconds()
