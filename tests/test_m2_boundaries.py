from dataclasses import replace
import json

import numpy as np
import pandas as pd
import pytest

from goldai.market import Timeframe
from goldai.strategies import balanced_kernel as bk
from goldai.strategies import migrated
from goldai.strategies.ema_kernel import _invalidated, VideoSourceConfig
from goldai.strategies.models import Direction, EntryIntent, StrategyState
from goldai.strategies.supply_kernel import SupplyDemandSignalEngine, SupplyDemandParams, Zone
from goldai.strategies.supply_types import Bar
from goldai.indicators.balanced import prepare_features
from test_m2_migration import market, ema_rows


@pytest.mark.parametrize('component,direction',[('poc',1),('pdl',-1)])
def test_balanced_independent_ready_geometry_quality_and_dedup(component,direction,monkeypatch):
    rng=np.random.default_rng(0)
    cl=2600+np.cumsum(rng.normal(0,2,800)); op=np.r_[cl[0],cl[:-1]]
    high=np.maximum(op,cl)+rng.uniform(.01,1,800)
    low=np.minimum(op,cl)-rng.uniform(.01,1,800)
    rows=list(zip(op,high,low,cl))
    state=market(rows,Timeframe.M5)
    frame=pd.DataFrame([{'time':b.opened_at,'open':b.open,'high':b.high,'low':b.low,
        'close':b.close,'tick_volume':b.tick_count} for b in state.history[Timeframe.M5]])
    fixture=prepare_features(frame)
    fixture['atr_percentile288']=.9
    for prefix in ('h1','entry_h4'):
        fixture[prefix+'_close']=2600+100*direction
        fixture[prefix+'_ema50']=2600+50*direction
        fixture[prefix+'_ema200']=2600
    fixture['entry_h4_plus_di14']=30
    fixture['entry_h4_minus_di14']=10
    fixture['h4_adx14']=20.0
    fixture['entry_prev_day_high']=frame.high.rolling(36,min_periods=1).max().shift(1)
    fixture['entry_prev_day_low']=frame.low.rolling(36,min_periods=1).min().shift(1)
    if component=='poc':
        signals=bk.generate_volume_profile_retests(fixture,0,lookback=72,target_level='poc',
            min_atr_percentile=.8,breakout_buffer_atr=.05,retest_tolerance_atr=.2,
            retest_bars=12,stop_buffer_atr=.2,long_only=True)
    else:
        signals=bk.generate_pdh_pdl_retest_v2(fixture,0,min_atr_percentile=.7,
            breakout_buffer_atr=.2,retest_tolerance_atr=.1,retest_bars=6,
            stop_buffer_atr=.2,min_body_atr=.2,allow_long=False,allow_short=True)
    assert signals
    signal=signals[-1]
    cut=signal.signal_index+1
    state=market(rows[:cut],Timeframe.M5)
    # Deliberately controlled feature snapshot tests wrapper behavior separately
    # from the full original-feature parity script and causal feature fixtures.
    monkeypatch.setattr(migrated,'prepare_features',lambda _:fixture.iloc[:cut])
    engine=migrated.BalancedComponent(component)
    decision=engine.evaluate(state)
    assert decision.state is StrategyState.READY
    assert decision.stop==signal.stop
    assert decision.direction is (Direction.LONG if direction>0 else Direction.SHORT)
    assert decision.entry_intent.reward_r==3
    assert decision.entry_intent.semantics=='NEXT_BAR_EXECUTABLE_QUOTE'
    assert decision.timestamp==state.timestamp
    assert engine.evaluate(state).state is StrategyState.COOLDOWN
    fixture.loc[cut-1,'entry_h4_plus_di14']=-100
    fixture.loc[cut-1,'h4_adx14']=17.999
    assert migrated.BalancedComponent(component).evaluate(state).invalidation=='H4_QUALITY_REJECTED'


def test_ema_touch_equality_and_recurrence_rule():
    row=pd.Series({'bid_close':101.,'bid_low':100.,'bid_high':102.,'ema50':100.})
    assert not _invalidated(row,'long','touch')
    row['bid_low']=99.999
    assert _invalidated(row,'long','touch')
    row['bid_high']=100.; row['bid_close']=99.
    assert not _invalidated(row,'short','touch')
    row['bid_high']=100.001
    assert _invalidated(row,'short','touch')


def b(i,o=100,h=101,l=99,c=100):
    return Bar(str(i),str(i),str(i+1),o,h,l,c,10)


@pytest.mark.parametrize('age,expired',[(24,False),(25,True)])
def test_supply_zone_age_boundary(age,expired):
    e=SupplyDemandSignalEngine(timeframe='M15',params=SupplyDemandParams())
    z=Zone('DEMAND',0,'0',100,98,1,1,2,2,False)
    e.active_zones=[z]
    e.bars=[b(i) for i in range(age+1)]
    assert e._manage_zones(age,b(age,102,103,101,102)) is None
    assert (z not in e.active_zones)==expired


@pytest.mark.parametrize('age,ready',[(3,True),(4,False)])
@pytest.mark.parametrize('short',[False,True])
def test_supply_confirmation_deadline_and_consumption(age,ready,short):
    e=SupplyDemandSignalEngine(timeframe='M15',params=SupplyDemandParams())
    z=Zone('SUPPLY' if short else 'DEMAND',0,'0',100,102 if short else 98,
           1,1,2,2,False,retest_index=1,retest_time='1')
    e.active_zones=[z]
    e.bars=[b(i) for i in range(age+2)]
    bar=b(age+1,100,101,97,98) if short else b(age+1,100,103,99,102)
    signal=e._manage_zones(age+1,bar)
    assert (signal is not None)==ready
    assert not e.active_zones
    assert e._manage_zones(age+1,bar) is None


def test_supply_compact_base_longest_suffix_and_exceptional_path():
    e=SupplyDemandSignalEngine(timeframe='M15',params=SupplyDemandParams())
    e.bars=[b(i,100,100.25,99.75,100) for i in range(20)]
    assert e._base_suffix(before_index=19,atr=1)==(16,19)
    e=SupplyDemandSignalEngine(timeframe='M15',params=SupplyDemandParams())
    for i in range(20): e.on_bar(b(i,100,100.45,99.55,100.02))
    e.on_bar(b(20,100,100.25,99.75,100))
    e.on_bar(b(21,100,102.30,99.95,102.15))
    assert e.exceptional_zones==1
    assert e.retests==0
    zone=e.active_zones[0]
    assert zone.distal==99.75
    e.on_bar(b(22,102.15,102.2,99.5,99.6))
    assert e.broken==1


@pytest.mark.parametrize('kwargs',[
    {'semantics':'BAD','reward_r':2},
    {'semantics':'FIRST_QUOTE_AT_OR_AFTER_CLOSE','reward_r':float('nan')},
    {'semantics':'FIRST_QUOTE_AT_OR_AFTER_CLOSE'},
])
def test_invalid_intent(kwargs):
    with pytest.raises(ValueError): EntryIntent(**kwargs)


def test_reset_restore_and_input_guards():
    engine=migrated.EmaM15Touch()
    state=market(ema_rows())
    engine.evaluate(state)
    assert engine.snapshot()==json.loads(json.dumps(engine.snapshot()))
    bad=engine.snapshot(); bad['strategy_id']='different'
    with pytest.raises(ValueError): engine.restore(bad)
    bad=engine.snapshot(); bad['last_timestamp']='2026-01-01'
    with pytest.raises(ValueError): engine.restore(bad)
    with pytest.raises(ValueError): migrated.SupplyDemandM15(4)
    with pytest.raises(ValueError): migrated.BalancedComponent('orb')
    bars=state.history[Timeframe.M15]
    with pytest.raises(ValueError,match='duration'):
        migrated.EmaM15Touch().evaluate(replace(state,history={Timeframe.M15:(replace(bars[-1],opened_at=bars[-2].opened_at),)}))
