# M3 replay semantics, recorded before implementation

Base: 4b21e4d61892ffb18cf18ce9f7d7028656b1db91. Strategy kernels and wrappers remain frozen.

| Strategy | Decision | Intent | Entry | Stop | Target | Hold | Same-strategy positions |
|---|---|---|---|---|---|---|---|
| ema50_chandelier_m15_touch | M15 close | FIRST_QUOTE_AT_OR_AFTER_CLOSE | Ask long, Bid short | Fixed M2 Chandelier | Actual entry 2R | None in primary | Overlap allowed, production execute_rows evaluates every signal |
| poc_continuation_retest_long | M5 close | NEXT_BAR_EXECUTABLE_QUOTE | Ask | Fixed structural | Actual entry 3R | None in exact-tick primary | One active/pending |
| pdh_pdl_breakout_retest | M5 close | NEXT_BAR_EXECUTABLE_QUOTE | Bid | Fixed structural | Actual entry 3R | None in exact-tick primary | One active/pending |
| xauusd_structural_break_trend_v1 | H1 close | FIRST_QUOTE_AT_OR_AFTER_CLOSE, quote-relative geometry | Ask long, Bid short | $3 from actual fill | $20 from actual fill | 1440 minutes | One active/pending |
| m15_supply_demand | M15 close | FIRST_QUOTE_AT_OR_AFTER_CLOSE | Ask long, Bid short | Fixed distal | 3R, resting target fill | None | One active/pending |
| m15_supply_demand_2r | M15 close | FIRST_QUOTE_AT_OR_AFTER_CLOSE | Ask long, Bid short | Fixed distal | 2R, resting target fill | None | One active/pending |

## Recovered source

Archive identities remain in STRATEGY_MIGRATION_M2.md. EMA production_backtest.execute_rows and video_source_v1.execute_signal use searchsorted(left), allow overlapping signals, inspect the entry tick, stop before target, fill actual executable quotes and force END_OF_DATA in the source experiment. Primary M3 retains unresolved EOF; an explicit EMA SOURCE_CONTROL mode supports its recovered EOF liquidation, without any continuation/profit overlay.

Supply research structural_pullback_v1.ExecutionBook allows one open/pending position. Stops fill the actual close-side quote; targets fill the resting level, without favorable overshoot. M3 ACCEPTED resolves to FIXED_R_RESTING_TARGET. Explicit FIXED_R uses actual exit quotes and is an expected semantic difference.

Structural application/gold_structural_demo._exit_reason checks executable stop, target, then 24-hour timeout. SOURCE_CONTROL retains $3/$20/1440. A separate FIXED_R comparison uses 3R and remains research only.

Balanced entry_lab.simulate_signals uses next observed M5 bar open, structural stops, nominal 3R/-1R, an outcome horizon of 96 bars, ATR risk filters and bar ambiguity rejection. These outcome-selection rules cannot be reproduced as causal exact-tick exits by discarding unresolved trades. M3 preserves M2 candidate rules and exact-tick 3R, carries unresolved positions to EOF, and flags SIMULATOR_POLICY_FALLBACK. No proprietary public source exit is invented. Balanced SOURCE_CONTROL is unavailable. Prior historical parity is NOT_RERUN.

## Common tick and boundary order

Before exposing an arriving tick to the strategy, finalize any existing candle whose close is at or before that tick. Evaluate at the completed candle's actual close time using only prior ticks. Missing intervals produce no synthetic bars. Queue the decision, process existing position exits on the arriving quote, then resolve eligible entries, then inspect their close side on that same tick. One-position checks occur at signal admission, so a position still open at the decision boundary suppresses that same-strategy candidate even if the next quote closes it. This common sequencing is explicitly flagged SIMULATOR_POLICY_FALLBACK where historical ordering is not reproduced.

Next-bar intent means first quote in the next observed bar, not an extra full bar of latency. A gap may delay either intent. No earlier tick can fill. Equal timestamps retain input order, including distinct quotes; stream cursor disambiguates them. Stop wins any abnormal simultaneous trigger. Valid ordered stop/target geometry makes simultaneous price triggers impossible on one close-side scalar. Spread can cause an immediate entry-tick stop. Zero-duration positions are valid.

LONG exits at Bid, SHORT exits at Ask. Gapped stops always use actual quotes. Targets use actual quotes except the explicit recovered supply resting-target model. Signed favorable slippage to trigger level and actual quote are both recorded. Additional adverse slippage is explicit, applied on entry/exit; commission and swap overlays are normalized R. True Bid/Ask data rejects spread multipliers other than one.

Realized R uses constant initial entry-to-stop risk, without compounding. MFE is nonnegative favorable movement, MAE nonnegative adverse movement on observed executable close-side quotes, including entry and exit ticks. Time to extrema uses the first occurrence. Baseline costs are zero beyond embedded spread. No broker adapter or account balance participates.
