"""Canonical wrappers around recovered detection rules. No fills or I/O.

Batch-prefix evaluation deliberately preserves original warm-up and setup
history. Supply/demand state is reconstructed from the same immutable prefix;
EMA audits at the end of a prefix are not treated as real-time invalidations.
"""
from __future__ import annotations

from datetime import datetime
import hashlib

import numpy as np
import pandas as pd

from goldai.indicators.balanced import prepare_features
from goldai.indicators.pivots import confirmed_pivots
from goldai.market import BarStatus, MarketState, Timeframe
from goldai.strategies.base import DeterministicStrategy
from goldai.strategies.models import Direction, EntryIntent, StrategyDecision, StrategyState
from goldai.strategies.ema_kernel import VideoSourceConfig, detect_setups
from goldai.strategies.supply_kernel import SupplyDemandSignalEngine, SupplyDemandParams
from goldai.strategies.supply_types import Bar
from goldai.strategies.balanced_kernel import generate_volume_profile_retests, generate_pdh_pdl_retest_v2


class MigratedStrategy(DeterministicStrategy):
    version = '1.0.0'
    strategy_id = ''
    timeframe = Timeframe.M15

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._emitted: set[str] = set()
        self._last_timestamp: datetime | None = None
        self._history_count = 0
        self._history_hash = hashlib.sha256(b'').hexdigest()

    def snapshot(self) -> dict:
        return {'strategy_id': self.strategy_id, 'version': self.version,
                'last_timestamp': self._last_timestamp.isoformat() if self._last_timestamp else None,
                'history_count':self._history_count, 'history_hash':self._history_hash,
                'emitted': sorted(self._emitted)}

    def restore(self, state: dict) -> None:
        if state.get('strategy_id') != self.strategy_id or state.get('version') != self.version:
            raise ValueError('state identity mismatch')
        timestamp = datetime.fromisoformat(state['last_timestamp']) if state.get('last_timestamp') else None
        if timestamp is not None and (timestamp.tzinfo is None or timestamp.utcoffset() is None):
            raise ValueError('state timestamp must be aware')
        emitted = state.get('emitted', [])
        if not isinstance(emitted, list) or any(not isinstance(x, str) or len(x) != 64 for x in emitted):
            raise ValueError('invalid emitted signal identities')
        history_count = int(state['history_count'])
        history_hash = state['history_hash']
        if history_count<0 or not isinstance(history_hash,str) or len(history_hash)!=64:
            raise ValueError('invalid history checkpoint')
        self._last_timestamp, self._emitted = timestamp, set(emitted)
        self._history_count, self._history_hash = history_count, history_hash

    def _decision(self, market, state=StrategyState.IDLE, reason='NO_SETUP', **values):
        return StrategyDecision(self.strategy_id, self.version, market.symbol, self.timeframe,
                                market.timestamp, state, reason=reason, **values)

    def evaluate(self, market: MarketState) -> StrategyDecision:
        if market.symbol != 'XAUUSD':
            return self._decision(market, reason='SYMBOL_NOT_SUPPORTED')
        if self._last_timestamp is not None and market.timestamp < self._last_timestamp:
            raise ValueError('evaluation timestamps must be monotonic; reset for a new replay')
        bars = tuple(market.history.get(self.timeframe, ()))
        for tf, history in market.history.items():
            previous = None
            for bar in history:
                if bar.symbol != market.symbol or bar.timeframe != tf:
                    raise ValueError('history symbol/timeframe mismatch')
                if bar.status is not BarStatus.COMPLETE or bar.closed_at > market.timestamp:
                    raise ValueError('only completed causal bars are allowed')
                if (bar.closed_at-bar.opened_at).total_seconds() != tf.seconds:
                    raise ValueError('bar duration does not match timeframe')
                if previous is not None and bar.opened_at < previous:
                    raise ValueError('history must be ordered without overlapping bars')
                previous = bar.closed_at
        if not bars:
            return self._decision(market, StrategyState.WAITING, 'HISTORY_REQUIRED')
        if market.stale or bars[-1].closed_at != market.timestamp:
            return self._decision(market, StrategyState.WAITING, 'WAIT_FRESH_DECISION_CLOSE')
        digest = hashlib.sha256()
        if len(bars)<self._history_count:
            raise ValueError('history prefix was removed; reset required')
        for i,bar in enumerate(bars):
            digest.update(bar.to_json().encode())
            if i+1==self._history_count and digest.hexdigest()!=self._history_hash:
                raise ValueError('history prefix was revised; reset required')
        result = self._detect(market, bars)
        self._history_count, self._history_hash = len(bars), digest.hexdigest()
        self._last_timestamp = market.timestamp
        if result.state is StrategyState.READY:
            identity = result.signal_id
            if identity in self._emitted:
                return self._decision(market, StrategyState.COOLDOWN, 'DUPLICATE_SETUP',
                                      metadata={'suppressed_signal_id': identity})
            self._emitted.add(identity)
        return result


class EmaM15Touch(MigratedStrategy):
    strategy_id = 'ema50_chandelier_m15_touch'

    def _detect(self, market, bars):
        frame = pd.DataFrame([{'bid_open': b.open, 'bid_high': b.high, 'bid_low': b.low,
                               'bid_close': b.close} for b in bars],
                             index=pd.DatetimeIndex([b.opened_at for b in bars]))
        result = detect_setups(frame, VideoSourceConfig(ema_invalidation_mode='touch'))
        row = result.bars.iloc[-1]
        if row['signal'] in ('long', 'short'):
            setup = next(a for a in result.audits if a.setup_id == row['setup_id'])
            return self._decision(market, StrategyState.READY, 'STRUCTURE_CLOSE_CONFIRMED',
                direction=Direction.LONG if row['signal']=='long' else Direction.SHORT,
                stop=float(row.stop_loss), risk_reward=2.0,
                setup_timestamp=setup.ema_break_time.to_pydatetime(),
                entry_intent=EntryIntent('FIRST_QUOTE_AT_OR_AFTER_CLOSE', reward_r=2.0),
                metadata={'structure': setup.structure_price, 'bid_signal_close': float(row.bid_close)})
        event = str(row['event'])
        if any(x in event for x in ('EMA_RECROSS', 'OVERSIZED_STRUCTURE_BREAKOUT', 'INVALID_CHANDELIER_STOP')):
            return self._decision(market, StrategyState.INVALIDATED, event, invalidation=event)
        if len(bars) < 22:
            return self._decision(market, StrategyState.WAITING, 'INDICATOR_WARMUP')
        if result.audits:
            last = result.audits[-1]
            if last.reason.value in ('STALE_SETUP', 'INSUFFICIENT_PULLBACK'):
                return self._decision(market, StrategyState.WAITING if last.structure_price else StrategyState.FORMING,
                                      event or 'SETUP_IN_PROGRESS')
        return self._decision(market, reason=event or 'NO_SETUP')


class StructuralBreakH1(MigratedStrategy):
    strategy_id = 'xauusd_structural_break_trend_v1'
    timeframe = Timeframe.H1

    def _detect(self, market, bars):
        if len(bars) < 16:
            return self._decision(market, StrategyState.WAITING, 'XAU_STRUCTURAL_BREAK_HISTORY_INSUFFICIENT')
        highs, lows = confirmed_pivots(bars, 4)
        if len(highs)<2 or len(lows)<2:
            return self._decision(market, StrategyState.FORMING, 'INSUFFICIENT_CONFIRMED_STRUCTURE')
        previous_hi, hi = highs[-2][1], highs[-1][1]
        previous_lo, lo = lows[-2][1], lows[-1][1]
        previous_close, close = bars[-2].close, bars[-1].close
        direction = Direction.NONE
        if hi>previous_hi and lo>previous_lo and previous_close<=hi and close>hi:
            direction = Direction.LONG
        elif hi<previous_hi and lo<previous_lo and previous_close>=lo and close<lo:
            direction = Direction.SHORT
        if direction is Direction.NONE:
            return self._decision(market, reason='NO_QUALIFYING_GOLD_STRUCTURAL_BREAK')
        return self._decision(market, StrategyState.READY, 'CONFIRMED_STRUCTURE_CLOSE_BREAK',
            direction=direction, setup_timestamp=bars[-1].closed_at, risk_reward=20/3,
            entry_intent=EntryIntent('FIRST_QUOTE_AT_OR_AFTER_CLOSE', stop_distance=3,
                                     target_distance=20, max_hold_minutes=1440),
            metadata={'last_swing_high':hi, 'last_swing_low':lo,
                      'product_position_limit_reference':1})


class SupplyDemandM15(MigratedStrategy):
    strategy_id = 'm15_supply_demand'

    def __init__(self, reward_r: int = 3):
        if reward_r not in (2,3):
            raise ValueError('only separate frozen 2R and 3R variants are supported')
        self.reward_r = reward_r
        if reward_r == 2:
            self.strategy_id = 'm15_supply_demand_2r'
        super().__init__()

    def _detect(self, market, bars):
        engine = SupplyDemandSignalEngine(timeframe='M15', params=SupplyDemandParams())
        signal = None
        for b in bars:
            signal = engine.on_bar(Bar(b.opened_at.isoformat(), b.opened_at.isoformat(),
                                      b.closed_at.isoformat(), b.open, b.high, b.low, b.close, b.tick_count))
        if signal:
            return self._decision(market, StrategyState.READY, 'FRESH_ZONE_CONFIRMATION',
                direction=Direction(signal.direction), stop=signal.stop_level,
                risk_reward=float(self.reward_r), setup_timestamp=datetime.fromisoformat(signal.breakout_time),
                entry_intent=EntryIntent('FIRST_QUOTE_AT_OR_AFTER_CLOSE', reward_r=self.reward_r),
                metadata={'zone_proximal':signal.breakout_level,'research_status':'RESEARCH_ONLY_NOT_ACCEPTED'})
        if len(bars)<14:
            return self._decision(market, StrategyState.WAITING, 'INDICATOR_WARMUP')
        return self._decision(market, StrategyState.WAITING if engine.active_zones else StrategyState.IDLE,
                              'WAIT_ZONE_RETEST_OR_CONFIRMATION' if engine.active_zones else 'NO_SETUP')


class BalancedComponent(MigratedStrategy):
    timeframe = Timeframe.M5
    strategy_id = 'poc_continuation_retest_long'

    def __init__(self, component: str = 'poc'):
        if component not in ('poc','pdl'):
            raise ValueError('unknown Balanced component')
        self.component = component
        if component == 'pdl':
            self.strategy_id = 'pdh_pdl_breakout_retest'
        super().__init__()

    def _detect(self, market, bars):
        if len(bars)<301:
            return self._decision(market, StrategyState.WAITING, 'INDICATOR_WARMUP')
        frame = prepare_features(pd.DataFrame([{'time':b.opened_at, 'open':b.open,'high':b.high,
            'low':b.low,'close':b.close,'tick_volume':b.tick_count} for b in bars]))
        if self.component == 'poc':
            signals = generate_volume_profile_retests(frame, 0, lookback=72,target_level='poc',
                min_atr_percentile=0.80,breakout_buffer_atr=0.05,retest_tolerance_atr=0.20,
                retest_bars=12,stop_buffer_atr=0.20,long_only=True)
        else:
            signals = generate_pdh_pdl_retest_v2(frame,0,min_atr_percentile=0.70,
                breakout_buffer_atr=0.20,retest_tolerance_atr=0.10,retest_bars=6,
                stop_buffer_atr=0.20,min_body_atr=0.20,allow_long=False,allow_short=True)
        latest = next((s for s in reversed(signals) if s.signal_index==len(bars)-1),None)
        if latest is None:
            return self._decision(market, reason='NO_QUALIFYING_COMPONENT_SETUP')
        row = frame.iloc[-1]
        quality = row.entry_h4_plus_di14-row.entry_h4_minus_di14 if self.component=='poc' else row.h4_adx14
        if not np.isfinite(quality) or quality < (0 if self.component=='poc' else 18):
            return self._decision(market, StrategyState.INVALIDATED, 'H4_QUALITY_REJECTED', invalidation='H4_QUALITY_REJECTED')
        return self._decision(market, StrategyState.READY, 'INDEPENDENT_BALANCED_COMPONENT',
            direction=Direction.LONG if latest.direction==1 else Direction.SHORT,
            stop=latest.stop, risk_reward=3.0, setup_timestamp=bars[-1].closed_at,
            entry_intent=EntryIntent('NEXT_BAR_EXECUTABLE_QUOTE', reward_r=3.0),
            metadata={'level':latest.level, 'component':self.component})


def build_strategy(strategy_id: str) -> MigratedStrategy:
    constructors = {'ema50_chandelier_m15_touch': EmaM15Touch,
        'xauusd_structural_break_trend_v1': StructuralBreakH1,
        'h1_structural_break_trend': StructuralBreakH1,
        'm15_supply_demand': SupplyDemandM15,
        'm15_supply_demand_2r': lambda: SupplyDemandM15(2),
        'poc_continuation_retest_long': BalancedComponent,
        'pdh_pdl_breakout_retest': lambda: BalancedComponent('pdl')}
    if strategy_id not in constructors:
        raise ValueError('strategy is disabled or not implemented')
    return constructors[strategy_id]()
