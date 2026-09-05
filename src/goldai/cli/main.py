from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from goldai import __version__
from goldai.config import load_config
from goldai.data import DataManifest, audit_histdata, prepare_histdata
from goldai.data.persistence import duckdb_available, parquet_available
from goldai.mt5 import MT5DependencyStatus, MT5ObserveMarketDataAdapter
from goldai.strategies import default_registry


def _doctor(config_path: str | None, check_mt5: bool = False) -> int:
    try:
        config = load_config(config_path)
        config_status = "PASS"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Configuration ............ FAIL ({exc})")
        return 2

    registry = default_registry()
    mt5_status = MT5ObserveMarketDataAdapter.dependency_status()
    mt5_connection = "NOT TESTED"
    account_type = "UNKNOWN"
    result = 0
    if check_mt5:
        if mt5_status is MT5DependencyStatus.NOT_INSTALLED:
            mt5_connection = "NOT TESTED (dependency not installed)"
            result = 3
        else:
            adapter = MT5ObserveMarketDataAdapter()
            try:
                adapter.initialize()
                mt5_connection = "PASS (observe-only)"
                account_type = adapter.account_classification().value
            except (ConnectionError, RuntimeError) as exc:
                mt5_connection = f"FAIL ({exc})"
                result = 2
            finally:
                adapter.shutdown()

    rows = (
        ("Configuration", config_status),
        ("Package", f"PASS ({__version__})"),
        ("Historical data", "SUPPORTED (HistData stream)"),
        ("Parquet support", "AVAILABLE" if parquet_available() else "OPTIONAL / NOT INSTALLED"),
        ("DuckDB support", "AVAILABLE" if duckdb_available() else "OPTIONAL / NOT INSTALLED"),
        ("MT5 dependency", mt5_status.value.replace("_", " ")),
        ("MT5 connection", mt5_connection),
        ("Account type", account_type),
        ("Strategy registry", f"PASS ({len(registry.all())} scaffolded)"),
        ("Risk engine", "SCAFFOLDED / FAIL-CLOSED"),
        ("Broker mutation", "DISABLED"),
        ("Jarvis", "DISABLED"),
        ("Execution", config.execution_mode.value),
    )
    print("GoldAI Core\n")
    for label, status in rows:
        print(f"{label:.<27} {status}")
    return result


def _data_audit(args: argparse.Namespace) -> int:
    if args.path is None:
        print("NOT IMPLEMENTED WITHOUT INPUT: provide a HistData file or ZIP path")
        return 3
    try:
        report = audit_histdata(args.path, args.symbol, extreme_spread=args.extreme_spread)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"DATA AUDIT FAILED: {exc}", file=sys.stderr)
        return 2
    print(report.to_json() if args.json else report.to_text())
    return 1 if report.rejected_rows else 0


def _data_prepare(args: argparse.Namespace) -> int:
    try:
        result = prepare_histdata(
            args.path,
            args.symbol,
            args.output,
            extreme_spread=args.extreme_spread,
            chunk_size=args.chunk_size,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"DATA PREPARATION FAILED: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(result.manifest.to_json())
    else:
        print(result.audit.to_text())
        print(f"Manifest.................... {result.manifest_path.resolve()}")
        print(f"Canonical fingerprint....... {result.persistence.canonical_fingerprint}")
    return 1 if result.audit.rejected_rows else 0


def _data_inspect(args: argparse.Namespace) -> int:
    try:
        manifest = DataManifest.read(args.manifest)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"DATA INSPECTION FAILED: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(manifest.to_json())
    else:
        value = manifest.to_dict()
        for key in sorted(value):
            print(f"{key:.<32} {value[key]}")
    return 0


def _strategies_status() -> int:
    print("Strategy ID | Version | Timeframe | Status | Authorization | Research")
    for record in default_registry().all():
        print(
            f"{record.strategy_id} | {record.version} | {record.timeframe.value} | "
            f"{record.status.value} | {record.execution_authorization.value} | {record.research_status}"
        )
    return 0


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("path", nargs="?", type=Path, help="HistData .csv, .txt, or .zip source")
    parser.add_argument("--symbol", default="XAUUSD", help="Canonical symbol name")
    parser.add_argument("--extreme-spread", type=float, help="Flag accepted ticks above this absolute spread")
    parser.add_argument("--json", action="store_true", help="Write deterministic JSON output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="goldai", description="GoldAI Autonomous research foundation")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="Path to a JSON configuration file")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Report safety and component readiness")
    doctor.add_argument("--check-mt5", action="store_true", help="Attempt an observe-only MT5 connection")

    data = commands.add_parser("data", help="Canonical historical market-data commands")
    data_commands = data.add_subparsers(dest="data_command", required=True)
    audit = data_commands.add_parser("audit", help="Audit HistData integrity without modifying the source")
    _add_source_arguments(audit)
    prepare = data_commands.add_parser("prepare", help="Write validated canonical Parquet partitions")
    _add_source_arguments(prepare)
    prepare.add_argument("--output", type=Path, default=Path("data/canonical"))
    prepare.add_argument("--chunk-size", type=int, default=100_000)
    inspect_command = data_commands.add_parser("inspect", help="Inspect a prepared-data manifest")
    inspect_command.add_argument("manifest", type=Path)
    inspect_command.add_argument("--json", action="store_true")

    strategies = commands.add_parser("strategies", help="Strategy registry commands")
    strategies.add_subparsers(dest="strategies_command", required=True).add_parser("status", help="List strategy status")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor(args.config, args.check_mt5)
    if args.command == "data" and args.data_command == "audit":
        return _data_audit(args)
    if args.command == "data" and args.data_command == "prepare":
        if args.path is None:
            print("DATA PREPARATION FAILED: source path is required", file=sys.stderr)
            return 2
        return _data_prepare(args)
    if args.command == "data" and args.data_command == "inspect":
        return _data_inspect(args)
    if args.command == "strategies" and args.strategies_command == "status":
        return _strategies_status()
    print("NOT IMPLEMENTED", file=sys.stderr)
    return 3
