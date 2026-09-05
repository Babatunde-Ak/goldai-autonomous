from dataclasses import replace
from datetime import UTC, datetime, timedelta
import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from goldai.market import MarketBar, MarketState, MarketSession, Timeframe, BarStatus
from goldai.strategies.migrated import EmaM15Touch, StructuralBreakH1, SupplyDemandM15, BalancedComponent, build_strategy
from goldai.strategies.models import Direction, EntryIntent, StrategyDecision, StrategyState
from goldai.indicators.ema_chandelier import ema, wilder_atr, chandelier_stop
from goldai.indicators.pivots import confirmed_pivots
from goldai.indicators.balanced import prepare_features, adx_components
from goldai.strategies.registry import migration_registry
from goldai.cli.main import main

START = datetime(2026,1,5,tzinfo=UTC)


def market(rows, tf=Timeframe.M15):
    bars = tuple(MarketBar('XAUUSD',tf,START+timedelta(seconds=i*tf.seconds),
        START+timedelta(seconds=(i+1)*tf.seconds),*row,tick_count=10) for i,row in enumerate(rows))
    return MarketState('XAUUSD',bars[-1].closed_at,MarketSession.LONDON,stale=False,history={tf:bars})


def ema_rows(short=False):
    rows = [(99,100,98,99)]*25 + [(99,102,98.5,101),(101,103,100.5,102),
        (102,102.2,100.8,101.5),(101.5,101.7,100.6,101.2),
        (101.2,103.5,100.9,102.8),(102.8,103.6,102.4,103.2)]
    return [(200-o,200-l,200-h,200-c) for o,h,l,c in rows] if short else rows


def supply_rows(short=False):
    rows = [(100+(0.05 if i%2 else 0),100.45+(0.05 if i%2 else 0),
             99.55+(0.05 if i%2 else 0),100.02+(0.05 if i%2 else 0)) for i in range(20)]
    rows += [(100,100.30,99.70,100.05),(100.05,101.20,100,101.05),
             (101.05,102.30,101,102.10),(102.10,102.20,100.20,100.55),
             (100.55,102.35,100.40,102.25)]
    return [(200-o,200-l,200-h,200-c) for o,h,l,c in rows] if short else rows


def structural_rows(short=False):
    # Two unique highs and lows, second pair both higher, then a close cross.
    prices=[100]*35
    prices[5]=110; prices[11]=90; prices[18]=115; prices[25]=95
    rows=[(p,p+1,p-1,p) for p in prices]
    rows += [(100,118,99,117)]
    return [(220-o,220-l,220-h,220-c) for o,h,l,c in rows] if short else rows


@pytest.mark.parametrize('short',[False,True])
@pytest.mark.parametrize('kind',['ema','structural','supply2','supply3'])
def test_ready_and_unfilled_geometry(kind,short):
    if kind=='ema': engine, state = EmaM15Touch(),market(ema_rows(short))
    elif kind=='structural': engine,state = StructuralBreakH1(),market(structural_rows(short),Timeframe.H1)
    else: engine,state = SupplyDemandM15(2 if kind=='supply2' else 3),market(supply_rows(short))
    result=engine.evaluate(state)
    assert result.state is StrategyState.READY
    assert result.direction is (Direction.SHORT if short else Direction.LONG)
    assert result.entry is None and result.target is None
    assert result.entry_intent is not None and result.signal_id
    bid=state.history[engine.timeframe][-1].close
    entry,stop,target=result.entry_intent.preview(result.direction,bid,bid+0.2,result.stop)
    assert entry==pytest.approx(bid if short else bid+0.2)
    assert abs((target-entry)/(entry-stop))==pytest.approx(result.risk_reward)
    if kind=='structural':
        assert abs(stop-entry)==pytest.approx(3)
        assert abs(target-entry)==pytest.approx(20)
        assert result.entry_intent.max_hold_minutes==1440
    assert json.loads(result.to_json())['signal_id']==result.signal_id
    saved=engine.snapshot()
    clone=type(engine)(engine.reward_r) if isinstance(engine,SupplyDemandM15) else type(engine)()
    clone.restore(saved)
    assert clone.evaluate(state).state is StrategyState.COOLDOWN
    assert engine.evaluate(state).state is StrategyState.COOLDOWN
    engine.reset()
    assert engine.evaluate(state).signal_id==result.signal_id


@pytest.mark.parametrize('short',[False,True])
def test_ema_touch_and_insufficient_pullback(short):
    rows=ema_rows(short)
    o,h,l,c=rows[28]
    rows[28]=(o,105 if short else h,l if short else 95,c)
    assert EmaM15Touch().evaluate(market(rows[:29])).state is StrategyState.INVALIDATED
    rows=ema_rows(short)
    o,h,l,c=rows[28]
    rows[28]=(c,h,l,o)  # opposing sequence interrupted
    assert EmaM15Touch().evaluate(market(rows)).state is not StrategyState.READY


@pytest.mark.parametrize('short',[False,True])
def test_ema_oversized_confirmation(short):
    rows=ema_rows(short)
    o,h,l,c=rows[-1]
    rows[-1]=(o,h if short else 130,70 if short else l,c)
    result=EmaM15Touch().evaluate(market(rows))
    assert result.state is StrategyState.INVALIDATED
    assert 'OVERSIZED' in result.reason


@pytest.mark.parametrize('engine,tf',[(EmaM15Touch,Timeframe.M15),(StructuralBreakH1,Timeframe.H1),
    (SupplyDemandM15,Timeframe.M15),(BalancedComponent,Timeframe.M5)])
def test_causal_input_boundaries(engine,tf):
    state=market([(100,101,99,100)]*10,tf)
    assert engine().evaluate(state).state is not StrategyState.READY
    assert engine().evaluate(replace(state,stale=True)).state is StrategyState.WAITING
    assert engine().evaluate(replace(state,symbol='EURUSD')).state is StrategyState.IDLE
    assert engine().evaluate(replace(state,history={})).reason=='HISTORY_REQUIRED'
    with pytest.raises(ValueError,match='causal'):
        engine().evaluate(replace(state,timestamp=state.timestamp-timedelta(seconds=1)))
    bars=state.history[tf]
    with pytest.raises(ValueError,match='overlapping'):
        engine().evaluate(replace(state,history={tf:bars+(bars[-1],)}))
    with pytest.raises(ValueError,match='causal'):
        engine().evaluate(replace(state,history={tf:bars[:-1]+(replace(bars[-1],status=BarStatus.INCOMPLETE),)}))
    e=engine(); e.evaluate(state)
    with pytest.raises(ValueError,match='revised'):
        e.evaluate(replace(state,history={tf:(replace(bars[0],high=102),)+bars[1:]}))
    with pytest.raises(ValueError,match='monotonic'):
        e.evaluate(replace(state,timestamp=state.timestamp-timedelta(minutes=1)))


def test_pivots_confirm_after_four_right_bars_and_reject_ties():
    bars=market(structural_rows(),Timeframe.H1).history[Timeframe.H1]
    assert not confirmed_pivots(bars[:9],4)[0]
    assert confirmed_pivots(bars[:10],4)[0]==[(5,111)]
    tied=list(bars[:10]); tied[6]=replace(tied[6],high=111)
    assert not confirmed_pivots(tied,4)[0]
    assert confirmed_pivots(bars[:10],4)[0][0] in confirmed_pivots(bars,4)[0]


def test_indicator_seed_warmup_and_switches():
    close=pd.Series([100.0]*40)
    assert ema(close).iloc[0]==100
    a=wilder_atr(close+1,close-1,close)
    assert np.isnan(a.iloc[20]) and a.iloc[21]==2
    assert wilder_atr(close[:4]+1,close[:4]-1,close[:4]).isna().all()
    trend=pd.Series(np.r_[np.linspace(100,130,50),np.linspace(130,80,50),np.linspace(80,140,50)])
    stops=chandelier_stop(trend+1,trend-1,trend)
    assert {-1,1}.issubset(set(stops.chandelier_direction))
    pd.testing.assert_frame_equal(stops.iloc[:80],chandelier_stop(trend[:80]+1,trend[:80]-1,trend[:80]))


def test_balanced_features_are_causal_and_warmup_explicit():
    state=market([(100+i/100,101+i/100,99+i/100,100.1+i/100) for i in range(500)],Timeframe.M5)
    frame=pd.DataFrame([{'time':b.opened_at,'open':b.open,'high':b.high,'low':b.low,'close':b.close,
                         'tick_volume':b.tick_count} for b in state.history[Timeframe.M5]])
    all_features=prepare_features(frame)
    pd.testing.assert_frame_equal(all_features.iloc[:380],prepare_features(frame.iloc[:380]))
    assert all_features['entry_h4_ema200'].isna().all()
    assert all_features.atr_percentile288.iloc[:108].isna().all()
    assert BalancedComponent().evaluate(state).state is not StrategyState.READY
    assert BalancedComponent('pdl').evaluate(state).state is not StrategyState.READY


@pytest.mark.parametrize('bid,ask',[(0,1),(2,1),(float('nan'),3),(1,float('inf'))])
def test_intent_rejects_invalid_quotes(bid,ask):
    with pytest.raises(ValueError): EntryIntent('FIRST_QUOTE_AT_OR_AFTER_CLOSE',reward_r=2).preview(Direction.LONG,bid,ask,0.5)


def test_registry_cli_and_safety(capsys):
    records=migration_registry().all()
    assert all(r.execution_authorization.value=='NONE' for r in records)
    assert any(r.research_status=='REJECTED' for r in records)
    assert main(['strategies','describe','ema50_chandelier_m15_touch'])==0
    assert json.loads(capsys.readouterr().out)['execution_authorization']=='NONE'
    assert main(['strategies','describe','missing'])==2
    assert main(['strategies','validate'])==0
    for name in ['m5_supply_demand_rejected','liquidity_sweep_scalper','ny_orb_research','ml_meta_label_gate']:
        with pytest.raises(ValueError): build_strategy(name)
    root=Path(__file__).parents[1]/'src/goldai/strategies'
    for path in root.glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.Import): names=[a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom): names=[node.module or '']
            else: names=[]
            assert not any(any(x in name.lower() for x in ('metatrader','execution','mt5','broker')) for name in names)
            if isinstance(node,ast.Attribute):
                assert node.attr not in {'order_send','order_modify','position_close'}
