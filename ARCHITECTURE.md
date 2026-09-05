# Architecture

## Design goals

GoldAI separates market data, strategies, risk, execution, and persistence. Domain modules do not depend on MetaTrader 5, a web framework, an LLM, PyArrow, DuckDB, or a database driver.

## Milestone 1 market-data flow

```text
HistData file or ZIP                      MetaTrader 5
        |                                      |
        v                                      v
Historical adapter                     Observe-only adapter
        |                                      |
        +----------> Canonical MarketTick <----+
                            |
                            v
                Canonical candle engine
                            |
                            v
             M1 M5 M15 M30 H1 H4 D1 bars
                            |
                            v
                 Future MarketState use
```

Both adapters map source-specific records into the same immutable type. Broker objects do not enter domain or strategy modules. Source and provenance metadata remain available for audit but do not change source-neutral market semantics.

## Canonical tick contract

`MarketTick` contains a normalized symbol, timezone-aware UTC timestamp, positive finite Bid and Ask, optional Last, optional Bid, Ask, and Last volumes, source, source sequence, flags, and metadata.

The contract rejects naive timestamps, non-positive prices, non-finite prices, Bid above Ask, negative volumes, blank symbols, and blank sources. Serialization has stable field names and JSON key ordering. Canonical fingerprints exclude adapter-specific source metadata.

## HistData boundary

The historical adapter streams Generic ASCII rows from plain text or ZIP members. It never changes the source. SHA-256 fingerprints identify the original file or archive.

Quality findings are explicit: `VALID`, `MALFORMED`, `DUPLICATE`, `OUT_OF_ORDER`, `NON_POSITIVE_PRICE`, `BID_ABOVE_ASK`, `EXTREME_SPREAD`, and `UNSUPPORTED_FORMAT`.

Temporary SQLite tables provide full-stream duplicate detection and exact spread quantiles without a tick-sized in-memory collection. Accepted tick delivery remains iterator based.

## Candle boundary

The candle engine floors timestamps against Unix epoch boundaries in UTC. It maintains only one working bar per timeframe. A bar becomes available only when a tick crosses its close boundary or an explicit observation boundary proves the period complete.

Completed bars preserve Bid OHLC, Ask OHLC, tick count, available volume, minimum spread, mean spread, maximum spread, UTC open timestamp, UTC close boundary, and `COMPLETE` status. Historical and live-style data use the same implementation.

## Historical persistence

```text
Raw archive
    |
    v
Validated canonical iterator
    |
    v
Chunked Parquet partitions
    |
    +----> symbol/year/month/ticks-NNNNN.parquet
    |
    +----> symbol/manifest.json
    |
    v
Optional DuckDB query view
```

PyArrow and DuckDB are optional dependencies. Imports remain safe when they are unavailable. Parquet metadata records the canonical schema version. The manifest records source provenance, audit counts, output locations, source fingerprint, canonical fingerprint, and creation time.

## MT5 observe boundary

The MT5 adapter imports the official package lazily. It can initialize a terminal, confirm symbol availability, read symbol specifications, map current and historical ticks, read rates, and classify the observed account as DEMO, REAL, CONTEST, or UNKNOWN.

The adapter contains no broker mutation method. MetaTrader5 is optional because Linux, CI, Termux, and offline research environments may not provide it.

## Strategy boundary

A strategy receives `MarketState` and returns `StrategyDecision`. It cannot execute an order. Milestone 2 adds a completed immutable history prefix to MarketState and source-derived candidate wrappers. Pure numeric kernels depend only on optional NumPy/pandas and domain data. EntryIntent records future executable-quote geometry without a fill. Prefix hashes and deterministic signal IDs protect history integrity and duplicate suppression. See docs/STRATEGIES.md.

## Risk and execution boundary

The required downstream order remains:

```text
Strategy -> Portfolio Router -> Risk Engine -> Execution Authorization -> Adapter
```

Milestone 2 keeps fail-closed authorization. MT5 DEMO execution remains disabled. REAL, FUNDED, CONTEST, and UNKNOWN account types remain blocked.

## Dependency rule

Dependencies point inward. Source adapters depend on canonical domain types. Canonical domain types do not depend on adapters. Persistence, broker, notifications, AI, and UI integrations stay outside deterministic strategy logic.
