"""Frozen GoldAI 1.2 feature semantics, computed from canonical Bid bars.

HTF values are aligned to M5 OPEN time as in the original, even though the
decision happens at M5 close. Do not change this lag during migration.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous = frame['close'].shift(1)
    return pd.concat([frame.high-frame.low, (frame.high-previous).abs(),
                      (frame.low-previous).abs()], axis=1).max(axis=1)


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(frame).ewm(alpha=1/period, adjust=False, min_periods=period).mean()


def adx_components(frame: pd.DataFrame, period: int = 14):
    up, down = frame.high.astype(float).diff(), -frame.low.astype(float).diff()
    plus = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=frame.index)
    minus = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=frame.index)
    tr = atr(frame, period).replace(0.0, np.nan)
    plus = 100 * plus.ewm(alpha=1/period, adjust=False, min_periods=period).mean()/tr
    minus = 100 * minus.ewm(alpha=1/period, adjust=False, min_periods=period).mean()/tr
    dx = 100 * (plus-minus).abs()/(plus+minus).replace(0.0, np.nan)
    adx = dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    return adx.fillna(0.0), plus.fillna(0.0), minus.fillna(0.0)


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out['atr14'] = atr(out)
    out['atr_percentile288'] = out.atr14.rolling(288, min_periods=96).rank(pct=True)
    indexed = out.set_index('time')
    for rule, prefix in [('1h', 'h1'), ('4h', 'entry_h4')]:
        bars = indexed[['open', 'high', 'low', 'close']].resample(
            rule, label='right', closed='left').agg(
                {'open':'first', 'high':'max', 'low':'min', 'close':'last'}).dropna()
        bars['ema50'] = ema(bars.close, 50)
        bars['ema200'] = ema(bars.close, 200)
        bars['adx14'], bars['plus_di14'], bars['minus_di14'] = adx_components(bars)
        aligned = bars.reindex(indexed.index, method='ffill')
        for col in ['close', 'ema50', 'ema200', 'adx14', 'plus_di14', 'minus_di14']:
            out[f'{prefix}_{col}'] = aligned[col].to_numpy()
    out['h4_adx14'] = out['entry_h4_adx14']
    daily = indexed[['high','low']].resample('1D', label='left', closed='left').agg(
        {'high':'max','low':'min'})
    previous = daily.shift(1).reindex(indexed.index, method='ffill')
    out['entry_prev_day_high'] = previous.high.to_numpy()
    out['entry_prev_day_low'] = previous.low.to_numpy()
    return out
