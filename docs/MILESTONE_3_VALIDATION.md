# Milestone 3 validation report

## Checkpoint identity

Repository: https://github.com/Babatunde-Ak/goldai-autonomous
Branch: goldai-autonomous-v1
Accepted parent M2: `4b21e4d61892ffb18cf18ce9f7d7028656b1db91`
Author: Babatunde Akanji, `163486508+Babatunde-Ak@users.noreply.github.com`
Version: 0.4.0.dev0, pre-alpha offline research checkpoint.

The exact release commit and ZIP SHA are supplied in the delivery message. In a checkout,
`git log -1 --format='%H%n%P%n%an%n%ae'` retrieves the commit, parent and author without
embedding a self-referential commit hash in source. The accepted M2 parent was fetched and
verified, and its tree exactly matched the earlier local M2 tree. That local checkpoint
was preserved under `m2-local-checkpoint-e784505`. No M0/M1/M2 rewrite occurred.

## Delivered architecture and contracts

ReplayClock, StrategyReplayRunner, FillSimulator, immutable ReplayConfig/CostModel,
detailed TradeRecord, closed-trade statistics and persistence are implemented in
`src/goldai/replay`. CLI supports run, inspect, compare and list-strategies. New files also
include scripts/benchmark_replay.py, tests/test_m3_replay.py, execution semantics,
engine and reproducibility guides. Root architecture, roadmap, research/safety policies,
README, performance documentation, release exclusions, CLI and package version are updated.

All six operational M2 variants are replay-capable: EMA M15 touch, POC long, PDL short,
structural H1, supply/demand M15 3R and independent 2R. Strategy and indicator files are
byte-for-byte unchanged from accepted M2. Existing execution/risk/config code is unchanged.
No portfolio, AI, Telegram, UI, live paper execution or broker mutation was added.

Executable Bid/Ask sides, two EntryIntent types, quote latency, source-specific position
limits, stop/target gap fills, time/source exits and unresolved EOF are explicit. Primary
modes are FIXED_R, FIXED_R_RESTING_TARGET and SOURCE_CONTROL as documented in the matrix.
The optional structural fixed 3R comparison is separate from its $3/$20 accepted contract.
R accounting is constant-risk. MFE/MAE and their elapsed times derive from the actual quote
path. JSONL and optional Parquet persist all intent states; immutable result manifests
identify code, strategy, data, period, costs, counts, metrics and checksums.

## Local results

Python 3.12.13; NumPy 2.3.5; pandas 2.2.3; PyArrow 25.0.1; DuckDB 1.5.5.

| Check | Result |
|---|---|
| Full pytest suite | 172 passed, 0 failed, 7.76 seconds |
| Existing M2 tests | All 120 preserved and passing |
| Added M3 tests | 52 passing cases |
| Coverage | 90.07% (M2: 88.54%) |
| Compile all src | PASS |
| Doctor | PASS, 0.4.0.dev0, offline replay 6 variants |
| CLI run/inspect/compare/list | PASS, including JSON output |
| Prepared Parquet fixture + declaration | PASS |
| Checkpoint/resume | Exact result and ledger equality at five cursors |
| Wrong version/data/prefix/short resume | Refused as expected |
| Broker safety regression | PASS; OBSERVE_ONLY, mutation DISABLED |
| MT5 | Dependency absent; terminal connection not tested |
| Historical outcome parity | NOT_RERUN |

A damaged local DuckDB binary initially caused a process-level bus error on import.
Reinstalling the existing cached wheel repaired the environment. No source/test change
was used to hide that installation failure. Python 3.13 has not run locally; CI remains
responsible for that matrix leg when runners become available.

Synthetic tests cover causality at completion boundaries, no future quote exposure,
chronological/equal-time tick handling, long/short entry and exit sides, exact 2R/3R and
-1R fixtures, stop/target gaps, spread-induced immediate stop, entry delays, absent quotes,
unresolved EOF, structural $3/$20/time semantics, EMA source EOF, costs, duplicate signals,
position limits, ledger integrity, metrics, attribution, stress removal and data governance.
Actual M2 READY candidates for EMA, supply and structural run from canonical ticks.
Balanced source detectors retain the original M2 feature/kernel parity tests; generic
integration and performance tests do not claim fully warmed historical READY outcomes.

The independent original-source parity script was rerun successfully: EMA 31 candidates,
supply 27, POC 13, PDL 115; 16 feature prefixes; structural 72 prefixes with 2 READY cases.
Classification remains SYNTHETIC_SOURCE_PARITY_ONLY. These are not historical trade counts.

## Performance and recovery

See PERFORMANCE.md for exact synthetic measurements. EMA 80/160 decision bars took
3.3502/11.1460 seconds including tracemalloc. Balanced POC 320/400 bars took
6.0471/12.9951 seconds; PDL 5.7603/13.6666. All six variants were measured at 80/160 bars.
Full-prefix repeated evaluation scales poorly. No incremental path is implemented and
no incremental/reference equivalence is asserted. Long multi-year throughput is a known
limitation. Optimizing safely requires separate equivalence evidence; no strategy seed,
warm-up or state rule was changed for speed.

Checkpoint JSON records identity/cursor/prefix hash, strategy snapshot, ledger state,
bar count and last tick. Recovery reconstructs aggregator and metrics inputs by replaying
and verifying the consumed prefix. It is a tested deterministic recovery path, not fast
seek or direct aggregator-state restoration.

## Historical evidence and holdouts

No matching prepared historical Parquet stream was present in the project or extracted
source workspace. Original strategy source/report archives were available for contract
inspection. No real historical price periods were consumed. All generated price paths,
including fixtures with calendar-like timestamps, are synthetic. No 2021-2025 development,
2026 evaluation or locked July market evidence was replayed. No new historical returns,
PF, drawdown or profitability claims are made. Historical parity is NOT_RERUN for every
variant; Balanced's recovered source bar-based outcome filtering remains an explicit
semantic difference from exact-tick primary replay.

The engine prints/persists declared data usage before consuming selected prepared ticks.
REPLAY_ENGINE.md gives exact ingestion/replay commands and declaration fields for later
authorized data. A matching-data legacy ledger adapter is still needed to compare arbitrary
prior reports. Current compare handles only normalized M3 results and cannot certify a
legacy outcome from headline figures.

## Publication and archive verification

Cloud Browser access to the repository is authenticated. Codespaces reports exhausted
monthly free usage or budget and no existing workspace for this repository. Billing/access
settings are not changed. If Git push has no usable credentials, preserve this exact local
checkpoint and publish the full source ZIP separately. Do not recreate strategy code.

The latest observed remote M2 Actions run is 33991150728. M3 must not be labeled CI PASS
unless a workflow runs against its published SHA. Account/runner failure is distinct from
code failure. The workflow file is unchanged; it runs pytest, compilation, import and doctor
on Python 3.12/3.13 after a successful push.

Release target: `GoldAI_Autonomous_V1_Milestone_3_0.4.0-dev0.zip`.
The delivery procedure audits ZIP CRCs, exact source-file bytes and membership, absence of
credentials/raw data/runtime artifacts, then installs, imports, tests, runs doctor and
synthetic replay from the extracted ZIP. Final extraction results and SHA-256 accompany the
ZIP delivery. Source archives intentionally omit .git and record source-content identity
for replay rather than fabricating a commit. No Git bundle is required for ZIP use.

## Limitations and next review

Known limits: full-prefix speed; growing bars/ledger memory; replay-prefix recovery cost;
no historical outcome rerun; no general legacy-report adapter; no fully warmed historical
Balanced trade evidence; normalized R costs rather than broker-specific lot accounting;
no placebo/permutation execution; no broker connectivity validation on Linux.

Recommended M4 review: portfolio routing and complete risk contracts with deterministic
conflict/exposure limits, explicit independent input evidence and safety regression gates.
Separately authorize historical reproduction and any equivalence-proven performance work.
Do not infer capital allocation, autonomous paper trading, DEMO execution or AI permission.
Milestone 4 has not started and requires separate approval.
