from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

import numpy as np
import pandas as pd

from goldai.indicators.ema_chandelier import add_indicators


class SetupState(str, Enum):
    WAITING_FOR_EMA_BREAK = "WAITING_FOR_EMA_BREAK"
    WAITING_FOR_PULLBACK = "WAITING_FOR_PULLBACK"
    WAITING_FOR_STRUCTURE_BREAK = "WAITING_FOR_STRUCTURE_BREAK"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    AVOIDED = "AVOIDED"
    ENTERED = "ENTERED"
    CLOSED = "CLOSED"


class SetupReason(str, Enum):
    NONE = "NONE"
    EMA_WICK_ONLY = "EMA_WICK_ONLY"
    EMA_RECROSS = "EMA_RECROSS"
    INSUFFICIENT_PULLBACK = "INSUFFICIENT_PULLBACK"
    STRUCTURE_WICK_ONLY = "STRUCTURE_WICK_ONLY"
    OVERSIZED_STRUCTURE_BREAKOUT = "OVERSIZED_STRUCTURE_BREAKOUT"
    INVALID_CHANDELIER_STOP = "INVALID_CHANDELIER_STOP"
    INVALID_RISK = "INVALID_RISK"
    STALE_SETUP = "STALE_SETUP"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TIMEOUT_PROFIT_EXIT = "TIMEOUT_PROFIT_EXIT"
    END_OF_DATA = "END_OF_DATA"


@dataclass(frozen=True)
class VideoSourceConfig:
    ema_invalidation_mode: str = "close"  # close or touch
    breakout_average_lookback: int = 20
    oversized_breakout_multiple: float = 3.0
    minimum_pullback_candles: int = 2
    reward_r: float = 2.0

    def __post_init__(self) -> None:
        if self.ema_invalidation_mode not in {"close", "touch"}:
            raise ValueError("ema_invalidation_mode must be close or touch")
        if self.breakout_average_lookback < 1:
            raise ValueError("breakout_average_lookback must be positive")
        if self.oversized_breakout_multiple <= 0:
            raise ValueError("oversized_breakout_multiple must be positive")
        if self.minimum_pullback_candles < 2:
            raise ValueError("minimum_pullback_candles must be at least two")


@dataclass
class Setup:
    setup_id: str
    direction: str
    state: SetupState
    ema_break_index: int
    ema_break_time: pd.Timestamp
    pullback_start_index: int | None = None
    pullback_start_time: pd.Timestamp | None = None
    pullback_count: int = 0
    structure_price: float | None = None
    structure_index: int | None = None
    structure_time: pd.Timestamp | None = None
    structure_break_time: pd.Timestamp | None = None
    wick_only_structure_break_count: int = 0
    breakout_range: float | None = None
    average_range: float | None = None
    breakout_multiple: float | None = None
    chandelier_stop: float | None = None
    signal_close: float | None = None
    risk_reference: float | None = None
    entry_allowed: bool = False
    reason: SetupReason = SetupReason.NONE

    def as_record(self) -> dict:
        row = asdict(self)
        row["state"] = self.state.value
        row["reason"] = self.reason.value
        for key in (
            "ema_break_time",
            "pullback_start_time",
            "structure_time",
            "structure_break_time",
        ):
            value = row[key]
            row[key] = "" if value is None else str(value)
        return row


@dataclass
class DetectionResult:
    bars: pd.DataFrame
    audits: list[Setup]
    ema_wick_only_long: int
    ema_wick_only_short: int



def _indicator_bars(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"bid_open", "bid_high", "bid_low", "bid_close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Missing Bid OHLC columns: {sorted(missing)}")
    base = bars.drop(columns=[
        column
        for column in ("ema50", "atr", "chandelier_long", "chandelier_short", "chandelier_direction", "chandelier_active")
        if column in bars.columns
    ])
    return add_indicators(base)


def _invalidated(row: pd.Series, direction: str, mode: str) -> bool:
    if direction == "long":
        return bool((row["bid_close"] if mode == "close" else row["bid_low"]) < row["ema50"])
    return bool((row["bid_close"] if mode == "close" else row["bid_high"]) > row["ema50"])


def detect_setups(bars: pd.DataFrame, config: VideoSourceConfig | None = None) -> DetectionResult:
    config = config or VideoSourceConfig()
    out = _indicator_bars(bars)
    candle_range = out["bid_high"] - out["bid_low"]
    out["previous_average_range"] = candle_range.shift(1).rolling(
        config.breakout_average_lookback,
        min_periods=config.breakout_average_lookback,
    ).mean()
    out["setup_id"] = ""
    out["signal"] = ""
    out["signal_close"] = np.nan
    out["stop_loss"] = np.nan
    out["risk_reference"] = np.nan
    out["take_profit_reference"] = np.nan
    out["event"] = ""

    audits: list[Setup] = []
    active: Setup | None = None
    setup_number = 0
    wick_ema_long = 0
    wick_ema_short = 0

    def event(i: int, value: str) -> None:
        column = out.columns.get_loc("event")
        current = str(out.iat[i, column])
        out.iat[i, column] = value if not current else f"{current}|{value}"

    def finish(setup: Setup, state: SetupState, reason: SetupReason) -> None:
        nonlocal active
        setup.state = state
        setup.reason = reason
        audits.append(setup)
        active = None

    for i in range(1, len(out)):
        row = out.iloc[i]
        previous = out.iloc[i - 1]
        timestamp = pd.Timestamp(out.index[i])
        if not np.isfinite(row["ema50"]):
            continue

        if row["bid_high"] > row["ema50"] and row["bid_close"] <= row["ema50"]:
            wick_ema_long += 1
            event(i, SetupReason.EMA_WICK_ONLY.value + "_LONG")
        if row["bid_low"] < row["ema50"] and row["bid_close"] >= row["ema50"]:
            wick_ema_short += 1
            event(i, SetupReason.EMA_WICK_ONLY.value + "_SHORT")

        if active is not None and _invalidated(row, active.direction, config.ema_invalidation_mode):
            event(i, SetupReason.EMA_RECROSS.value)
            finish(active, SetupState.INVALIDATED, SetupReason.EMA_RECROSS)
            continue

        if active is None:
            bullish_break = previous["bid_close"] <= previous["ema50"] and row["bid_close"] > row["ema50"]
            bearish_break = previous["bid_close"] >= previous["ema50"] and row["bid_close"] < row["ema50"]
            if not bullish_break and not bearish_break:
                continue
            setup_number += 1
            direction = "long" if bullish_break else "short"
            active = Setup(
                setup_id=f"VS1-{setup_number:06d}",
                direction=direction,
                state=SetupState.WAITING_FOR_PULLBACK,
                ema_break_index=i,
                ema_break_time=timestamp,
            )
            event(i, f"EMA_CLOSE_BREAK_{direction.upper()}")
            continue

        opposing = (
            row["bid_close"] < row["bid_open"]
            if active.direction == "long"
            else row["bid_close"] > row["bid_open"]
        )
        if active.state == SetupState.WAITING_FOR_PULLBACK:
            if not opposing:
                if 0 < active.pullback_count < config.minimum_pullback_candles:
                    event(i, SetupReason.INSUFFICIENT_PULLBACK.value)
                active.pullback_count = 0
                active.pullback_start_index = None
                active.pullback_start_time = None
                active.structure_price = None
                active.structure_index = None
                active.structure_time = None
                continue
            if active.pullback_count == 0:
                active.pullback_start_index = i
                active.pullback_start_time = timestamp
                segment = out.iloc[active.ema_break_index:i]
                if segment.empty:
                    continue
                if active.direction == "long":
                    structure_label = segment["bid_high"].idxmax()
                    active.structure_price = float(segment.loc[structure_label, "bid_high"])
                else:
                    structure_label = segment["bid_low"].idxmin()
                    active.structure_price = float(segment.loc[structure_label, "bid_low"])
                active.structure_index = int(out.index.get_loc(structure_label))
                active.structure_time = pd.Timestamp(structure_label)
            active.pullback_count += 1
            if active.pullback_count >= config.minimum_pullback_candles:
                active.state = SetupState.WAITING_FOR_STRUCTURE_BREAK
                event(i, "PULLBACK_CONFIRMED")
            continue

        assert active.structure_price is not None
        wick_break = (
            row["bid_high"] > active.structure_price and row["bid_close"] <= active.structure_price
            if active.direction == "long"
            else row["bid_low"] < active.structure_price and row["bid_close"] >= active.structure_price
        )
        if wick_break:
            active.wick_only_structure_break_count += 1
            event(i, SetupReason.STRUCTURE_WICK_ONLY.value)

        confirmed = (
            row["bid_close"] > active.structure_price
            if active.direction == "long"
            else row["bid_close"] < active.structure_price
        )
        if not confirmed:
            continue

        active.structure_break_time = timestamp
        active.breakout_range = float(row["bid_high"] - row["bid_low"])
        active.average_range = float(row["previous_average_range"])
        active.breakout_multiple = (
            active.breakout_range / active.average_range
            if np.isfinite(active.average_range) and active.average_range > 0
            else np.nan
        )
        if not np.isfinite(active.breakout_multiple) or active.breakout_multiple >= config.oversized_breakout_multiple:
            event(i, SetupReason.OVERSIZED_STRUCTURE_BREAKOUT.value)
            finish(active, SetupState.AVOIDED, SetupReason.OVERSIZED_STRUCTURE_BREAKOUT)
            continue

        active.signal_close = float(row["bid_close"])
        active.chandelier_stop = float(
            row["chandelier_long"] if active.direction == "long" else row["chandelier_short"]
        )
        active.risk_reference = (
            active.signal_close - active.chandelier_stop
            if active.direction == "long"
            else active.chandelier_stop - active.signal_close
        )
        if not np.isfinite(active.chandelier_stop) or active.risk_reference <= 0:
            event(i, SetupReason.INVALID_CHANDELIER_STOP.value)
            finish(active, SetupState.AVOIDED, SetupReason.INVALID_CHANDELIER_STOP)
            continue

        active.entry_allowed = True
        active.state = SetupState.CONFIRMED
        out.iat[i, out.columns.get_loc("setup_id")] = active.setup_id
        out.iat[i, out.columns.get_loc("signal")] = active.direction
        out.iat[i, out.columns.get_loc("signal_close")] = active.signal_close
        out.iat[i, out.columns.get_loc("stop_loss")] = active.chandelier_stop
        out.iat[i, out.columns.get_loc("risk_reference")] = active.risk_reference
        target = (
            active.signal_close + config.reward_r * active.risk_reference
            if active.direction == "long"
            else active.signal_close - config.reward_r * active.risk_reference
        )
        out.iat[i, out.columns.get_loc("take_profit_reference")] = target
        event(i, "STRUCTURE_CLOSE_CONFIRMED")
        finish(active, SetupState.CONFIRMED, SetupReason.NONE)

    if active is not None:
        reason = SetupReason.INSUFFICIENT_PULLBACK if active.state == SetupState.WAITING_FOR_PULLBACK else SetupReason.STALE_SETUP
        finish(active, SetupState.INVALIDATED, reason)

    return DetectionResult(out, audits, wick_ema_long, wick_ema_short)
