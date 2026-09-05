# Milestone 2 source map, before implementation

Base: `0c8cb3dcb2cf48ee6a072a340436d7dc7f04fa07`. Author: Babatunde Akanji.
Initial Git state is clean. The named accidental untracked file is absent here.
This opening map records the pre-implementation state. Completion results follow below; historical performance has not been rerun.

## Recovered artifacts

| Source | SHA-256 |
|---|---|
| Skydev_Gold_M15_Operator_v1.0.0.zip | 5388073ec3c36325b9a743ed90a10444e2fa7a07573245f1fba56add8edc7abf |
| skydev_v2-0.8.6-py3-none-any.whl | 728872bb3d9b0e675bbc568c1d5d5d1b2373ae9d57b26fb0cc4289415f8e32e1 |
| skydev_v2_0.8.7_SUPPLY_DEMAND_V1_RESEARCH_SOURCE.zip | a8c6b2ea084372e10ff21d2923762dba02ca8fd94fb4616f91863b2d2c18123c |
| gold_ai_mt5_python_v1.2.0.zip | fd07303d6f921cb994aa6a952121092370b36936fe22246fbe5f708ae369bf78 |

## Proposed strategy mapping

All intended migrated versions are `1.0.0`. Every execution authorization remains NONE.

| Strategy ID | Exact source | Rule completeness | Entry / stop / target | Reference evidence | Target posture / unresolved work |
|---|---|---|---|---|---|
| ema50_chandelier_m15_touch | M15 operator: video_source_v1.py, indicators.py, live_engine.py; PRODUCTION_ACCEPTANCE.md | Detector recovered | First quote at or after confirmation close, Ask long / Bid short; side Chandelier; actual-entry 2R | Reported production replay: 30 trades, +16.585R | Candidate detector only; fixture parity pending |
| poc_continuation_retest_long | GoldAI 1.2: epic_strategies.py, fine_tune.py, entry_lab.py, indicators.py; FINE_TUNE_RESEARCH.md | Independent internal entry recovered, not the public proprietary entry | Next M5 open executable quote; min(retest low, POC) minus 0.2 ATR; 3R | Balanced combined 67 trades / +49R, post-selection development | RESEARCH; feature and signal parity pending; M5, not scaffold M15 |
| pdh_pdl_breakout_retest | Same GoldAI 1.2 files, generate_pdh_pdl_retest_v2 | Internal short detector recovered | Prior UTC-day low retest; max(retest high, PDL) plus 0.2 ATR; next M5 executable quote, 3R | Same combined sample, no independent metrics inferred | RESEARCH; feature parity pending; M5 |
| xauusd_structural_break_trend_v1 | Skydev 0.8.6 strategies/product.py, application/gold_structural_demo.py; SYMBOL_SPECIFIC_PRODUCT_POLICY_0.8.6.md | Confirmed unique pivots and cross rule recovered | Actual quote-relative 3 USD stop, 20 USD target; 1440-minute hold metadata only | Reported pooled Apr-Jun 18 trades, PF 1.441 | Candidate detector only; preserve old scaffold ID as alias |
| m15_supply_demand | Skydev 0.8.7 research/supply_demand_v1.py and structural_pullback_v1.py; SUPPLY_DEMAND_V1_COMBINED_REPORT.md | Zone construction and engine recovered | First quote at confirmation close; distal edge; separate 2R and 3R | M15 3R selected 8 trades, +3.984R | RESEARCH only; never promote; fixture parity pending |

## Exact details that summaries omitted

- EMA touch invalidation uses strict low < EMA / high > EMA, not equality. Oversize rejects >= 3 times the arithmetic mean of the previous 20 ranges. Structure is the earliest maximum/minimum between EMA break and first pullback candle. The second pullback candle cannot itself confirm. Chandelier ratchets using current close; EMA seeds immediately but ATR starts after 22 bars.
- Structural pivots require a unique maximum/minimum in the nine-bar window. The detector needs at least 16 bars, two highs and two lows, and a previous-close crossing test. The old detector's mid-price and opposite-side invalidation are reference fields, not actual fill geometry; the lifecycle rebases the stop from actual entry. No lifecycle is to be migrated.
- Supply/demand compactness is <= 0.90 ATR per base candle, <= 1.25 ATR for the full base; longest suffix of one through four candles. ATR includes the current completed displacement candle, despite the helper name _prior_atr. Same-direction overlapping zones are suppressed. Manage old zones before creating new zones, newest zone first. Distal invalidation uses close, not wick. Expiry checks use > 24 and > 3.
- POC has 36 bins, typical-price tick-count weights (minimum one), 70% value area, right-side tie preference, and profile refresh every 12 bars. Breakout is above VAH + 0.05 ATR; retest is POC with 0.20 ATR tolerance and 12-bar deadline. H1/H4 EMA200 voting remains part of the original entry logic.
- PDH/PDL short uses PDL, UTC-day reset, bearish retest close, minimum 0.20 ATR body, and original H1/H4 direction votes in addition to the documented filters.
- Balanced research generators exclude an end-of-data outcome horizon. That is a simulator availability restriction, not an entry rule. A causal candidate interface must document the distinction and prove identical signals on the shared eligible prefix.

## Evidence limitations

Source reports are reference evidence, not results of this migration. No raw historical replay has run in GoldAI M2. Original engines contain execution code which must remain outside this repository. No strategy may be marked migrated until deterministic parity and causality checks pass. Source gaps or unresolved behavior conflicts must remain non-operational.

Future liquidity sweep, VWAP/value-area scalpers, NY ORB and ML gates remain placeholders. M5 EMA baseline and M5 supply/demand remain rejected/disabled research history.

## Completion record

All five mapped families passed synthetic source checks. Pending table items are resolved at candidate-detector level. Six frozen variants evaluate candidates. No selected family is SPEC_INCOMPLETE. All remain RESEARCH with authorization NONE.

Parity counts: EMA 31, supply/demand 27, POC 13, PDL 115 signals; 16 Balanced feature prefixes; 72 structural prefixes including two READY cases. See STRATEGY_PARITY_M2.json and STRATEGY_EVIDENCE.md. Historical replay remains outstanding.

Only pure recovered kernels were migrated. Broker code, simulator exits and outcome-horizon availability were not copied into candidate execution paths. Thresholds were not tuned. Indicator seeds, tie ordering, causal alignment and strict comparisons retain recovered behavior.
