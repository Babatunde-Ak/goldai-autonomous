from dataclasses import replace, asdict
from datetime import UTC, datetime, timedelta
import json
import hashlib
import ast
from pathlib import Path

import pytest

from goldai.market import MarketTick, Timeframe
from goldai.strategies.models import StrategyDecision, StrategyState, Direction, EntryIntent
from goldai.replay import STRATEGIES
from goldai.replay.contracts import ReplayConfig, CostModel, fingerprint
from goldai.replay.engine import StrategyReplayRunner, FillSimulator
from goldai.replay.io import tick_fingerprint, save_result, inspect_result, compare_results, prepared_source
from goldai.replay.metrics import metrics, grouped_metrics, remove_top_trades
from goldai.cli.main import main
from goldai.data.prepare import prepare_histdata

T = datetime(2025,1,31,23,45,tzinfo=UTC)


def tick(seconds, bid=100, ask=101):
    return MarketTick("XAUUSD", T+timedelta(seconds=seconds), bid, ask, "fixture")


class Scripted:
    version = "fixture-v1"
    timeframe = Timeframe.M15

    def __init__(self, identity=STRATEGIES[0], short=False, reward=3, stop=None, hold=None, every=False):
        self.strategy_id, self.short, self.reward = identity, short, reward
        self.stop, self.hold, self.every = stop, hold, every
        self.reset()

    def reset(self):
        self.count = 0
        self.observed = []

    def snapshot(self):
        return {"count":self.count, "identity":self.strategy_id}

    def evaluate(self, market):
        self.count += 1
        bars = market.history[self.timeframe]
        assert market.timestamp == bars[-1].closed_at
        assert market.latest_tick.timestamp < market.timestamp
        assert all(b.closed_at <= market.timestamp for b in bars)
        self.observed.append((market.timestamp, market.latest_tick.bid, bars[-1].close))
        state = StrategyState.READY if self.count == 1 or self.every else StrategyState.IDLE
        intent = EntryIntent("NEXT_BAR_EXECUTABLE_QUOTE" if self.strategy_id in STRATEGIES[1:3]
                             else "FIRST_QUOTE_AT_OR_AFTER_CLOSE",
                             reward_r=self.reward, max_hold_minutes=self.hold)
        if self.strategy_id == STRATEGIES[3]:
            intent = EntryIntent("FIRST_QUOTE_AT_OR_AFTER_CLOSE",stop_distance=3,target_distance=20,max_hold_minutes=1440)
        return StrategyDecision(self.strategy_id,self.version,"XAUUSD",self.timeframe,market.timestamp,state,
            direction=Direction.SHORT if self.short else Direction.LONG,
            stop=self.stop if self.stop is not None else 102 if self.short else 99,
            entry_intent=intent,setup_timestamp=market.timestamp)


def run(ticks, strategy=None, **kwargs):
    strategy = strategy or Scripted()
    config = ReplayConfig(strategy.strategy_id,tick_fingerprint(ticks),"manifest-fixture","commit-fixture",**kwargs)
    runner = StrategyReplayRunner(config,strategy)
    return runner, runner.run(iter(ticks))


@pytest.mark.parametrize("short", [False,True])
@pytest.mark.parametrize("reward", [2,3])
@pytest.mark.parametrize("exit_reason", ["STOP","TARGET"])
def test_exact_r_sides_and_metrics(short,reward,exit_reason):
    # Entry risk is two, spread is included through Ask/Bid.
    exit_quote = (102 if short else 99) if exit_reason=="STOP" else (100-reward*2 if short else 101+reward*2)
    quotes = [tick(0),tick(899),tick(900)]
    quotes.append(tick(901,exit_quote-1,exit_quote) if short else tick(901,exit_quote,exit_quote+1))
    runner,(m,rows)=run(quotes,Scripted(short=short,reward=reward))
    r=rows[0]
    assert r["entry_price"] == (100 if short else 101)
    assert r["entry_side"] == ("BID" if short else "ASK")
    assert r["exit_side"] == ("ASK" if short else "BID")
    assert r["exit_reason"] == exit_reason
    assert r["realized_r"] == (reward if exit_reason=="TARGET" else -1)
    assert r["initial_risk"] == 2
    assert r["mae_r"] >= .5
    assert r["holding_seconds"] == 1
    assert m["tick_count_processed"] == 4
    assert m["bar_counts"] == {"M15":1}
    assert m["closed_trades"] == 1
    assert runner.strategy.observed[0][1:] == (100,100)


@pytest.mark.parametrize("short",[False,True])
def test_gaps_actual_stop_target_and_source_resting_target(short):
    for target in (False,True):
        q = (90 if short else 110) if target else (105 if short else 95)
        ticks=[tick(0),tick(900),tick(901,q-1,q) if short else tick(901,q,q+1)]
        _,(_,rows)=run(ticks,Scripted(short=short))
        assert rows[0]["exit_price"]==q
        assert rows[0]["slippage_to_level"] != 0
        _,(_,rows)=run(ticks,Scripted(STRATEGIES[4],short=short))
        assert rows[0]["exit_price"] == (rows[0]["target"] if target else q)


def test_zero_duration_wide_spread_and_equal_timestamp_order():
    _,(m,rows)=run([tick(0),tick(900,98,101)])
    assert rows[0]["state"]=="CLOSED_STOP"
    assert rows[0]["holding_seconds"]==0
    assert rows[0]["realized_r"]==-1.5
    ticks=[tick(0),tick(900),tick(900,107,108),tick(900,90,91)]
    _,(_,rows)=run(ticks)
    assert rows[0]["exit_cursor"]==2 and rows[0]["realized_r"]==3
    assert rows[0]["time_to_mfe_seconds"]==0


@pytest.mark.parametrize("identity",STRATEGIES[:3])
def test_gap_entry_and_delay_are_causal(identity):
    ticks=[tick(0),tick(899),tick(910),tick(911,102,103),tick(912,104,105)]
    runner,(m,rows)=run(ticks,Scripted(identity),costs=CostModel(entry_delay_ticks=1,entry_delay_seconds=11))
    r=rows[0]
    assert r["signal_timestamp"]==(T+timedelta(seconds=900)).isoformat()
    assert r["entry_cursor"]==3 and r["entry_price"]==103
    assert r["entry_delay_seconds"]==11 and r["entry_delay_ticks"]==1
    assert runner.strategy.observed[0][1]==100


def test_eof_no_quote_unresolved_and_source_exit():
    ticks=[tick(0),tick(899)]
    config=ReplayConfig(STRATEGIES[0],tick_fingerprint(ticks),"m","c")
    r=StrategyReplayRunner(config,Scripted())
    for t in ticks:r.push(t)
    m,rows=r.finish(T+timedelta(seconds=900))
    assert rows[0]["state"]=="REJECTED_NO_QUOTE" and m["no_quote_entries"]==1
    _,(m,rows)=run([tick(0),tick(900)])
    assert rows[0]["state"]=="UNRESOLVED_AT_END" and m["closed_trades"]==0
    _,(m,rows)=run([tick(0),tick(900)],exit_mode="SOURCE_CONTROL")
    assert rows[0]["state"]=="CLOSED_SOURCE_EXIT" and rows[0]["realized_r"]==-.5


@pytest.mark.parametrize("short",[False,True])
def test_structural_price_geometry_time_exit_and_separate_3r(short):
    ticks=[tick(0),tick(900),tick(900+86400,100,101)]
    _,(m,rows)=run(ticks,Scripted(STRATEGIES[3],short))
    r=rows[0]
    assert r["initial_risk"]==3 and abs(r["target"]-r["entry_price"])==20
    assert r["state"]=="CLOSED_TIME" and r["holding_seconds"]==86400
    _,(m,rows)=run(ticks,Scripted(STRATEGIES[3],short),exit_mode="FIXED_R")
    assert abs(rows[0]["target"]-rows[0]["entry_price"])==9


def test_cost_overlays_accounting_and_invalid_geometry():
    ticks=[tick(0),tick(900),tick(901,110,111)]
    _,(_,rows)=run(ticks,costs=CostModel(commission_r=.1,swap_r_per_day=.2,adverse_slippage=.25))
    r=rows[0]
    assert r["entry_price"]==101.25 and r["exit_price"]==109.75
    assert r["initial_risk"]==2.25
    assert r["cost_adjusted_r"]==pytest.approx(8.5/2.25-.1-.2/86400)
    _,(m,rows)=run(ticks,Scripted(stop=105))
    assert rows[0]["state"]=="REJECTED_BAD_GEOMETRY" and m["filled_entries"]==0


@pytest.mark.parametrize("identity,expected",[(STRATEGIES[0],2),(STRATEGIES[4],1),(STRATEGIES[1],1)])
def test_same_strategy_position_limit(identity,expected):
    _,(m,rows)=run([tick(0),tick(900),tick(1800)],Scripted(identity,every=True))
    assert m["signals"]==2 and m["filled_entries"]==expected
    if expected==1:assert rows[-1]["state"]=="REJECTED_POSITION_LIMIT"


@pytest.mark.parametrize("cut",[0,1,2,3,4])
def test_checkpoint_resume_matches_uninterrupted(cut):
    ticks=[tick(0),tick(899),tick(900),tick(900,102,103),tick(901,107,108)]
    runner,expected=run(ticks)
    partial=StrategyReplayRunner(runner.config,Scripted())
    for t in ticks[:cut]:partial.push(t)
    cp=json.loads(json.dumps(partial.checkpoint()))
    resumed=StrategyReplayRunner(runner.config,Scripted()).run(iter(ticks),checkpoint=cp)
    assert resumed==expected
    bad=replace(runner.config,data_fingerprint="different")
    with pytest.raises(ValueError,match="incompatible"):
        StrategyReplayRunner(bad,Scripted()).run(iter(ticks),checkpoint=cp)


def test_reproducibility_corruption_order_and_input_guards(tmp_path):
    ticks=[tick(0),tick(900),tick(901,107,108)]
    r,(m,ledger)=run(ticks)
    assert run(ticks)[1]==(m,ledger)
    save_result(tmp_path/"a",m,ledger,{"classification":"SYNTHETIC"},parquet=True)
    assert inspect_result(tmp_path/"a")== (m,ledger)
    save_result(tmp_path/"b",m,ledger,{})
    assert compare_results(tmp_path/"a",tmp_path/"b")["classification"]=="EXACT"
    with pytest.raises(FileExistsError):save_result(tmp_path/"a",m,ledger,{})
    (tmp_path/"a/trades.jsonl").write_text("")
    with pytest.raises(ValueError,match="ledger"):inspect_result(tmp_path/"a")
    with pytest.raises(ValueError,match="chronological"):run([tick(1),tick(0)])
    with pytest.raises(ValueError,match="symbol"):run([replace(tick(0),symbol="EURUSD")])
    with pytest.raises(ValueError,match="finalized"):r.push(tick(902))
    config=replace(r.config,data_fingerprint="bad")
    with pytest.raises(ValueError,match="fingerprint"):StrategyReplayRunner(config,Scripted()).run(ticks)


@pytest.mark.parametrize("kwargs",[
    {"spread_multiplier":2},{"commission_r":-1},{"adverse_slippage":float("nan")},
    {"entry_delay_ticks":1.5}])
def test_cost_validation(kwargs):
    with pytest.raises(ValueError):CostModel(**kwargs)


def test_registry_excludes_disabled_and_locked_usage():
    with pytest.raises(ValueError):ReplayConfig("ny_orb_research","d","m","c")
    with pytest.raises(ValueError):ReplayConfig(STRATEGIES[0],"d","m","c",data_usage="LOCKED")
    with pytest.raises(ValueError):ReplayConfig(STRATEGIES[1],"d","m","c",exit_mode="SOURCE_CONTROL")


def test_metrics_streaks_grouping_and_top_removal():
    rows=[]
    for i,v in enumerate([3,3,-1,-2,0,2]):
        rows.append({"trade_id":str(i),"exit_cursor":i,"realized_r":v,"cost_adjusted_r":v,
            "mfe_r":max(0,v),"mae_r":max(0,-v),"holding_seconds":60,
            "exit_timestamp":f"2025-0{1+i%2}-01T00:00:00+00:00",
            "direction":"LONG","strategy_id":"fixture","timeframe":"M15"})
    m=metrics(rows)
    assert m["net_r"]==5 and m["expectancy_r"]==pytest.approx(5/6)
    assert m["profit_factor"]==pytest.approx(8/3) and m["maximum_drawdown_r"]==3
    assert m["longest_winning_streak"]==2 and m["longest_losing_streak"]==2
    assert m["breakevens"]==1 and m["median_r"]==1
    assert grouped_metrics(rows)["month"]["2025-01"]["trade_count"]==3
    assert remove_top_trades(rows,2)["net_r"]==-1
    assert metrics([])["win_rate"] is None
    with pytest.raises(ValueError):remove_top_trades(rows,-1)


@pytest.mark.parametrize("identity",STRATEGIES)
def test_all_real_m2_wrappers_run_generic_engine(identity):
    from goldai.replay.io import synthetic_ticks
    ticks=list(synthetic_ticks(32))
    config=ReplayConfig(identity,tick_fingerprint(ticks),"fixture","commit")
    m,rows=StrategyReplayRunner(config).run(iter(ticks))
    assert m["tick_count_processed"]==129 and m["strategy_id"]==identity
    assert m["execution_model"]=="EXACT_BID_ASK_OFFLINE"


@pytest.mark.parametrize("kind",["ema","supply","structural"])
@pytest.mark.parametrize("short",[False,True])
def test_m2_ready_candidates_integrate_from_canonical_ticks(kind,short):
    from test_m2_migration import ema_rows,supply_rows,structural_rows
    from goldai.strategies.migrated import build_strategy
    fn,identity,seconds={"ema":(ema_rows,STRATEGIES[0],900),
        "supply":(supply_rows,STRATEGIES[4],900),
        "structural":(structural_rows,STRATEGIES[3],3600)}[kind]
    rows=fn(short);ticks=[]
    # Align H1 fixture origin separately.
    start=datetime(2025,1,6,tzinfo=UTC)
    for i,(o,h,l,c) in enumerate(rows):
        for offset,price in [(0,o),(1,h),(2,l),(seconds-1,c)]:
            ticks.append(MarketTick("XAUUSD",start+timedelta(seconds=i*seconds+offset),price,price+.2,"fixture"))
    close=rows[-1][-1]
    ticks.append(MarketTick("XAUUSD",start+timedelta(seconds=len(rows)*seconds),close,close+.2,"fixture"))
    config=ReplayConfig(identity,tick_fingerprint(ticks),"fixture","commit")
    m,ledger=StrategyReplayRunner(config).run(iter(ticks))
    assert m["filled_entries"]>=1
    assert ledger[-1]["direction"]==("SHORT" if short else "LONG")


def test_cli_synthetic_inspect_compare_and_checkpoint(tmp_path,capsys):
    dest=tmp_path/"run"
    base=["replay","run","--strategy",STRATEGIES[0],"--synthetic","--output",str(dest)]
    assert main(base)==0
    assert "DATA_USAGE_DECLARATION" in capsys.readouterr().out
    assert main(["replay","inspect",str(dest),"--json"])==0
    assert main(["replay","compare",str(dest),str(dest)])==0
    assert main(["replay","list-strategies"])==0
    assert main(base)==2
    cp=tmp_path/"checkpoint.json"
    assert main(["replay","run","--strategy",STRATEGIES[0],"--synthetic",
        "--output",str(tmp_path/"partial"),"--checkpoint-at","30","--checkpoint-output",str(cp)])==0
    assert main(["replay","run","--strategy",STRATEGIES[0],"--synthetic",
        "--output",str(tmp_path/"resumed"),"--resume",str(cp)])==0
    assert inspect_result(dest)==inspect_result(tmp_path/"resumed")


def test_prepared_source_usage_governance_and_stream(tmp_path,capsys):
    raw=tmp_path/"ticks.csv"
    raw.write_text("20250106 000000000,100,101\n20250106 001500000,100,101\n")
    prep=prepare_histdata(raw,"XAUUSD",tmp_path/"data")
    p=prep.manifest_path
    declaration={"data_manifest_sha":hashlib.sha256(p.read_bytes()).hexdigest(),"locked":False,
        "classification":"DEVELOPMENT","first_tick":prep.manifest.first_tick,"last_tick":prep.manifest.last_tick}
    m,sha,factory=prepared_source(p,declaration)
    assert tick_fingerprint(factory())==m.canonical_data_fingerprint
    usage=tmp_path/"usage.json";usage.write_text(json.dumps(declaration))
    assert main(["replay","run","--strategy",STRATEGIES[0],"--data",str(p),"--usage",str(usage),
                 "--output",str(tmp_path/"result")])==0
    for key,value in [("locked",True),("first_tick","wrong"),("data_manifest_sha","bad"),("classification","LOCKED")]:
        with pytest.raises(ValueError):prepared_source(p,{**declaration,key:value})


def test_no_broker_imports_or_calls():
    root=Path(__file__).parents[1]/"src/goldai/replay"
    for p in root.glob("*.py"):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node,ast.ImportFrom):
                assert not any(s in (node.module or "") for s in ("execution","mt5","broker"))
            if isinstance(node,ast.Attribute):
                assert node.attr not in {"order_send","position_close","order_modify"}


def test_checkpoint_refuses_version_prefix_and_short_input():
    ticks=[tick(0),tick(900),tick(901)]
    runner=StrategyReplayRunner(ReplayConfig(STRATEGIES[0],tick_fingerprint(ticks),"m","c"),Scripted())
    for t in ticks[:2]:runner.push(t)
    cp=runner.checkpoint()
    for key in ("engine_version","strategy_version"):
        changed=json.loads(json.dumps(cp))
        changed["identity"][key]="different"
        changed["checkpoint_hash"]=fingerprint({k:v for k,v in changed.items() if k!="checkpoint_hash"})
        with pytest.raises(ValueError,match="incompatible"):
            StrategyReplayRunner(runner.config,Scripted()).run(ticks,checkpoint=changed)
    with pytest.raises(ValueError,match="prefix/state"):
        StrategyReplayRunner(runner.config,Scripted()).run([tick(0,100.1,101),*ticks[1:]],checkpoint=cp)
    with pytest.raises(ValueError,match="beyond dataset"):
        StrategyReplayRunner(runner.config,Scripted()).run(ticks[:1],checkpoint=cp)


def test_duplicate_and_foreign_decision_are_rejected():
    class SameSignal(StrategyDecision):
        @property
        def signal_id(self):return "provider-duplicate"
    class Duplicating(Scripted):
        def evaluate(self,market):
            d=super().evaluate(market)
            return SameSignal(**{k:getattr(d,k) for k in d.__dataclass_fields__})
    _,(m,rows)=run([tick(0),tick(900),tick(1800)],Duplicating(every=True))
    assert m["signals"]==1 and m["duplicate_signals"]==1 and len(rows)==1
    class Foreign(Scripted):
        def evaluate(self,market):
            return replace(super().evaluate(market),strategy_version="foreign")
    with pytest.raises(ValueError,match="decision boundary"):
        run([tick(0),tick(900)],Foreign())


def test_segments_and_json_stdout(tmp_path,capsys):
    from goldai.replay.metrics import segment_metrics
    _,(_,rows)=run([tick(0),tick(900),tick(901,107,108)])
    bounds={"feb":("2025-02-01T00:00:00+00:00","2025-03-01T00:00:00+00:00")}
    assert segment_metrics(rows,bounds)["feb"]["net_r"]==3
    with pytest.raises(ValueError):segment_metrics(rows,{"bad":("2025-01-01","2025-02-01")})
    assert main(["replay","run","--strategy",STRATEGIES[0],"--synthetic",
                 "--output",str(tmp_path/"json"),"--json"])==0
    captured=capsys.readouterr()
    assert json.loads(captured.out)["data_usage"]=="SYNTHETIC"
    assert "DATA_USAGE_DECLARATION" in captured.err


def test_release_excludes_replay_outputs(tmp_path):
    from scripts.create_release_zip import should_include
    for name in ("runs/a/manifest.json","trial.usage.json","checkpoint.json","private.key","venv/bin/python"):
        path=tmp_path/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text("private runtime contents")
        assert not should_include(path,tmp_path,tmp_path/"release.zip")
