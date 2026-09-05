from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int = 50) -> pd.Series:
    """TradingView-compatible recursive EMA seeded from the first value."""
    return series.ewm(span=length, adjust=False, min_periods=1).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    previous_close = close.shift(1)
    return pd.concat(
        [(high - low), (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 22) -> pd.Series:
    tr = true_range(high, low, close)
    values = np.full(len(tr), np.nan, dtype=float)
    if len(tr) < length:
        return pd.Series(values, index=tr.index, name="atr")
    values[length - 1] = float(tr.iloc[:length].mean())
    for i in range(length, len(tr)):
        values[i] = ((values[i - 1] * (length - 1)) + float(tr.iloc[i])) / length
    return pd.Series(values, index=tr.index, name="atr")


def chandelier_stop(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 22,
    atr_length: int = 22,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    atr = wilder_atr(high, low, close, atr_length)
    raw_long = high.rolling(lookback, min_periods=lookback).max() - multiplier * atr
    raw_short = low.rolling(lookback, min_periods=lookback).min() + multiplier * atr

    long_stop = np.full(len(close), np.nan)
    short_stop = np.full(len(close), np.nan)
    direction = np.zeros(len(close), dtype=np.int8)

    for i in range(len(close)):
        if np.isnan(raw_long.iloc[i]) or np.isnan(raw_short.iloc[i]):
            continue
        if i == 0 or np.isnan(long_stop[i - 1]):
            long_stop[i] = raw_long.iloc[i]
            short_stop[i] = raw_short.iloc[i]
            continue

        short_stop[i] = (
            raw_short.iloc[i]
            if close.iloc[i] > short_stop[i - 1]
            else min(raw_short.iloc[i], short_stop[i - 1])
        )
        long_stop[i] = (
            raw_long.iloc[i]
            if close.iloc[i] < long_stop[i - 1]
            else max(raw_long.iloc[i], long_stop[i - 1])
        )

        long_switch = close.iloc[i] >= short_stop[i - 1] and close.iloc[i - 1] < short_stop[i - 1]
        short_switch = close.iloc[i] <= long_stop[i - 1] and close.iloc[i - 1] > long_stop[i - 1]
        previous_direction = direction[i - 1]
        if previous_direction <= 0 and long_switch:
            direction[i] = 1
        elif previous_direction >= 0 and short_switch:
            direction[i] = -1
        else:
            direction[i] = previous_direction

    active = np.where(direction > 0, long_stop, short_stop)
    return pd.DataFrame(
        {
            "atr": atr,
            "chandelier_long": long_stop,
            "chandelier_short": short_stop,
            "chandelier_direction": direction,
            "chandelier_active": active,
        },
        index=close.index,
    )


def add_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    result = bars.copy()
    result["ema50"] = ema(result["bid_close"], 50)
    chandelier = chandelier_stop(result["bid_high"], result["bid_low"], result["bid_close"])
    return result.join(chandelier)
