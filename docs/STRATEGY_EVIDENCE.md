# Milestone 2 evidence

Classification: SYNTHETIC_SOURCE_PARITY_ONLY. No historical replay, fills, P&L, parameter search or holdout evaluation ran in GoldAI M2.

The archive fingerprints and exact source modules are in STRATEGY_MIGRATION_M2.md. Five source families were recoverable. No selected family remains SPEC_INCOMPLETE. Internal implementations were recovered for Balanced POC/PDL; they are not claimed to reproduce proprietary public strategy code.

## Reproduced checks

The independent script scripts/verify_m2_source_parity.py loads selected pure definitions from the original artifacts. It excludes old broker and simulation entry points. Run it with `--sources /path/to/m2-sources` using the extracted source directory arrangement documented in that script. Original archives are intentionally not bundled.

Eight seeded 800-bar synthetic fixtures produced identical EMA audit/frame results, supply/demand signals and active zone states, and POC/PDL signals on the source-eligible prefix. Balanced feature columns matched the original feature builder exactly, with 16 causal prefix checks. Structural checks compared 72 prefixes and two directional READY cases against the original detector. The machine-readable result is STRATEGY_PARITY_M2.json.

Unit tests independently exercise canonical adapters, indicators, warm-up, long/short geometry, strict boundaries, duplicate suppression, reset/restore, ordered completed inputs, registry/CLI and forbidden broker calls. Controlled feature fixtures isolate POC/PDL rule behavior; they are not realistic price performance samples.

## Original reports, reference only

| Family | Original report evidence | Limitation |
|---|---|---|
| EMA M15 | PRODUCTION_ACCEPTANCE.md: 30 trades, +16.585R, PF 2.171 | Old engine replay; not rerun here |
| Balanced POC + PDL | FINE_TUNE_RESEARCH.md: combined 67 resolved trades, +49R, PF 2.289 | Post-selection development; not independent per-family evidence |
| Structural H1 | RELEASE_0.8.6_SYMBOL_SPECIFIC_PRODUCT_ACCEPTANCE.md: pooled April-June 18 trades, PF 1.441 | Source product metric; no new constant-risk validation |
| Supply/demand M15 3R | SUPPLY_DEMAND_V1_COMBINED_REPORT.md: 8 trades, +3.984R, PF 1.794 | Small selected research sample; no promotion |

Old M5 EMA and M5 supply/demand rejection remains part of the catalog. Recovered source evidence does not authorize them. Future scalpers, NY ORB and ML gates remain placeholders. No strategy has been promoted to SHADOW, PAPER or DEMO.

## Remaining evidence gap

Synthetic equivalence does not establish full historical equivalence or profitability. Milestone 3 should implement a unified deterministic replay/backtest boundary, exact executable Bid/Ask semantics, independent per-strategy outcomes, explicit source exit controls and reproducible manifests. It requires separate approval. Portfolio allocation, execution, AI and UI remain outside that milestone recommendation.
