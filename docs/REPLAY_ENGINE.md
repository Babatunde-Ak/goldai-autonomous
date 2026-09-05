# Milestone 3 replay engine

Version 0.4.0.dev0 is an offline correctness checkpoint. Five families, six independent
variants use the unchanged M2 strategy and indicator code. No strategy can suppress another
runner. EMA supports overlapping positions; the other variants admit one pending/open
position at a time. Disabled M5 and incomplete strategy families cannot replay.

## Running

Install Python 3.12+ and `python -m pip install -e ".[dev,data]"`.

```bash
python -m goldai replay list-strategies
python -m goldai replay run --strategy ema50_chandelier_m15_touch --synthetic --output runs/base --json
python -m goldai replay run --strategy ema50_chandelier_m15_touch --synthetic --output runs/stress --commission-r 0.05 --slippage 0.1 --delay-ticks 1 --json
python -m goldai replay inspect runs/base --json
python -m goldai replay compare runs/base runs/stress --json
```

Each output directory must be new. A sibling `.usage.json` is persisted before selected
price ticks are consumed, including interrupted attempts. Choose a new output name after
a failed attempt; do not erase the declaration to hide a trial. `--json` sends the declaration
to stderr and the result manifest to stdout. Inspect and compare emit JSON.

The built-in synthetic fixture is a numeric zigzag, not historical evidence. It is a smoke
test and need not generate a trade in every strategy. Scripted lifecycle tests and actual
M2 EMA/supply/structural READY fixtures test filled trades separately. Balanced integration
runs the real wrapper; its long HTF warm-up and source signal kernels are covered by M2 tests.

## Exact price semantics

See EXECUTION_SEMANTICS.md for the source-backed matrix and fallback labels. Long entries
use Ask and long closes use Bid; shorts enter Bid and close Ask. Spread is already embedded.
Both entry-intent types wait for the first available quote at/after the completed-bar signal
boundary, subject to explicit latency. Geometry rebases to actual stressed entry. No
signal-bar closing price is assumed executable. Current quotes enter strategy state only
on later completed bars. Equal timestamps preserve stream order; gaps are never interpolated.

A pending trade becomes OPEN or REJECTED_BAD_GEOMETRY. Admission can produce
REJECTED_POSITION_LIMIT. OPEN trades close as CLOSED_STOP, CLOSED_TARGET, CLOSED_TIME or
CLOSED_SOURCE_EXIT; others remain UNRESOLVED_AT_END. Pending EOF intent becomes
REJECTED_NO_QUOTE. The final incomplete bar is not forced complete by the CLI. The Python
API can supply an explicit `observed_until` completion boundary, without inventing a quote.
No expiry rule is invented where the recovered source has none.

Stop checks precede target checks, then time checks, on the same quote. Entry ticks also
participate in exits and excursions. Stop gaps fill at actual close-side price. Targets
fill at actual price except accepted supply/demand resting targets, which fill at target
level. EOF normally leaves trades unresolved. EMA SOURCE_CONTROL liquidates at the last
quote as its source does. Structural source control uses $3/$20 and 1,440 minutes; its
explicit FIXED_R research comparison uses $3/3R with the same timeout. Balanced's bar-based
96-bar outcome filtering is not claimed equivalent to exact-tick primary replay.

## Accounting and persistence

Initial risk is the positive distance from actual entry to stop. `pnl_price` is directional
exit minus entry; `realized_r` and `gross_r` divide this by initial risk. They include
configured adverse fill slippage, but precede normalized commission and swap deductions.
`cost_adjusted_r` subtracts round-trip commission R and swap R/day times elapsed days.
Baseline costs are zero. Slippage is applied adversely on both fills in quote price units.
A spread multiplier other than one is rejected on exact Bid/Ask data. No balance or lots
change this constant-risk series.

MFE/MAE use observed executable close-side quotes while open, including the exit quote.
They are nonnegative excursion magnitudes in price and R, with elapsed seconds to first
strict extremum and holding seconds. Stress exit slippage changes realized P&L, not the
observed quote excursion. Source resting-target overshoot may exceed realized target R.

Each new result directory contains DATA_USAGE_DECLARATION.json, trades.jsonl and manifest.json.
`--parquet` also writes trades.parquet when ledger rows exist. Every intent, including rejected
and unresolved intent, remains in the ledger. Nested intent and source metadata are JSON
strings in Parquet. Trade IDs hash run ID plus signal ID. The ledger includes strategy/version,
direction/timeframe, setup/signal/fill/exit timestamps and cursors, quote sides, geometry,
latency, initial risk, costs, R, excursions, holding time, source metadata and fallback flags.
`TradeRecord` in replay/contracts.py is the exact field schema.

Manifest identity includes engine version, code commit or explicit source-archive identity,
code content hash, unchanged strategy/indicator specification hash, numerical dependency
versions, dataset/manifest SHA, period, usage, execution and cost modes. It records counts
of ticks, completed bars, signals, duplicates, fills, rejections, no-quote and unresolved
trades. `pending_entries` is the final pending count, zero after EOF rejection. Canonical
sorted finite JSON drives ledger and result hashes. Wall-clock run time is excluded.

Closed-trade metrics use cost-adjusted R ordered by exit cursor then deterministic trade ID:
counts, wins/losses/breakevens, win rate, mean/median/expectancy, net R, gross profit/loss,
PF, drawdown from starting zero, win/loss streaks, average win/loss, payoff, mean excursions
and mean/median hold. No-loss PF is null with an explanatory status, never fabricated
infinity. Unresolved/rejected rows are excluded from these metrics but counted explicitly.
Year/month attribution uses UTC exit time. Direction, strategy and timeframe groups are
independent summaries. `segment_metrics(rows, {name: (start_iso, end_iso)})` supports explicit
half-open chronological windows, diagnostic only. Simultaneous exits use the documented
trade-ID tie-break; no combined portfolio capital curve is produced.

## Governance and real prepared data

No real price periods were consumed in this milestone. No matching prepared historical
Parquet stream was available in the project/source workspace. Original source/report
archives are reference evidence, not a price dataset. Historical outcome parity is NOT_RERUN.

For later authorized ingestion, replace the paths below with the selected archive and
output. Audit provenance and holdout status before preparation. Do not point preparation
at locked data just to discover what is in it.

```bash
python -m goldai data audit /authorized/XAUUSD.csv --symbol XAUUSD --json
python -m goldai data prepare /authorized/XAUUSD.csv --symbol XAUUSD --output data/canonical
python -m goldai data inspect data/canonical/XAUUSD/manifest.json
```

Create DATA_USAGE_DECLARATION.json with these fields. Copy first/last exactly from the M1
manifest; compute its SHA with `sha256sum data/canonical/XAUUSD/manifest.json`.

```json
{
  "classification": "DEVELOPMENT",
  "locked": false,
  "data_manifest_sha": "REPLACE_WITH_MANIFEST_SHA256",
  "first_tick": "REPLACE_WITH_MANIFEST_FIRST_TICK",
  "last_tick": "REPLACE_WITH_MANIFEST_LAST_TICK",
  "provenance": "Identify authorized raw archive and source SHA"
}
```

```bash
python -m goldai replay run --strategy ema50_chandelier_m15_touch --data data/canonical/XAUUSD/manifest.json --usage DATA_USAGE_DECLARATION.json --output runs/authorized_ema --parquet --json
```

Relative partition locations resolve from the parent of the manifest's symbol directory,
matching M1 preparation. Absolute M1 paths must remain available or be deliberately relocated
with a new manifest SHA. Counts, period, chronology and complete semantic data fingerprint
are verified. Preparation must already be chronological. No runtime sorting or deduplication
changes market evidence. The engine reads Parquet batches and retains bars/ledger, not ticks.

Classifications are DEVELOPMENT, ROBUSTNESS, EVALUATION or PREVIOUSLY_CONSUMED. 2026 cannot
be development/robustness and must be split from earlier evaluation data. July 2026 requires
PREVIOUSLY_CONSUMED plus `prior_consumption_evidence`; otherwise it is refused. Declarations
cannot independently establish ownership or authorization. No automated holdout discovery
or partition-level date filtering is claimed.

## Research hooks and limitations

Costs, fixed adverse slippage, tick/second latency and `remove_top_trades(rows, count)` are
implemented. Source-control modes stay separate from primary modes. Random-entry placebo,
timing perturbation schedules, permutation and bootstrap execution are deferred. Future
modules should accept immutable signal/ledger records and a declared seed/scenario, create
a distinct result identity, and never mutate baseline strategy parameters or data.

`replay compare` verifies two normalized M3 results and reports per-signal entry/exit/R
changes plus trade-count, net-R, PF and drawdown pairs. It distinguishes EXACT, DATA_MISMATCH,
SOURCE_MISMATCH and EXPECTED_SEMANTIC_DIFFERENCE. It is not an adapter for arbitrary legacy
reports and cannot assert historical parity. Matching source datasets and an audited legacy
ledger adapter are required before historical reproduction. See REPLAY_REPRODUCIBILITY.md.
EOF has no artificial forced liquidation except the explicit EMA source-control branch.
Full-prefix strategy evaluation and retained bar/ledger history limit long-run throughput.
No production-readiness, profitability, incremental equivalence or historical outcome claim
is made by this checkpoint.
