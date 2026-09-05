# GoldAI Autonomous V1

GoldAI Autonomous is a research-first engineering foundation for deterministic XAUUSD and Forex strategy evaluation, paper trading, and future guarded MetaTrader 5 DEMO execution.

Project owner: Babatunde Akanji

## Current milestone

Version `0.1.0-dev0` implements Milestone 0 only. It defines domain boundaries, safe configuration, a strategy registry, auditable events, storage contracts, execution interfaces, a CLI foundation, tests, and CI.

No strategy is operational. No broker order route exists. MT5 DEMO execution is explicitly disabled. REAL, FUNDED, CONTEST, and UNKNOWN account mutation is blocked by policy and code.

## Installation

Python 3.12 or 3.13 is recommended.

```bash
python -m venv .venv
```

Activate the environment, then install the project and development tools:

```bash
python -m pip install -e ".[dev]"
```

## CLI

```bash
python -m goldai doctor
python -m goldai --config config/default.json doctor
python -m goldai data audit
python -m goldai strategies status
```

`data audit` intentionally exits with a clear `NOT IMPLEMENTED` result until Milestone 1 provides the historical data core.

## Repository structure

```text
src/goldai/       Python package and domain boundaries
tests/            Automated architecture and safety tests
docs/             Supplemental design records
config/           Safe example configuration
scripts/          Development and release helpers
data/             Ignored raw, canonical, bar, and feature data
vault/            Reserved local memory directory, ignored by default
.github/workflows Continuous integration
```

## Implemented

- Canonical market models for ticks, bars, timeframes, symbol specifications, spreads, sessions, and market state.
- Deterministic strategy interface and typed decisions.
- Seven-entry research registry with no execution authorization.
- Deterministic, timestamped, serializable events.
- Fail-closed account and execution authorization.
- Paper, observe-only, and MT5 DEMO adapter boundaries.
- Typed JSON configuration with `OBSERVE_ONLY` as the safe default.
- Technology-neutral storage contracts.
- Structured JSON logging with correlation fields.
- CLI diagnostics and strategy status.
- Pytest coverage of the M0 safety and domain rules.
- Secret-free GitHub Actions CI.

## Not implemented

- Historical data importing, auditing, or replay.
- Live MT5 connectivity.
- Any trading strategy behavior.
- Portfolio routing or a complete risk engine.
- Paper fills and position accounting.
- MT5 DEMO or real-money order execution.
- Jarvis, local LLMs, Obsidian, Telegram, API, or web terminal.
- Strategy optimization, ML training, or profitability validation.

## Development workflow

1. Work on `goldai-autonomous-v1` during Milestone 0.
2. Keep `main` stable.
3. Add tests for every domain or safety change.
4. Run `python -m pytest` and `python -m compileall -q src`.
5. Never modify final holdout evidence or commit credentials.
6. Promote strategies only through a future explicit review process.

Read [ARCHITECTURE.md](ARCHITECTURE.md), [SAFETY_POLICY.md](SAFETY_POLICY.md), and [RESEARCH_POLICY.md](RESEARCH_POLICY.md) before implementing later milestones.

## Status

This repository is a pre-alpha architecture checkpoint. It is not production-ready and makes no profitability claim.

