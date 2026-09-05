from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, UTC, timedelta
import hashlib
import json
from pathlib import Path
import subprocess

from goldai.data.manifest import DataManifest
from goldai.data.persistence import ParquetTickStore
from goldai.market import MarketTick
from goldai.replay.contracts import canonical, fingerprint, source_hash


def commit_sha():
    try:
        root = Path(__file__).parents[3]
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "SOURCE_ARCHIVE:" + source_hash()


def synthetic_ticks(bars=40, timeframe_seconds=900):
    """Deterministic numeric fixture, no historical prices or claimed edge."""
    start = datetime(2025, 1, 6, tzinfo=UTC)
    for i in range(bars):
        base = 2600 + (i % 12 - 6)*0.5
        for offset, price in ((0, base), (60, base+1), (120, base-1), (timeframe_seconds-1, base+0.25)):
            yield MarketTick("XAUUSD", start+timedelta(seconds=i*timeframe_seconds+offset),
                             price, price+0.2, "synthetic-m3", sequence=i*4+offset)
    yield MarketTick("XAUUSD", start+timedelta(seconds=bars*timeframe_seconds),
                     2600, 2600.2, "synthetic-m3")


def tick_fingerprint(ticks):
    h = hashlib.sha256()
    for t in ticks:
        h.update((t.semantic_json()+"\n").encode())
    return h.hexdigest()


def prepared_source(manifest_path, declaration):
    path = Path(manifest_path)
    manifest = DataManifest.read(path)
    manifest_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if declaration.get("data_manifest_sha") != manifest_sha:
        raise ValueError("data usage declaration manifest mismatch")
    if declaration.get("locked") is not False:
        raise ValueError("locked status must be explicitly false")
    if declaration.get("classification") not in {"DEVELOPMENT", "ROBUSTNESS", "EVALUATION", "PREVIOUSLY_CONSUMED"}:
        raise ValueError("historical usage must be explicitly classified")
    if declaration.get("first_tick") != manifest.first_tick or declaration.get("last_tick") != manifest.last_tick:
        raise ValueError("declared periods must exactly match the complete prepared stream")
    if manifest.symbol != "XAUUSD" or manifest.schema_version != "goldai.canonical-ticks.v1":
        raise ValueError("unsupported prepared stream")
    if manifest.chronology_anomalies:
        raise ValueError("prepare a chronological source before replay")
    if manifest.first_tick:
        first, last = datetime.fromisoformat(manifest.first_tick), datetime.fromisoformat(manifest.last_tick)
        if declaration["classification"] in {"DEVELOPMENT", "ROBUSTNESS"} and last.year >= 2026:
            raise ValueError("2026 must be evaluated separately")
        if declaration["classification"] == "EVALUATION" and first.year < 2026:
            raise ValueError("split development and evaluation datasets")
        # Designated July remains blocked without a specific consumed-evidence declaration.
        july = datetime(2026, 7, 1, tzinfo=UTC)
        august = datetime(2026, 8, 1, tzinfo=UTC)
        if first < august and last >= july:
            if declaration["classification"] != "PREVIOUSLY_CONSUMED" or not declaration.get("prior_consumption_evidence"):
                raise ValueError("July 2026 locked evidence requires documented prior consumption")
    locations = [Path(p) if Path(p).is_absolute() else path.parent.parent / p
                 for p in manifest.canonical_output_locations]
    if not locations or any(not p.is_file() for p in locations):
        raise ValueError("prepared partitions unavailable at manifest locations")

    def stream():
        count = 0
        first_seen = last_seen = None
        for tick in ParquetTickStore(path.parent).read_ticks(locations):
            count += 1
            first_seen = first_seen or tick.timestamp.isoformat()
            last_seen = tick.timestamp.isoformat()
            yield tick
        if (count, first_seen, last_seen) != (manifest.tick_count, manifest.first_tick, manifest.last_tick):
            raise ValueError("prepared counts/period mismatch")
    return manifest, manifest_sha, stream


def save_result(output, manifest, ledger, declaration, parquet=False):
    destination = Path(output)
    destination.mkdir(parents=True, exist_ok=False)
    (destination/"DATA_USAGE_DECLARATION.json").write_text(canonical(declaration)+"\n")
    (destination/"trades.jsonl").write_text("".join(canonical(r)+"\n" for r in ledger))
    (destination/"manifest.json").write_text(canonical(manifest)+"\n")
    if parquet and ledger:
        import pyarrow as pa
        import pyarrow.parquet as pq
        rows = [{**r, "intent": canonical(r["intent"]), "source_metadata": canonical(r["source_metadata"])}
                for r in ledger]
        pq.write_table(pa.Table.from_pylist(rows), destination/"trades.parquet")
    return destination


def inspect_result(path):
    path = Path(path)
    if path.is_dir():
        path = path/"manifest.json"
    manifest = json.loads(path.read_text())
    unsigned = {k:v for k,v in manifest.items() if k != "result_fingerprint"}
    if fingerprint(unsigned) != manifest.get("result_fingerprint"):
        raise ValueError("manifest fingerprint mismatch")
    ledger = [json.loads(line) for line in (path.parent/"trades.jsonl").read_text().splitlines()]
    if fingerprint(ledger) != manifest["ledger_hash"]:
        raise ValueError("ledger fingerprint mismatch")
    return manifest, ledger


def compare_results(left, right):
    a, ar = inspect_result(left)
    b, br = inspect_result(right)
    same_data = a["data_fingerprint"] == b["data_fingerprint"]
    same_source = a["strategy_id"] == b["strategy_id"] and a["strategy_spec_hash"] == b["strategy_spec_hash"]
    classification = "DATA_MISMATCH" if not same_data else "SOURCE_MISMATCH" if not same_source else (
        "EXACT" if a["result_fingerprint"] == b["result_fingerprint"] else "EXPECTED_SEMANTIC_DIFFERENCE"
        if a["exit_mode"] != b["exit_mode"] or a["cost_model"] != b["cost_model"] else "SOURCE_MISMATCH")
    by_signal = {r["signal_id"]:r for r in ar}
    differences = []
    for row in br:
        old = by_signal.pop(row["signal_id"], None)
        fields = ("signal_timestamp", "entry_timestamp", "entry_price", "exit_timestamp", "exit_price", "realized_r")
        changes = {f: [old.get(f) if old else None, row.get(f)] for f in fields
                   if old is None or old.get(f) != row.get(f)}
        if changes:
            differences.append({"signal_id":row["signal_id"], "fields":changes})
    differences.extend({"signal_id":s,"missing_in_right":True} for s in by_signal)
    return {"classification": classification, "scope":"NORMALIZED_REPLAY_RESULTS_ONLY",
            "trade_count_difference": b["closed_trades"]-a["closed_trades"],
            "net_r_difference": b["net_r"]-a["net_r"],
            "profit_factor": [a["profit_factor"],b["profit_factor"]],
            "maximum_drawdown_r": [a["maximum_drawdown_r"],b["maximum_drawdown_r"]],
            "trade_differences":differences}
