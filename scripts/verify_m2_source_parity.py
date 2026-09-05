"""Compare recovered source detectors against M2 on deterministic fixtures.

Run with --sources pointing at the four extracted original releases described
in docs/STRATEGY_MIGRATION_M2.md. No source broker or simulator is imported.
Only the named pure definitions are loaded through AST selection.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Literal

import numpy as np
import pandas as pd

from goldai.indicators import ema_chandelier, balanced
from goldai.strategies import ema_kernel, supply_kernel, supply_types, balanced_kernel


def definitions(path, names, module_name, extra=None):
    source=Path(path).read_text()
    tree=ast.parse(source)
    nodes=[]
    for node in tree.body:
        if isinstance(node,(ast.ClassDef,ast.FunctionDef)) and node.name in names:
            nodes.append(node)
    assert len(nodes)==len(names), (path,names)
    module=ModuleType(module_name)
    sys.modules[module_name]=module
    module.__dict__.update({'np':np,'pd':pd,'math':math,'dataclass':dataclass,'asdict':asdict,
        'Enum':Enum,'Decimal':Decimal,'Literal':Literal,'Direction':Literal['LONG','SHORT'],
        'Regime':Literal['BULL','BEAR','NEUTRAL'],'ZoneDirection':Literal['DEMAND','SUPPLY']})
    module.__dict__.update(extra or {})
    future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
    selected=ast.fix_missing_locations(ast.Module(body=[future]+nodes,type_ignores=[]))
    exec(compile(selected,str(path),'exec'),module.__dict__)
    return module


def run(sources: Path):
    ema_root=sources/'ema-original/Skydev_Gold_M15_Operator_v1.0.0'
    supply_root=sources/'supply-original/src/skydev_v2/research'
    bal_root=sources/'balanced-original/gold_ai_mt5_python_v1.2.0/src/gold_ai'
    ei=definitions(ema_root/'indicators.py',{'ema','true_range','wilder_atr','chandelier_stop','add_indicators'},'oracle_ema_ind')
    ed=definitions(ema_root/'video_source_v1.py',{'SetupState','SetupReason','VideoSourceConfig','Setup',
        'DetectionResult','_indicator_bars','_invalidated','detect_setups'},'oracle_ema',{'add_indicators':ei.add_indicators})
    st=definitions(supply_root/'structural_pullback_v1.py',{'Bar','Signal'},'oracle_supply_types')
    sd=definitions(supply_root/'supply_demand_v1.py',{'SupplyDemandParams','Zone','SupplyDemandSignalEngine'},
                   'oracle_supply',{'Bar':st.Bar,'Signal':st.Signal})
    bi=definitions(bal_root/'indicators.py',{'ema','rsi','true_range','atr','adx_components',
        '_resampled_context','_add_daily_context','add_indicators'},'oracle_bal_ind')
    nr=definitions(bal_root/'dataset.py',{'normalize_rates'},'oracle_normalize')
    bf=definitions(bal_root/'entry_lab.py',{'EntrySignal','_htf_frame','prepare_entry_frame'},
        'oracle_bal_features',{**bi.__dict__,'normalize_rates':nr.normalize_rates})
    bd=definitions(bal_root/'epic_strategies.py',{'VolumeProfile','_sig','_profile_arrays','_bias_arrays',
        'generate_volume_profile_retests','generate_pdh_pdl_retest_v2'},'oracle_bal',{'EntrySignal':bf.EntrySignal})
    report={'classification':'SYNTHETIC_SOURCE_PARITY_ONLY','historical_replay':False,
            'seeds':list(range(8)), 'ema':0,'supply':0,'poc':0,'pdl':0,'feature_prefixes':0}
    from goldai.market import MarketBar, MarketState, MarketSession, Timeframe
    from goldai.strategies.migrated import StructuralBreakH1
    from goldai.strategies.models import StrategyState, Direction as CanonicalDirection
    from datetime import UTC, datetime, timedelta
    class ReferenceBase:
        def __init__(self, **kwargs): pass
        def _none(self, *args): return None
        def _signal(self, **kwargs): return kwargs
    structural=definitions(sources/'structural-original/skydev_v2/strategies/product.py',
        {'GoldStructuralBreakParams','_confirmed_pivots','XauusdStructuralBreakTrendV1'},
        'oracle_structural',{'_ProductStrategyBase':ReferenceBase,
                            'Direction':SimpleNamespace(BUY=CanonicalDirection.LONG,SELL=CanonicalDirection.SHORT)})
    report['structural_prefixes']=0
    report['structural_ready']=0
    for short in (False,True):
        prices=[100]*35
        prices[5]=110; prices[11]=90; prices[18]=115; prices[25]=95
        rows=[(p,p+1,p-1,p) for p in prices]+[(100,118,99,117)]
        if short: rows=[(220-o,220-l,220-h,220-c) for o,h,l,c in rows]
        start=datetime(2026,1,5,tzinfo=UTC)
        bars=tuple(MarketBar('XAUUSD',Timeframe.H1,start+timedelta(hours=i),start+timedelta(hours=i+1),*row)
                   for i,row in enumerate(rows))
        original=structural.XauusdStructuralBreakTrendV1(configuration_hash='fixture',configuration_json='{}')
        for cut in range(1,len(bars)+1):
            part=bars[:cut]
            snapshot=SimpleNamespace(symbol='XAUUSD',h1=tuple(SimpleNamespace(
                high=Decimal(str(b.high)),low=Decimal(str(b.low)),close=Decimal(str(b.close)),
                close_time=b.closed_at) for b in part),timestamp=part[-1].closed_at,
                latest_bid=Decimal('117'),latest_ask=Decimal('117.2'))
            expected=original.evaluate(snapshot,None)
            actual=StructuralBreakH1().evaluate(MarketState('XAUUSD',part[-1].closed_at,
                MarketSession.LONDON,stale=False,history={Timeframe.H1:part}))
            assert (expected is not None)==(actual.state is StrategyState.READY)
            if expected:
                assert expected['direction']==actual.direction
                assert float(expected['features']['stop_distance_usd'])==actual.entry_intent.stop_distance
                assert float(expected['features']['target_distance_usd'])==actual.entry_intent.target_distance
                assert expected['features']['max_hold_minutes']==actual.entry_intent.max_hold_minutes
                report['structural_ready']+=1
            report['structural_prefixes']+=1
    for seed in report['seeds']:
        rng=np.random.default_rng(seed)
        n=800
        cl=2600+np.cumsum(rng.normal(0,2,n))
        op=np.r_[cl[0],cl[:-1]]
        frame=pd.DataFrame({'time':pd.date_range('2026-01-05',periods=n,freq='5min',tz='UTC'),
            'open':op,'high':np.maximum(op,cl)+rng.uniform(0.01,1,n),
            'low':np.minimum(op,cl)-rng.uniform(0.01,1,n),'close':cl,'tick_volume':rng.integers(1,100,n)})
        ef=frame.set_index('time').rename(columns={k:'bid_'+k for k in ['open','high','low','close']})
        old=ed.detect_setups(ef,ed.VideoSourceConfig(ema_invalidation_mode='touch'))
        new=ema_kernel.detect_setups(ef,ema_kernel.VideoSourceConfig(ema_invalidation_mode='touch'))
        pd.testing.assert_frame_equal(old.bars,new.bars,check_exact=True)
        pd.testing.assert_frame_equal(pd.DataFrame([x.as_record() for x in old.audits]),
                                      pd.DataFrame([x.as_record() for x in new.audits]), check_exact=True)
        report['ema']+=int((old.bars.signal!='').sum())
        old_sd=sd.SupplyDemandSignalEngine(timeframe='M15',params=sd.SupplyDemandParams())
        new_sd=supply_kernel.SupplyDemandSignalEngine(timeframe='M15',params=supply_kernel.SupplyDemandParams())
        for i,row in frame.iterrows():
            values=(str(i),str(row.time),str(row.time+pd.Timedelta(minutes=15)),row.open,row.high,row.low,row.close,int(row.tick_volume))
            a,b=old_sd.on_bar(st.Bar(*values)),new_sd.on_bar(supply_types.Bar(*values))
            assert (asdict(a) if a else None)==(asdict(b) if b else None)
            assert [asdict(z) for z in old_sd.active_zones]==[asdict(z) for z in new_sd.active_zones]
        report['supply']+=len(old_sd.signals)
        old_features=bf.prepare_entry_frame(frame)
        new_features=balanced.prepare_features(frame)
        for name in set(old_features.columns)&set(new_features.columns):
            pd.testing.assert_series_equal(old_features[name],new_features[name],check_exact=True)
        for cut in (301,600):
            pd.testing.assert_frame_equal(new_features.iloc[:cut],balanced.prepare_features(frame.iloc[:cut]),check_exact=True)
            report['feature_prefixes']+=1
        # Controlled HTF fixtures isolate the recovered entry kernels from long
        # EMA200 warm-up; these are not claimed as historical market inputs.
        for direction in (1,-1):
            fixture=new_features.copy()
            fixture['atr_percentile288']=0.9
            for prefix in ('h1','entry_h4'):
                fixture[prefix+'_close']=2600+direction*100
                fixture[prefix+'_ema50']=2600+direction*50
                fixture[prefix+'_ema200']=2600
            fixture['entry_prev_day_high']=frame.high.rolling(36,min_periods=1).max().shift(1)
            fixture['entry_prev_day_low']=frame.low.rolling(36,min_periods=1).min().shift(1)
            for name,old_fn,new_fn,kwargs in [
                ('poc',bd.generate_volume_profile_retests,balanced_kernel.generate_volume_profile_retests,
                 dict(lookback=72,target_level='poc',min_atr_percentile=.80,breakout_buffer_atr=.05,
                      retest_tolerance_atr=.20,retest_bars=12,stop_buffer_atr=.20,long_only=True)),
                ('pdl',bd.generate_pdh_pdl_retest_v2,balanced_kernel.generate_pdh_pdl_retest_v2,
                 dict(min_atr_percentile=.70,breakout_buffer_atr=.20,retest_tolerance_atr=.10,
                      retest_bars=6,stop_buffer_atr=.20,min_body_atr=.20,allow_long=False,allow_short=True))]:
                expected=old_fn(fixture,96,**kwargs)
                actual=[s for s in new_fn(fixture,0,**kwargs) if s.signal_index<len(fixture)-98]
                assert [asdict(s) for s in expected]==[asdict(s) for s in actual]
                report[name]+=len(expected)
    assert all(report[name]>0 for name in ('ema','supply','poc','pdl')),report
    report['status']='PASS'
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().sources),indent=2))
