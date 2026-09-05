from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
Direction = Literal['LONG', 'SHORT']
Regime = Literal['BULL', 'BEAR', 'NEUTRAL']

@dataclass(frozen=True, slots=True)
class Bar:
    bucket: str
    open_time: str
    close_time: str
    open: float
    high: float
    low: float
    close: float
    ticks: int

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def bullish(self) -> bool:
        return self.close > self.open


@dataclass(frozen=True, slots=True)
class Signal:
    timeframe: str
    direction: Direction
    signal_time: str
    breakout_time: str
    breakout_level: float
    breakout_strength_atr: float
    stop_level: float
    pullback_candles: int
    regime: Regime
