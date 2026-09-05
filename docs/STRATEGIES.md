# Milestone 2 strategy contract

Version 0.3.0.dev0 migrates recovered candidate detectors. All strategy versions are 1.0.0, status RESEARCH, execution authorization NONE. Operational means candidate evaluation only.

| ID | Timeframe | Frozen intent |
|---|---|---|
| ema50_chandelier_m15_touch | M15 | Long/short, side Chandelier stop, 2R |
| poc_continuation_retest_long | M5 | Long POC retest, 3R |
| pdh_pdl_breakout_retest | M5 | Short prior-day-low retest, 3R |
| xauusd_structural_break_trend_v1 | H1 | Long/short, actual quote-relative $3 stop / $20 target |
| m15_supply_demand | M15 | Long/short, distal stop, 3R |
| m15_supply_demand_2r | M15 | Independent long/short variant, distal stop, 2R |

The old h1_structural_break_trend ID resolves to the canonical structural implementation. The seven-ID default_registry API remains compatible; migration_registry exposes the expanded catalog. Rejected M5 EMA and supply/demand variants and future scalpers, NY ORB and ML remain disabled.

## Usage and inputs

Install with `python -m pip install -e ".[strategies]"`. NumPy 2.3.5 and pandas 2.2.3 preserve the validated numeric environment. Base contracts and discovery do not import those optional dependencies.

Use `build_strategy(id)` from goldai.strategies.migrated, then evaluate a MarketState containing the complete immutable bar prefix in history[timeframe]. Histories must contain ordered, non-overlapping COMPLETE bars with matching symbol/timeframe and exact duration. Evaluation occurs at the last completed bar's UTC close. Future bars, revised history, removed prefixes and backward evaluation times reject input. Stale data returns WAITING.

Use XAUUSD Bid OHLC and original tick-count semantics. Balanced components derive their original H1/H4 features from M5 history. Preserve enough history for EMA200 warm-up on H4. Their original feature alignment uses the M5 open timestamp, retaining the source lag. No current incomplete higher-timeframe candle is exposed.

## Decisions and state

READY represents a candidate, never an order or fill. Entry and target may be unset because a future executable quote is not yet available. EntryIntent records first-quote-at-or-after-close or next-bar quote semantics. Long preview uses Ask; short preview uses Bid. Its pure preview calculates hypothetical geometry only. Structural stop/target distances rebase to that quote; its 1440-minute limit is metadata, with no position lifecycle.

EMA carries forming, waiting, invalidation and ready states from recovered setup rules. Supply/demand reconstructs zone formation, retest, expiry, invalidation and consumption from the prefix. POC/PDL preserve pending breakout/retest state and quality filters. No shared portfolio state connects the families.

Stable signal identities include strategy/version, direction, symbol, timeframe, setup and signal timestamps and geometry. Repeated READY candidates become COOLDOWN. reset() starts a separate stream. snapshot()/restore() preserve deduplication and prefix identity; callers retain the full matching history.

The source EMA batch audit labels unfinished EOF setups. The wrapper keeps these forming/waiting, since EOF is not a live invalidation. Original Balanced generators omit their last outcome-horizon bars; the candidate adapter removes only that simulator availability restriction. Source parity compares the shared eligible prefix.

## Verification

Run `python -m pytest`, `python -m goldai strategies validate` and `python -m goldai strategies describe ema50_chandelier_m15_touch`.
See STRATEGY_MIGRATION_M2.md for exact recovered rules and STRATEGY_EVIDENCE.md for evidence limits.
