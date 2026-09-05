# Milestone 2 validation report

Repository: https://github.com/Babatunde-Ak/goldai-autonomous
Branch: goldai-autonomous-v1
Base checkpoint: 0c8cb3dcb2cf48ee6a072a340436d7dc7f04fa07
Author: Babatunde Akanji, 163486508+Babatunde-Ak@users.noreply.github.com
Version: 0.3.0.dev0. No AI co-author.

## Scope delivered

Five source families, six candidate variants: EMA M15; Balanced POC long; Balanced PDL short; structural H1; independent supply/demand 2R and 3R. Complete source map and fingerprints are in STRATEGY_MIGRATION_M2.md. No selected family remains SPEC_INCOMPLETE. Rejected M5 EMA/supply and future scalpers, NY ORB and ML remain disabled.

Indicators include exact recovered EMA, Wilder ATR, Chandelier, unique confirmed pivots, ADX/DI, ATR percentile, higher-timeframe EMA votes, prior-day levels and volume-profile calculations. State covers EMA break/pullback/confirmation/invalidation; POC/PDL pending retests; supply/demand zone creation/retest/expiry/consumption; canonical deduplication and checkpoint restore.

Created modules: indicators/{balanced,ema_chandelier,pivots}.py; strategies/{balanced_kernel,ema_kernel,migrated,supply_kernel,supply_types}.py. Added two M2 test modules, source parity script and strategy documentation. Extended MarketState, StrategyDecision, registry and CLI; updated version and milestone documentation. Existing M1 tests, data engine, broker guards and CI workflow remain unchanged.

## Executed validation, September 5 2026

- Python 3.12.13: 120 passed, zero failed, 88.54% line coverage. Includes the original 82 tests.
- Compilation: python -m compileall -q src, PASS.
- Doctor: PASS; broker mutation DISABLED, execution OBSERVE_ONLY, account UNKNOWN, MT5 absent and connection not tested.
- CLI status, describe and validate: PASS. Six variants import and restore; every authorization NONE.
- Synthetic source parity: PASS; exact observed counts in STRATEGY_PARITY_M2.json.
- Broker-mutation AST scan and account safety regressions: PASS within the suite.
- Historical strategy replay: NOT RUN. No new profit or portfolio metrics.
- Git whitespace validation: PASS.

The temporary test environment had expired before the final rerun. A dependency installation interruption left a truncated DuckDB binary; its size and recorded hash mismatched. Reinstalling the intact cached wheel fixed the environment, after which all 120 tests passed. No project code was changed to suppress that failure.

Reproduce with python -m pip install -e ".[dev,data]", python -m pytest, python -m compileall -q src, and python -m goldai strategies validate. The independent source comparison additionally requires the four original extracted artifacts. Local validation used NumPy 2.3.5 and pandas 2.2.3.

## Publication and limits

The authenticated Cloud Browser confirmed repository access and the M1 remote checkpoint. Codespaces reports exhausted monthly free usage or budget. Latest existing CI run 33962337610 belongs to M1: both Python 3.12 and 3.13 jobs were not started because the account is locked due to billing. This is infrastructure failure, not a code-test result. M2 remote publication and its exact commit/ZIP fingerprint are reported separately with the delivered checkpoint.

No account settings, main branch, historical checkpoints or strategy parameters were changed. Candidate recomputation retains full history and is not optimized for large replay workloads. Synthetic parity does not establish full historical equivalence. All strategies remain RESEARCH, with authorization NONE. DEMO stays disabled; REAL, FUNDED, CONTEST and UNKNOWN remain blocked.

## Next milestone, recommendation only

Milestone 3 requires separate review and approval. Scope: unified deterministic independent-strategy replay/backtest, executable Bid/Ask quote semantics, explicit source exit controls, constant-risk outcomes and reproducible manifests. Do not add portfolio allocation, broker execution, AI, Telegram or UI. Milestone 3 has not started.
