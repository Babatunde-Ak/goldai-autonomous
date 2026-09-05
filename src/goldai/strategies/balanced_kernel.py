from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
import pandas as pd

@dataclass(frozen=True)
class EntrySignal:
    signal_index: int
    time: pd.Timestamp
    direction: int
    strategy: str
    stop: float
    level: float | None = None
    note: str = ""


@dataclass(frozen=True)
class VolumeProfile:
    poc: float
    vah: float
    val: float
    low: float
    high: float
    total_weight: float


def _sig(time, i: int, direction: int, strategy: str, stop: float, level: float | None = None, note: str = "") -> EntrySignal:
    return EntrySignal(int(i), pd.Timestamp(time[i]), int(direction), strategy, float(stop), None if level is None else float(level), note)


def _profile_arrays(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, start: int, end: int, bins: int, value_area: float) -> VolumeProfile | None:
    h = high[start:end]; l = low[start:end]; c = close[start:end]; w = np.maximum(volume[start:end], 1.0)
    if len(h) == 0:
        return None
    lo = float(np.nanmin(l)); hi = float(np.nanmax(h))
    if not np.isfinite(lo + hi) or hi <= lo:
        return None
    typical = (h + l + c) / 3.0
    edges = np.linspace(lo, hi, int(bins) + 1)
    idx = np.clip(np.searchsorted(edges, typical, side="right") - 1, 0, int(bins) - 1)
    hist = np.bincount(idx, weights=w, minlength=int(bins)).astype(float)
    total = float(hist.sum())
    if total <= 0:
        return None
    poc_idx = int(np.argmax(hist)); target = total * float(value_area)
    left = right = poc_idx; cum = float(hist[poc_idx])
    while cum < target and (left > 0 or right < int(bins) - 1):
        lv = float(hist[left - 1]) if left > 0 else -1.0
        rv = float(hist[right + 1]) if right < int(bins) - 1 else -1.0
        if rv >= lv and right < int(bins) - 1:
            right += 1; cum += float(hist[right])
        elif left > 0:
            left -= 1; cum += float(hist[left])
        else:
            break
    centers = (edges[:-1] + edges[1:]) / 2.0
    return VolumeProfile(float(centers[poc_idx]), float(edges[right + 1]), float(edges[left]), lo, hi, total)


def volume_profile(frame: pd.DataFrame, bins: int = 36, value_area: float = 0.70) -> VolumeProfile | None:
    high = frame["high"].to_numpy(float); low = frame["low"].to_numpy(float); close = frame["close"].to_numpy(float)
    volume = frame.get("tick_volume", pd.Series(1.0, index=frame.index)).to_numpy(float)
    return _profile_arrays(high, low, close, volume, 0, len(frame), bins, value_area)


def _bias_arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    h1c = df["h1_close"].to_numpy(float); h1e50 = df["h1_ema50"].to_numpy(float); h1e200 = df["h1_ema200"].to_numpy(float)
    h4c = df["entry_h4_close"].to_numpy(float); h4e50 = df["entry_h4_ema50"].to_numpy(float); h4e200 = df["entry_h4_ema200"].to_numpy(float)
    finite = np.isfinite(h1c+h1e50+h1e200+h4c+h4e50+h4e200)
    long_votes = (h1c > h1e200).astype(int) + (h1e50 > h1e200).astype(int) + (h4c > h4e200).astype(int) + (h4e50 > h4e200).astype(int)
    short_votes = (h1c < h1e200).astype(int) + (h1e50 < h1e200).astype(int) + (h4c < h4e200).astype(int) + (h4e50 < h4e200).astype(int)
    return finite & (long_votes >= 3), finite & (short_votes >= 3)


def classify_regime(row: pd.Series) -> str:
    atr_pct = float(row.get("atr_percentile288", np.nan)); adx = float(row.get("m15_adx14", np.nan))
    if np.isfinite(atr_pct) and atr_pct >= 0.80: return "expansion"
    if np.isfinite(adx) and adx >= 23: return "trend"
    if np.isfinite(atr_pct) and atr_pct <= 0.45 and np.isfinite(adx) and adx <= 18: return "quiet_range"
    return "transition"


def generate_volume_profile_retests(df: pd.DataFrame, horizon: int, *, lookback: int = 48, bins: int = 36, value_area: float = 0.70, breakout_buffer_atr: float = 0.10, retest_tolerance_atr: float = 0.20, retest_bars: int = 12, stop_buffer_atr: float = 0.20, min_atr_percentile: float = 0.55, target_level: str = "vah_val", long_only: bool = False, profile_refresh_bars: int = 12) -> list[EntrySignal]:
    time=df["time"].to_numpy(); op=df["open"].to_numpy(float); hi=df["high"].to_numpy(float); lo=df["low"].to_numpy(float); cl=df["close"].to_numpy(float); atrv=df["atr14"].to_numpy(float); atrp=df["atr_percentile288"].to_numpy(float); vol=df.get("tick_volume", pd.Series(1.0,index=df.index)).to_numpy(float)
    long_bias, short_bias = _bias_arrays(df)
    signals=[]; pl=ps=None; profile=None; start=max(300,int(lookback)+2); end=len(df); refresh=max(1,int(profile_refresh_bars))
    for i in range(start,end):
        av=atrv[i]
        if not np.isfinite(av+atrp[i]) or av<=0: continue
        if pl is not None:
            bi,p=pl
            if i-bi>retest_bars: pl=None
            elif i>bi:
                level=p.poc if target_level=="poc" else p.vah
                if lo[i] <= level + retest_tolerance_atr*av and cl[i] > level and cl[i] > op[i] and atrp[i] >= min_atr_percentile and long_bias[i]:
                    signals.append(_sig(time,i,1,f"vp_{target_level}_retest",min(lo[i],level)-stop_buffer_atr*av,level,f"POC={p.poc:.2f};VAH={p.vah:.2f};VAL={p.val:.2f}")); pl=None
        if ps is not None and not long_only:
            bi,p=ps
            if i-bi>retest_bars: ps=None
            elif i>bi:
                level=p.poc if target_level=="poc" else p.val
                if hi[i] >= level - retest_tolerance_atr*av and cl[i] < level and cl[i] < op[i] and atrp[i] >= min_atr_percentile and short_bias[i]:
                    signals.append(_sig(time,i,-1,f"vp_{target_level}_retest",max(hi[i],level)+stop_buffer_atr*av,level,f"POC={p.poc:.2f};VAH={p.vah:.2f};VAL={p.val:.2f}")); ps=None
        if profile is None or (i-start)%refresh==0:
            profile=_profile_arrays(hi,lo,cl,vol,i-lookback,i,bins,value_area)
        if profile is None: continue
        if pl is None and long_bias[i] and cl[i] > profile.vah + breakout_buffer_atr*av: pl=(i,profile)
        if not long_only and ps is None and short_bias[i] and cl[i] < profile.val - breakout_buffer_atr*av: ps=(i,profile)
    return signals



def generate_pdh_pdl_retest_v2(df: pd.DataFrame, horizon: int, *, breakout_buffer_atr: float = 0.10, retest_tolerance_atr: float = 0.20, retest_bars: int = 12, stop_buffer_atr: float = 0.20, min_atr_percentile: float = 0.55, min_body_atr: float = 0.20, allow_long: bool = True, allow_short: bool = True) -> list[EntrySignal]:
    time=df["time"].to_numpy(); op=df["open"].to_numpy(float); hi=df["high"].to_numpy(float); lo=df["low"].to_numpy(float); cl=df["close"].to_numpy(float); atrv=df["atr14"].to_numpy(float); atrp=df["atr_percentile288"].to_numpy(float); pdh=df["entry_prev_day_high"].to_numpy(float); pdl=df["entry_prev_day_low"].to_numpy(float)
    long_bias,short_bias=_bias_arrays(df); day=pd.to_datetime(df["time"],utc=True).dt.floor("D").to_numpy(); signals=[]; pl=ps=None; cur=None
    for i in range(300,len(df)):
        if day[i]!=cur: cur=day[i]; pl=ps=None
        av=atrv[i]
        if not np.isfinite(av+atrp[i]+pdh[i]+pdl[i]) or av<=0: continue
        body=abs(cl[i]-op[i])
        if pl is not None:
            bi=pl
            if i-bi>retest_bars: pl=None
            elif i>bi and lo[i]<=pdh[i]+retest_tolerance_atr*av and cl[i]>pdh[i] and cl[i]>op[i]:
                if allow_long and long_bias[i] and atrp[i]>=min_atr_percentile and body>=min_body_atr*av: signals.append(_sig(time,i,1,"pdh_pdl_retest_v2",min(lo[i],pdh[i])-stop_buffer_atr*av,pdh[i]))
                pl=None
        if ps is not None:
            bi=ps
            if i-bi>retest_bars: ps=None
            elif i>bi and hi[i]>=pdl[i]-retest_tolerance_atr*av and cl[i]<pdl[i] and cl[i]<op[i]:
                if allow_short and short_bias[i] and atrp[i]>=min_atr_percentile and body>=min_body_atr*av: signals.append(_sig(time,i,-1,"pdh_pdl_retest_v2",max(hi[i],pdl[i])+stop_buffer_atr*av,pdl[i]))
                ps=None
        if allow_long and pl is None and long_bias[i] and cl[i]>pdh[i]+breakout_buffer_atr*av: pl=i
        if allow_short and ps is None and short_bias[i] and cl[i]<pdl[i]-breakout_buffer_atr*av: ps=i
    return signals
