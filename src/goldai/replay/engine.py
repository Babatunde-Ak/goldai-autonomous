from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
from importlib.metadata import version

from goldai.data.aggregation import CanonicalCandleAggregator
from goldai.market import MarketState, MarketSession
from goldai.strategies.models import Direction, EntryIntent, StrategyState
from goldai.replay import ENGINE_VERSION, STRATEGIES
from goldai.replay.contracts import ReplayConfig, TradeRecord, canonical, fingerprint, source_hash
from goldai.replay.metrics import metrics, grouped_metrics


class ReplayClock:
    def __init__(self):
        self.timestamp = None
        self.cursor = -1

    def advance(self, tick):
        if self.timestamp is not None and tick.timestamp < self.timestamp:
            raise ValueError("ticks must remain chronological")
        self.timestamp = tick.timestamp
        self.cursor += 1


class FillSimulator:
    def __init__(self, config):
        self.config = config

    def enter(self, trade, tick, cursor):
        if tick.timestamp < datetime.fromisoformat(trade.signal_timestamp):
            return False
        if trade.eligible_cursor is None:
            trade.eligible_cursor = cursor
        costs = self.config.costs
        eligible_time = datetime.fromisoformat(trade.signal_timestamp) + timedelta(seconds=costs.entry_delay_seconds)
        if cursor < trade.eligible_cursor + costs.entry_delay_ticks or tick.timestamp < eligible_time:
            return False
        intent = EntryIntent(**trade.intent)
        quote = tick.ask if trade.sign == 1 else tick.bid
        entry = quote + trade.sign*costs.adverse_slippage
        try:
            # Spread remains present in the quote. Geometry rebases to stressed fill.
            if trade.sign == 1:
                entry, stop, target = intent.preview(Direction.LONG, tick.bid, entry, trade.stop)
            else:
                entry, stop, target = intent.preview(Direction.SHORT, entry, tick.ask, trade.stop)
        except ValueError:
            trade.state = "REJECTED_BAD_GEOMETRY"
            return True
        if self.config.strategy_id == STRATEGIES[3] and self.config.resolved_exit_mode == "FIXED_R":
            target = entry + trade.sign*3*abs(entry-stop)
        if target <= 0:
            trade.state = "REJECTED_BAD_GEOMETRY"
            return True
        trade.entry_quote, trade.entry_price = quote, entry
        trade.stop, trade.target, trade.initial_risk = stop, target, abs(entry-stop)
        trade.entry_timestamp, trade.entry_cursor = tick.timestamp.isoformat(), cursor
        trade.entry_side = "ASK" if trade.sign == 1 else "BID"
        trade.entry_delay_ticks = cursor-trade.eligible_cursor
        trade.entry_delay_seconds = (tick.timestamp-datetime.fromisoformat(trade.signal_timestamp)).total_seconds()
        trade.state = "OPEN"
        return True

    def observe(self, trade, tick, cursor, source_eof=False):
        quote = tick.bid if trade.sign == 1 else tick.ask
        elapsed = trade.elapsed(tick.timestamp)
        move = trade.sign*(quote-trade.entry_price)
        if move > trade.mfe_price:
            trade.mfe_price, trade.time_to_mfe_seconds = move, elapsed
        if -move > trade.mae_price:
            trade.mae_price, trade.time_to_mae_seconds = -move, elapsed
        trade.mfe_r, trade.mae_r = trade.mfe_price/trade.initial_risk, trade.mae_price/trade.initial_risk
        trade.holding_seconds = elapsed
        stop_hit = trade.sign*(quote-trade.stop) <= 0
        target_hit = trade.sign*(quote-trade.target) >= 0
        if stop_hit and target_hit:
            trade.flags.append("SIMULATOR_POLICY_FALLBACK:STOP_FIRST")
        reason = "STOP" if stop_hit else "TARGET" if target_hit else None
        hold = trade.intent.get("max_hold_minutes")
        if reason is None and hold is not None and elapsed >= hold*60:
            reason = "TIME"
        if reason is None and source_eof:
            reason = "SOURCE_EXIT"
        if reason is None:
            return
        level = trade.stop if reason == "STOP" else trade.target if reason == "TARGET" else quote
        fill = level if reason == "TARGET" and self.config.resolved_exit_mode == "FIXED_R_RESTING_TARGET" else quote
        trade.exit_quote = quote
        trade.exit_price = fill-trade.sign*self.config.costs.adverse_slippage
        trade.exit_side = "BID" if trade.sign == 1 else "ASK"
        trade.exit_timestamp, trade.exit_cursor = tick.timestamp.isoformat(), cursor
        trade.exit_reason, trade.state = reason, "CLOSED_"+reason
        trade.slippage_to_level = trade.sign*(trade.exit_price-level)
        trade.pnl_price = trade.sign*(trade.exit_price-trade.entry_price)
        trade.gross_r = trade.realized_r = trade.pnl_price/trade.initial_risk
        trade.cost_adjusted_r = trade.gross_r-self.config.costs.commission_r-self.config.costs.swap_r_per_day*elapsed/86400


class StrategyReplayRunner:
    """Streams ticks; keeps bars and the per-strategy ledger, not tick history.

    Checkpoint recovery deliberately replays and verifies the consumed prefix.
    This avoids unsafe pickle and partially serialized aggregator/indicator state.
    """
    def __init__(self, config: ReplayConfig, strategy=None):
        if strategy is None:
            from goldai.strategies.migrated import build_strategy
            strategy = build_strategy(config.strategy_id)
        if strategy.strategy_id != config.strategy_id:
            raise ValueError("strategy identity mismatch")
        strategy.reset()
        self.config, self.strategy = config, strategy
        self.clock = ReplayClock()
        self.aggregator = CanonicalCandleAggregator(strategy.timeframe)
        self.bars, self.trades, self.pending, self.open = [], [], [], []
        self.seen = set()
        self.signals = self.duplicates = 0
        self.last_tick = self.first_timestamp = None
        self.data_digest = hashlib.sha256()
        self.prefix_hash = fingerprint([])
        self.spec_hash = fingerprint({"id": strategy.strategy_id, "version": strategy.version,
                                      "timeframe": strategy.timeframe.value, "source_hash": source_hash(True)})
        self.identity = {"engine_version": ENGINE_VERSION, "config": asdict(config),
                         "strategy_version": strategy.version, "strategy_spec_hash": self.spec_hash,
                         "code_source_hash": source_hash(),
                         "numerical_dependencies": {name: version(name) for name in ("numpy", "pandas")}}
        self.run_id = fingerprint(self.identity)
        self.fill = FillSimulator(config)
        self.finished = False

    def _decision(self, bar):
        self.bars.append(bar)
        market = MarketState(self.config.symbol, bar.closed_at, MarketSession.CLOSED,
            latest_tick=self.last_tick, latest_bars={self.strategy.timeframe: bar},
            stale=False, history={self.strategy.timeframe: tuple(self.bars)})
        decision = self.strategy.evaluate(market)
        if decision.state is not StrategyState.READY:
            return
        if (decision.timestamp != bar.closed_at or decision.symbol != self.config.symbol
                or decision.entry_intent is None or decision.strategy_id != self.strategy.strategy_id
                or decision.strategy_version != self.strategy.version or decision.timeframe != self.strategy.timeframe):
            raise ValueError("invalid strategy decision boundary")
        if decision.signal_id in self.seen:
            self.duplicates += 1
            return
        self.seen.add(decision.signal_id)
        self.signals += 1
        trade = TradeRecord(fingerprint([self.run_id, decision.signal_id]), decision.signal_id,
            decision.strategy_id, decision.strategy_version, decision.direction.value,
            decision.timeframe.value, (decision.setup_timestamp or decision.timestamp).isoformat(),
            decision.timestamp.isoformat(), asdict(decision.entry_intent), decision.metadata,
            self.clock.cursor, stop=decision.stop,
            flags=["SIMULATOR_POLICY_FALLBACK:COMMON_BOUNDARY_ORDER"])
        if self.config.strategy_id in STRATEGIES[1:3]:
            trade.flags.append("SIMULATOR_POLICY_FALLBACK:BALANCED_EXACT_TICK_PRIMARY")
        self.trades.append(trade)
        if self.config.position_limit and len(self.open)+len(self.pending) >= self.config.position_limit:
            trade.state = "REJECTED_POSITION_LIMIT"
        else:
            self.pending.append(trade)

    def push(self, tick):
        if self.finished:
            raise ValueError("run already finalized")
        if tick.symbol != self.config.symbol:
            raise ValueError("tick symbol mismatch")
        self.clock.advance(tick)
        if self.first_timestamp is None:
            self.first_timestamp = tick.timestamp.isoformat()
        # Finalize without passing the new quote into strategy-visible state.
        for bar in self.aggregator.finalize(tick.timestamp):
            self._decision(bar)
        for trade in tuple(self.open):
            self.fill.observe(trade, tick, self.clock.cursor)
            if trade.state != "OPEN":
                self.open.remove(trade)
        for trade in tuple(self.pending):
            if self.fill.enter(trade, tick, self.clock.cursor):
                self.pending.remove(trade)
                if trade.state == "OPEN":
                    self.fill.observe(trade, tick, self.clock.cursor)
                    if trade.state == "OPEN":
                        self.open.append(trade)
        self.aggregator.push(tick)
        self.last_tick = tick
        self.data_digest.update((tick.semantic_json()+"\n").encode())
        self.prefix_hash = fingerprint([self.prefix_hash, tick.to_dict()])

    def checkpoint(self):
        if self.finished:
            raise ValueError("cannot checkpoint a finalized run")
        state = {"identity": self.identity, "cursor": self.clock.cursor,
                 "prefix_hash": self.prefix_hash, "strategy_snapshot": self.strategy.snapshot(),
                 "trade_state": [asdict(t) for t in self.trades],
                 "bar_count": len(self.bars), "last_tick": self.last_tick.to_dict() if self.last_tick else None,
                 "resume_method": "REPLAY_AND_VERIFY_PREFIX"}
        return {**state, "checkpoint_hash": fingerprint(state)}

    def finish(self, observed_until=None):
        if self.finished:
            raise ValueError("run already finalized")
        if observed_until is not None:
            if self.clock.timestamp and observed_until < self.clock.timestamp:
                raise ValueError("EOF observation precedes last tick")
            for bar in self.aggregator.finalize(observed_until):
                self._decision(bar)
        if self.config.data_fingerprint != self.data_digest.hexdigest():
            raise ValueError("dataset fingerprint mismatch")
        for trade in self.pending:
            trade.state = "REJECTED_NO_QUOTE"
        for trade in self.open:
            if self.config.strategy_id == STRATEGIES[0] and self.config.exit_mode == "SOURCE_CONTROL":
                self.fill.observe(trade, self.last_tick, self.clock.cursor, source_eof=True)
            else:
                trade.state = "UNRESOLVED_AT_END"
        self.finished = True
        ledger = [{**asdict(t), "run_id": self.run_id, "data_fingerprint": self.config.data_fingerprint}
                  for t in self.trades]
        stats = metrics(ledger)
        manifest = {**self.identity, "run_id": self.run_id,
            "strategy_id": self.strategy.strategy_id, "symbol": self.config.symbol,
            "decision_timeframe": self.strategy.timeframe.value,
            "execution_model": "EXACT_BID_ASK_OFFLINE", "exit_mode": self.config.resolved_exit_mode,
            "data_manifest_sha": self.config.data_manifest_sha, "data_fingerprint": self.config.data_fingerprint,
            "data_usage": self.config.data_usage, "code_commit_sha": self.config.code_commit,
            "cost_model": asdict(self.config.costs),
            "start_timestamp": self.first_timestamp,
            "end_timestamp": self.last_tick.timestamp.isoformat() if self.last_tick else None,
            "data_period": {"first_tick": self.first_timestamp,
                            "last_tick": self.last_tick.timestamp.isoformat() if self.last_tick else None},
            "observed_until": observed_until.isoformat() if observed_until else None,
            "tick_count_processed": self.clock.cursor+1,
            "bar_counts": {self.strategy.timeframe.value: len(self.bars)},
            "signals": self.signals, "duplicate_signals": self.duplicates,
            "pending_entries": 0,
            "filled_entries": sum(t.entry_price is not None for t in self.trades),
            "rejected_entries": sum(t.state.startswith("REJECTED") for t in self.trades),
            "no_quote_entries": sum(t.state == "REJECTED_NO_QUOTE" for t in self.trades),
            "unresolved_trades": sum(t.state == "UNRESOLVED_AT_END" for t in self.trades),
            "closed_trades": stats["trade_count"], **stats,
            "historical_parity": "NOT_RERUN",
            "warnings": sorted({f for t in self.trades for f in t.flags}),
            "groups": grouped_metrics(ledger), "ledger_hash": fingerprint(ledger)}
        manifest["result_fingerprint"] = fingerprint(manifest)
        return manifest, ledger

    def run(self, ticks, *, checkpoint=None, observed_until=None):
        restored = checkpoint is None
        if checkpoint:
            unsigned = {k:v for k,v in checkpoint.items() if k != "checkpoint_hash"}
            if checkpoint.get("checkpoint_hash") != fingerprint(unsigned) or checkpoint["identity"] != self.identity:
                raise ValueError("incompatible or corrupt checkpoint")
            if checkpoint["cursor"] == -1:
                if self.checkpoint() != checkpoint:
                    raise ValueError("empty checkpoint mismatch")
                restored = True
        for tick in ticks:
            self.push(tick)
            if checkpoint and self.clock.cursor == checkpoint["cursor"]:
                if self.checkpoint() != checkpoint:
                    raise ValueError("resume prefix/state mismatch")
                restored = True
        if not restored:
            raise ValueError("checkpoint cursor beyond dataset")
        return self.finish(observed_until)
