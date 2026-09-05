# Replay reproducibility

Run identity hashes immutable configuration, engine/source identity, strategy/indicator
source hash and numerical dependency versions. Use pinned NumPy 2.3.5 and pandas 2.2.3.
Prepared data is verified against M1's source-neutral semantic SHA-256. Input order matters,
including duplicate timestamps. No random number generator or system clock affects fills.
A changed dataset, cost scenario, strategy version or code identity produces a distinct run.
Python/platform differences are not claimed bit-for-bit equivalent until separately tested.

A Git checkout records its HEAD SHA plus a hash of all package Python files, so uncommitted
code changes remain distinguishable. An installed/extracted source ZIP without Git records
`SOURCE_ARCHIVE:<content hash>` instead of inventing a commit SHA. Thus archive-vs-checkout
run IDs differ intentionally; identical archive inputs and identical dependency versions
remain reproducible. The delivered release SHA and ZIP hash are reported separately.

```bash
python -m goldai replay run --strategy ema50_chandelier_m15_touch --synthetic --output runs/full --json
python -m goldai replay run --strategy ema50_chandelier_m15_touch --synthetic --output runs/partial --checkpoint-at 30 --checkpoint-output checkpoint.json
python -m goldai replay run --strategy ema50_chandelier_m15_touch --synthetic --output runs/resumed --resume checkpoint.json --json
python -m goldai replay compare runs/full runs/resumed --json
```

Expected normalized comparison: EXACT. Different output paths do not change identity.
The checkpoint is JSON, not executable pickle. It records cursor, chained complete tick
identity, strategy snapshot, ledger/open-position state, completed bar count, last tick,
code/data identity and a checksum. Resume replays the original stream from its beginning,
reconstructing aggregator, pending/open positions and metric inputs. At the checkpoint
cursor the complete checkpoint must match before processing the rest. Wrong data, changed
strategy/engine/code, corrupt checkpoint, changed input prefix and a too-short source are
refused. This tested recovery path preserves correctness but does not save prefix CPU time.
It is not a claim of direct serialized aggregator restore or random-access fast resume.

`inspect` verifies result and JSONL ledger hashes; it detects accidental modification but
provides no cryptographic signature against a party rewriting both data and hashes. Keep
original prepared manifests, declarations and release identity with research records.
Outputs refuse overwrite. Optional Parquet is an analysis projection; JSONL is authoritative
for ledger verification. Result paths and wall-clock durations do not affect fingerprints.

Comparison is limited to normalized replay outputs. EXACT requires identical result hashes.
DATA_MISMATCH takes precedence over source mismatch. Declared exit/cost changes are labeled
EXPECTED_SEMANTIC_DIFFERENCE, not proof that either model matches a historical source. Any
unexplained difference remains SOURCE_MISMATCH for investigation. No tolerance-based
historical acceptance has been implemented or claimed. All historical outcome parity
remains NOT_RERUN in M3; M2 source detector parity remains independently verified.
