# Market Data Performance Direction

Milestone 1 prioritizes correctness and bounded memory.

Current properties:

- HistData parsing is iterator based.
- ZIP members decompress once per adapter pass.
- Audit spreads and duplicate fingerprints use temporary disk storage.
- Parquet output flushes configurable chunks.
- Prepared Parquet prevents repeated decompression during future strategy trials.
- Candle aggregation keeps one working bar per timeframe.

Future measured optimizations may evaluate:

- batching SQLite duplicate inserts
- approximate streaming quantiles for exploratory audits, never evidence audits
- PyArrow CSV parsing after behavior parity is proven
- vectorized candle preparation for offline research
- Numba for measured numeric hot paths
- partition-level parallel preparation with deterministic merge order

No optimization should change canonical serialization, rejection counts, candle boundaries, or parity results.

## Milestone 2 candidate evaluation

Candidate wrappers recompute from the full immutable prefix to preserve source warm-up and state semantics. Memory grows with bars; repeated prefix evaluation can approach quadratic total work over a long replay. Prefix hashing also scans history. This is a correctness checkpoint, not a measured high-throughput replay implementation. Incremental truncation and numeric optimization require equivalence tests.
