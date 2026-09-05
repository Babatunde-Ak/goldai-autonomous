# Architecture Decisions

## ADR-001: Standard-library M0 core

Milestone 0 uses dataclasses, enums, protocols, argparse, and JSON. This keeps runtime dependencies empty and reduces coupling before data and adapter requirements are proven.

## ADR-002: OBSERVE_ONLY default

Default configuration is `OBSERVE_ONLY`. M0 rejects `DEMO` configuration and includes a disabled DEMO adapter. This makes unsafe activation require future code and review rather than a single setting change.

## ADR-003: Deterministic event identifiers

Event IDs derive from canonical event content. Identical replay input produces identical IDs, supporting deduplication and reproducibility.

## ADR-004: Parquet and DuckDB direction

Historical bulk data should use Parquet schemas queryable by DuckDB. Operational metadata can begin in SQLite behind the storage contract.

## ADR-005: One source-neutral tick and candle path

HistData and MT5 observations map into `MarketTick`. The canonical candle engine consumes only that type. Source metadata remains available for provenance but is excluded from source-neutral parity comparisons and canonical fingerprints.

## ADR-006: Disk-backed audit statistics

Data audit stores temporary spread observations and duplicate fingerprints on disk. This produces exact spread percentiles and non-adjacent duplicate detection without retaining the full tick stream in RAM.

## ADR-007: Optional market-data dependencies

PyArrow, DuckDB, and MetaTrader5 load only inside their adapters. Core imports and HistData audits work without them. Linux and Termux environments do not require MetaTrader5.
