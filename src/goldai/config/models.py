from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from goldai.market import Timeframe


class ExecutionMode(str, Enum):
    RESEARCH = "RESEARCH"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    PAPER = "PAPER"
    DEMO = "DEMO"


@dataclass(frozen=True, slots=True)
class RiskLimits:
    maximum_position_risk_pct: float = 0.25
    maximum_total_exposure_pct: float = 0.50
    maximum_concurrent_positions: int = 1
    daily_loss_lock_pct: float = 1.0

    def __post_init__(self) -> None:
        if min(self.maximum_position_risk_pct, self.maximum_total_exposure_pct, self.daily_loss_lock_pct) <= 0:
            raise ValueError("risk percentages must be positive")
        if self.maximum_concurrent_positions < 1:
            raise ValueError("maximum_concurrent_positions must be at least one")


@dataclass(frozen=True, slots=True)
class GoldAIConfig:
    execution_mode: ExecutionMode = ExecutionMode.OBSERVE_ONLY
    symbols: tuple[str, ...] = ("XAUUSD",)
    timeframes: tuple[Timeframe, ...] = (Timeframe.M5, Timeframe.M15, Timeframe.H1)
    enabled_strategies: tuple[str, ...] = ()
    market_data_source: str = "NOT_CONFIGURED"
    storage_url: str = "sqlite:///data/goldai.db"
    log_level: str = "INFO"
    risk: RiskLimits = field(default_factory=RiskLimits)

    def __post_init__(self) -> None:
        if not self.symbols or any(not symbol.strip() for symbol in self.symbols):
            raise ValueError("at least one valid symbol is required")
        if self.execution_mode is ExecutionMode.DEMO:
            raise ValueError("DEMO mode cannot be enabled by Milestone 0 configuration")


def _config_from_dict(data: dict[str, Any]) -> GoldAIConfig:
    risk_data = data.get("risk", {})
    return GoldAIConfig(
        execution_mode=ExecutionMode(data.get("execution_mode", "OBSERVE_ONLY")),
        symbols=tuple(data.get("symbols", ["XAUUSD"])),
        timeframes=tuple(Timeframe.parse(item) for item in data.get("timeframes", ["M5", "M15", "H1"])),
        enabled_strategies=tuple(data.get("enabled_strategies", [])),
        market_data_source=data.get("market_data_source", "NOT_CONFIGURED"),
        storage_url=data.get("storage_url", "sqlite:///data/goldai.db"),
        log_level=data.get("log_level", "INFO"),
        risk=RiskLimits(**risk_data),
    )


def load_config(path: str | Path | None = None) -> GoldAIConfig:
    if path is None:
        return GoldAIConfig()
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("configuration root must be an object")
    return _config_from_dict(data)

