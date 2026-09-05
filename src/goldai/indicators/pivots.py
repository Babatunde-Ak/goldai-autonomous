from __future__ import annotations
from decimal import Decimal

def confirmed_pivots(candles, p: int):
    highs: list[tuple[int, Decimal]] = []
    lows: list[tuple[int, Decimal]] = []
    for i in range(p, len(candles) - p):
        window = candles[i - p : i + p + 1]
        hi = candles[i].high
        lo = candles[i].low
        if hi == max(item.high for item in window) and sum(item.high == hi for item in window) == 1:
            highs.append((i, hi))
        if lo == min(item.low for item in window) and sum(item.low == lo for item in window) == 1:
            lows.append((i, lo))
    return highs, lows
