# GoldAI Autonomous V1

GoldAI Autonomous is a research-first foundation for deterministic XAUUSD and Forex strategy evaluation.

Project owner: Babatunde Akanji

## Current milestone

Version `0.4.0.dev0` adds Milestone 3 independent deterministic offline replay to the accepted Milestone 2 strategy contracts.

Historical HistData ticks and optional MetaTrader 5 observations map into the same `MarketTick` domain contract. One deterministic UTC candle engine produces completed Bid and Ask bars for M1, M5, M15, M30, H1, H4, and D1.

Five strategy families now evaluate candidates with synthetic source-parity evidence. No broker order route exists. MT5 DEMO execution remains disabled. REAL, FUNDED, CONTEST, and UNKNOWN account mutation remains blocked by policy and code.

## Installation

Python 3.12 or 3.13 is recommended.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

Install optional historical persistence support:

```bash
python -m pip install -e ".[data]"
```

Install the official MetaTrader5 dependency only on a supported Windows environment:

```bash
python -m pip install -e ".[mt5]"
```

## CLI

```bash
python -m goldai doctor
python -m goldai doctor --check-mt5
python -m goldai data audit path/to/HISTDATA.csv --symbol XAUUSD
python -m goldai data audit path/to/HISTDATA.zip --symbol XAUUSD --json
python -m goldai data prepare path/to/HISTDATA.zip --symbol XAUUSD --output data/canonical
python -m goldai data inspect data/canonical/XAUUSD/manifest.json
python -m goldai strategies status
python -m goldai strategies describe ema50_chandelier_m15_touch
python -m goldai strategies validate
```

`data audit` never modifies the source. It reports fingerprints, accepted and rejected rows, duplicates, chronology violations, timestamps, quality reasons, and exact spread percentiles. Use `--extreme-spread VALUE` to flag accepted ticks above a declared absolute spread threshold.

`data prepare` requires the optional `data` dependencies. It writes reusable Parquet partitions under `symbol/year/month`, then writes a deterministic JSON manifest containing source provenance and the canonical data fingerprint.

## Implemented

- Canonical ticks with UTC timestamps, Bid, Ask, optional Last and volumes, source sequence, flags, provenance, spread derivation, and deterministic serialization.
- Streaming HistData Generic ASCII ingestion from `.csv`, `.txt`, and `.zip` sources.
- Explicit malformed, duplicate, out-of-order, non-positive, Bid-above-Ask, and extreme-spread quality states.
- Disk-backed duplicate tracking and exact spread quantiles without retaining the full tick stream in RAM.
- Canonical completed Bid and Ask candles for M1 through D1 with no look-ahead.
- Optional chunked Parquet persistence and DuckDB queries.
- Machine-readable preparation manifests and SHA-256 fingerprints.
- Optional observe-only MT5 initialization, symbol metadata, ticks, rates, and account classification.
- Historical and synthetic MT5 parity tests using the same candle engine.
- Milestone 0 domain, strategy, risk, execution, event, storage, and safety contracts.

## Not implemented

- Portfolio routing, capital allocation, complete risk evaluation, or autonomous live paper trading.
- MT5 order creation, modification, or closure.
- Jarvis, local LLMs, Obsidian, Telegram, API, or web terminal.
- Profitability validation or production readiness.

## Data policy

Raw archives remain outside source control. GoldAI does not silently repair invalid rows. Canonical timestamps use UTC. Strategy logic will receive only completed bars. See [docs/DATA.md](docs/DATA.md), [RESEARCH_POLICY.md](RESEARCH_POLICY.md), and [SAFETY_POLICY.md](SAFETY_POLICY.md).

## Development checks

```bash
python -m pytest --cov=goldai
python -m compileall -q src
python -m goldai doctor
```

This repository is a pre-alpha engineering checkpoint. It makes no profitability claim.

## Milestone 2

Install candidate dependencies with `python -m pip install -e ".[strategies]"`, or all validation dependencies with `python -m pip install -e ".[dev,data]"`.
EMA M15, Balanced POC long, Balanced PDL short, structural H1 and independent supply/demand 2R/3R variants retain recovered source rules. All remain RESEARCH with execution authorization NONE.
See [strategy contracts](docs/STRATEGIES.md), [source map](docs/STRATEGY_MIGRATION_M2.md), and [evidence](docs/STRATEGY_EVIDENCE.md). Historical strategy replay has not been rerun in this checkpoint.

## Milestone 3 offline replay

Six independent strategy variants replay canonical Bid/Ask ticks with deterministic fills,
constant-risk accounting, MFE/MAE, grouped metrics, JSONL/optional Parquet ledgers and
fingerprinted manifests. This is a correctness reference engine, not a high-throughput
multi-year replay implementation. All historical strategy outcome parity is `NOT_RERUN`.

```bash
python -m pip install -e ".[dev,data]"
python -m goldai replay list-strategies
python -m goldai replay run --strategy ema50_chandelier_m15_touch --synthetic --output runs/ema_fixture --json
python -m goldai replay inspect runs/ema_fixture --json
python -m goldai replay compare runs/ema_fixture runs/ema_fixture --json
```

See [replay guide](docs/REPLAY_ENGINE.md), [execution semantics](docs/EXECUTION_SEMANTICS.md),
[reproducibility](docs/REPLAY_REPRODUCIBILITY.md), and [validation](docs/MILESTONE_3_VALIDATION.md).
Each run is isolated. Offline simulated trades never call broker execution adapters.
