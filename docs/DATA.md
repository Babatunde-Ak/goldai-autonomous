# Canonical Market Data

## Supported historical format

Milestone 1 supports HistData Generic ASCII Bid and Ask rows in `.csv`, `.txt`, or ZIP members:

```text
YYYYMMDD HHMMSSmmm,BID,ASK
YYYYMMDD HHMMSSmmm,BID,ASK,VOLUME
```

Comma and semicolon delimiters are accepted. Timestamps are interpreted as UTC. A blank optional volume remains missing. Invalid values are rejected and counted. GoldAI does not repair source rows.

## Canonical tick schema

Required fields:

- `symbol`
- `timestamp`, timezone-aware UTC
- `bid`
- `ask`
- `source`

Optional fields:

- `last`
- `bid_volume`
- `ask_volume`
- `last_volume`
- `sequence`
- `flags`
- `metadata`

Bid and Ask remain separate. The spread is `ask - bid`. Source-neutral parity ignores provenance fields but retains every market-semantic price and volume field.

## Audit workflow

```bash
python -m goldai data audit ticks.zip --symbol XAUUSD
python -m goldai data audit ticks.zip --symbol XAUUSD --extreme-spread 1.0 --json
```

The audit reports the source SHA-256, row counts, rejection reasons, duplicates across the full source, chronology violations, first and last accepted timestamps, and exact minimum, median, mean, p75, p90, p95, p99, and maximum spreads.

The extreme-spread threshold is explicit because valid thresholds depend on symbol precision, provider, and research protocol. Extreme-spread rows remain accepted with a flag. Other invalid states are rejected.

## Preparation and storage

Install optional persistence dependencies:

```bash
python -m pip install -e ".[data]"
python -m goldai data prepare ticks.zip --symbol XAUUSD --output data/canonical
```

Output layout:

```text
data/canonical/XAUUSD/2026/04/ticks-00000.parquet
data/canonical/XAUUSD/manifest.json
```

The writer consumes an iterator and flushes bounded chunks. It does not build one full-history DataFrame. Future research should query prepared Parquet rather than repeatedly decompressing the raw archive.

## Manifest and reproducibility

The JSON manifest records:

- symbol and period
- source path and SHA-256
- tick and rejection counts
- duplicate and chronology counts
- spread statistics
- canonical output locations
- canonical data fingerprint
- creation timestamp
- schema version

The source hash identifies raw bytes. The canonical fingerprint identifies accepted, source-neutral tick semantics in stream order.

## Candle policy

All boundaries use UTC. Supported timeframes are M1, M5, M15, M30, H1, H4, and D1. A candle remains unavailable until its close boundary has been observed. Missing intervals do not create synthetic candles.

## Adding a provider

1. Parse provider records in an adapter module.
2. Convert timestamps to aware UTC values.
3. Map each record into `MarketTick`.
4. Keep provider objects and credentials outside domain modules.
5. Add adapter mapping tests.
6. Run the same tick sequence through the canonical candle engine.
7. Prove source-neutral bar parity against an existing adapter.

## Current limitations

- No real XAUUSD archive ships with the repository.
- HistData archive members are processed in sorted member-name order.
- Exact audit percentiles and full-stream duplicate checks use temporary disk space.
- Parquet and DuckDB require the optional `data` dependency group.
- MetaTrader5 requires supported Windows software and is observation only.
