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

## Milestone 3 measured reference replay

Synthetic benchmark, Python 3.12.13, NumPy 2.3.5, pandas 2.2.3, shared Linux runtime.
Four fixture ticks per decision bar plus one completion tick. Elapsed time includes
tracemalloc overhead; peak is Python-tracked allocations, not process RSS or native arrays.
Each row is one measurement, not a statistical throughput guarantee.

| Strategy | 80 bars / 321 ticks (s) | 160 bars / 641 ticks (s) |
|---|---:|---:|
| EMA M15 | 3.3502 | 11.1460 |
| POC M5 | 0.3949 | 1.3005 |
| PDL M5 | 0.3969 | 1.2985 |
| Structural H1 | 0.4159 | 1.4620 |
| Supply 3R M15 | 0.6113 | 1.8676 |
| Supply 2R M15 | 0.5082 | 1.7792 |

POC/PDL under 301 bars measure warm-up only. Additional post-warm-up measurements:

| Strategy | 320 bars / 1281 ticks (s) | 400 bars / 1601 ticks (s) |
|---|---:|---:|
| POC | 6.0471 | 12.9951 |
| PDL | 5.7603 | 13.6666 |

Peak Python-tracked allocations across these tests were 0.830 to 0.941 MiB. This does not
establish bounded total memory: completed bars, signal IDs and ledger grow with the run.
Ticks are streamed in batches. Recompute-prefix work scales poorly, consistent with the
M2 concern. This reference path is suitable for correctness fixtures and small investigations;
throughput for multi-year research remains a limitation. No incremental path is implemented,
and no full-prefix/incremental equivalence claim is made. A safe optimization must compare
all decisions and state against this reference on identical prefixes, including indicator
seeds, warm-up, duplicate suppression, resampling and gap behavior. Rules were not changed
to improve benchmark time. Checkpoint resume also recomputes the consumed prefix.

Reproduce the main benchmark with:

```bash
PYTHONPATH=src python scripts/benchmark_replay.py --bars 80 160
```

To measure all variants beyond Balanced's initial warm-up use `--bars 320 400`; larger
runs intentionally cost more. The small synthetic signal path does not establish fully
warmed multi-year throughput or historical profitability.
