from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

from goldai.strategies.supply_types import Bar, Signal

ZoneDirection = Literal["DEMAND", "SUPPLY"]


@dataclass(frozen=True, slots=True)
class SupplyDemandParams:
    """Frozen, intentionally simple first supply/demand hypothesis for XAUUSD.

    The defaults operationalize the beginner rule discussed with the user:
    a compact base, followed by at least two strong candles moving away, with
    one exceptional-displacement candle accepted as the explicit exception.
    Parameters are frozen before historical result inspection in this run.
    """

    atr_period: int = 14
    max_base_bars: int = 4
    base_candle_max_atr: float = 0.90
    base_total_max_atr: float = 1.25
    strong_body_fraction: float = 0.60
    strong_range_min_atr: float = 0.90
    minimum_strong_candles: int = 2
    combined_displacement_min_atr: float = 1.50
    exceptional_body_fraction: float = 0.70
    exceptional_range_min_atr: float = 1.80
    exceptional_close_beyond_zone_atr: float = 1.00
    retest_expiry_bars: int = 24
    max_confirmation_bars: int = 3

    def __post_init__(self) -> None:
        if self.atr_period < 2:
            raise ValueError("ATR_PERIOD_TOO_SMALL")
        if not 1 <= self.max_base_bars <= 8:
            raise ValueError("BASE_BAR_LIMIT_INVALID")
        if self.minimum_strong_candles != 2:
            raise ValueError("FIRST_BASELINE_MINIMUM_STRONG_CANDLES_FROZEN_AT_2")
        if self.retest_expiry_bars < 1 or self.max_confirmation_bars < 1:
            raise ValueError("EXPIRY_INVALID")


@dataclass(slots=True)
class Zone:
    direction: ZoneDirection
    created_index: int
    created_time: str
    proximal: float
    distal: float
    atr_at_creation: float
    base_bars: int
    displacement_candles: int
    displacement_strength_atr: float
    exceptional_displacement: bool
    retest_index: int | None = None
    retest_time: str | None = None
    retest_extreme: float | None = None

    @property
    def lower(self) -> float:
        return min(self.proximal, self.distal)

    @property
    def upper(self) -> float:
        return max(self.proximal, self.distal)


class SupplyDemandSignalEngine:
    def __init__(self, *, timeframe: str, params: SupplyDemandParams) -> None:
        self.timeframe = timeframe
        self.params = params
        self.bars: list[Bar] = []
        self.true_ranges: list[float] = []
        self.atr_values: list[float] = []
        self.active_zones: list[Zone] = []
        self.signals: list[Signal] = []
        self.zones_created = 0
        self.demand_zones = 0
        self.supply_zones = 0
        self.exceptional_zones = 0
        self.retests = 0
        self.expired = 0
        self.broken = 0
        self.confirmation_expired = 0
        self.overlap_suppressed = 0

    def _prior_atr(self) -> float | None:
        if not self.atr_values:
            return None
        value = self.atr_values[-1]
        return value if math.isfinite(value) and value > 0 else None

    def _update_atr(self, bar: Bar) -> None:
        if not self.bars:
            tr = bar.high - bar.low
        else:
            prev_close = self.bars[-1].close
            tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
        self.true_ranges.append(tr)
        p = self.params.atr_period
        if len(self.true_ranges) < p:
            self.atr_values.append(float("nan"))
        elif len(self.true_ranges) == p:
            self.atr_values.append(sum(self.true_ranges[-p:]) / p)
        else:
            prior = self.atr_values[-1]
            self.atr_values.append(((prior * (p - 1)) + tr) / p)

    @staticmethod
    def _body_fraction(bar: Bar) -> float:
        total = bar.high - bar.low
        return 0.0 if total <= 0 else abs(bar.close - bar.open) / total

    def _strong(self, bar: Bar, *, direction: ZoneDirection, atr: float) -> bool:
        directional = bar.bullish if direction == "DEMAND" else bar.bearish
        return (
            directional
            and self._body_fraction(bar) >= self.params.strong_body_fraction
            and (bar.high - bar.low) >= self.params.strong_range_min_atr * atr
        )

    def _exceptional(self, bar: Bar, *, direction: ZoneDirection, atr: float) -> bool:
        directional = bar.bullish if direction == "DEMAND" else bar.bearish
        return (
            directional
            and self._body_fraction(bar) >= self.params.exceptional_body_fraction
            and (bar.high - bar.low) >= self.params.exceptional_range_min_atr * atr
        )

    def _base_suffix(self, *, before_index: int, atr: float) -> tuple[int, int] | None:
        # Longest causal suffix ending immediately before displacement.
        best: tuple[int, int] | None = None
        for count in range(1, self.params.max_base_bars + 1):
            start = before_index - count + 1
            if start < 0:
                break
            base = self.bars[start : before_index + 1]
            if any((x.high - x.low) > self.params.base_candle_max_atr * atr for x in base):
                continue
            total_range = max(x.high for x in base) - min(x.low for x in base)
            if total_range > self.params.base_total_max_atr * atr:
                continue
            best = (start, before_index)
        return best

    def _zone_overlaps(self, candidate: Zone) -> bool:
        for zone in self.active_zones:
            if zone.direction != candidate.direction:
                continue
            if max(zone.lower, candidate.lower) <= min(zone.upper, candidate.upper):
                return True
        return False

    def _try_create_zone(self, current_index: int) -> None:
        atr = self._prior_atr()
        if atr is None:
            return

        for direction in ("DEMAND", "SUPPLY"):
            exceptional = self._exceptional(self.bars[current_index], direction=direction, atr=atr)
            displacement_count = 1 if exceptional else 0
            first_disp = current_index
            if not exceptional:
                required = self.params.minimum_strong_candles
                first_disp = current_index - required + 1
                if first_disp < 0:
                    continue
                displacement = self.bars[first_disp : current_index + 1]
                if len(displacement) != required or not all(self._strong(x, direction=direction, atr=atr) for x in displacement):
                    continue
                displacement_count = required

            base_end = first_disp - 1
            suffix = self._base_suffix(before_index=base_end, atr=atr)
            if suffix is None:
                continue
            base_start, base_end = suffix
            base = self.bars[base_start : base_end + 1]
            zone_low = min(x.low for x in base)
            zone_high = max(x.high for x in base)
            last = self.bars[current_index]

            if direction == "DEMAND":
                beyond = last.close - zone_high
                if exceptional:
                    if beyond < self.params.exceptional_close_beyond_zone_atr * atr:
                        continue
                elif beyond < self.params.combined_displacement_min_atr * atr:
                    continue
                proximal, distal = zone_high, zone_low
                strength = beyond / atr
            else:
                beyond = zone_low - last.close
                if exceptional:
                    if beyond < self.params.exceptional_close_beyond_zone_atr * atr:
                        continue
                elif beyond < self.params.combined_displacement_min_atr * atr:
                    continue
                proximal, distal = zone_low, zone_high
                strength = beyond / atr

            candidate = Zone(
                direction=direction,
                created_index=current_index,
                created_time=last.close_time,
                proximal=proximal,
                distal=distal,
                atr_at_creation=atr,
                base_bars=len(base),
                displacement_candles=displacement_count,
                displacement_strength_atr=strength,
                exceptional_displacement=exceptional,
            )
            if self._zone_overlaps(candidate):
                self.overlap_suppressed += 1
                continue
            self.active_zones.append(candidate)
            self.zones_created += 1
            if direction == "DEMAND":
                self.demand_zones += 1
            else:
                self.supply_zones += 1
            if exceptional:
                self.exceptional_zones += 1

    def _manage_zones(self, current_index: int, bar: Bar) -> Signal | None:
        # Newest qualifying zone gets priority when multiple zones react on one bar.
        for zone in list(reversed(self.active_zones)):
            age = current_index - zone.created_index
            if age > self.params.retest_expiry_bars:
                self.active_zones.remove(zone)
                self.expired += 1
                continue

            if zone.direction == "DEMAND":
                if bar.close < zone.distal:
                    self.active_zones.remove(zone)
                    self.broken += 1
                    continue
            else:
                if bar.close > zone.distal:
                    self.active_zones.remove(zone)
                    self.broken += 1
                    continue

            if zone.retest_index is None:
                touched = bar.low <= zone.proximal if zone.direction == "DEMAND" else bar.high >= zone.proximal
                if not touched:
                    continue
                zone.retest_index = current_index
                zone.retest_time = bar.close_time
                zone.retest_extreme = bar.low if zone.direction == "DEMAND" else bar.high
                self.retests += 1
                continue

            confirm_age = current_index - zone.retest_index
            if confirm_age > self.params.max_confirmation_bars:
                self.active_zones.remove(zone)
                self.confirmation_expired += 1
                continue

            retest_bar = self.bars[zone.retest_index]
            if zone.direction == "DEMAND":
                confirmed = bar.bullish and bar.close > retest_bar.high
                stop_level = zone.distal
                direction = "LONG"
            else:
                confirmed = bar.bearish and bar.close < retest_bar.low
                stop_level = zone.distal
                direction = "SHORT"
            if not confirmed:
                continue

            signal = Signal(
                timeframe=self.timeframe,
                direction=direction,
                signal_time=bar.close_time,
                breakout_time=zone.created_time,
                breakout_level=zone.proximal,
                breakout_strength_atr=zone.displacement_strength_atr,
                stop_level=stop_level,
                pullback_candles=confirm_age,
                regime="NEUTRAL",
            )
            self.signals.append(signal)
            self.active_zones.remove(zone)
            return signal
        return None

    def on_bar(self, bar: Bar) -> Signal | None:
        current_index = len(self.bars)
        # Manage already-known zones first. A bar cannot create and retest the same zone.
        self._update_atr(bar)
        self.bars.append(bar)
        signal = self._manage_zones(current_index, bar)
        self._try_create_zone(current_index)
        return signal
