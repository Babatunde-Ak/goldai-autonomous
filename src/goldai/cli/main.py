from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from goldai import __version__
from goldai.config import load_config
from goldai.strategies import default_registry


def _doctor(config_path: str | None) -> int:
    try:
        config = load_config(config_path)
        config_status = "PASS"
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Configuration ............ FAIL ({exc})")
        return 2

    registry = default_registry()
    rows = (
        ("Configuration", config_status),
        ("Package", f"PASS ({__version__})"),
        ("Historical data", "NOT CONFIGURED"),
        ("Tick chronology", "NOT CHECKED"),
        ("Bid/Ask integrity", "NOT CHECKED"),
        ("Strategy registry", f"PASS ({len(registry.all())} scaffolded)"),
        ("Risk engine", "SCAFFOLDED"),
        ("MT5 connection", "DISABLED"),
        ("Account type", "UNKNOWN"),
        ("Jarvis", "DISABLED"),
        ("Execution", config.execution_mode.value),
    )
    print("GoldAI Core\n")
    for label, status in rows:
        print(f"{label:.<27} {status}")
    return 0


def _data_audit() -> int:
    print("NOT IMPLEMENTED: historical data auditing begins in Milestone 1")
    return 3


def _strategies_status() -> int:
    print("Strategy ID | Version | Timeframe | Status | Authorization | Research")
    for record in default_registry().all():
        print(
            f"{record.strategy_id} | {record.version} | {record.timeframe.value} | "
            f"{record.status.value} | {record.execution_authorization.value} | {record.research_status}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="goldai", description="GoldAI Autonomous research foundation")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help="Path to a JSON configuration file")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report safety and component readiness")
    data = commands.add_parser("data", help="Historical market-data commands")
    data.add_subparsers(dest="data_command", required=True).add_parser("audit", help="Audit data integrity")
    strategies = commands.add_parser("strategies", help="Strategy registry commands")
    strategies.add_subparsers(dest="strategies_command", required=True).add_parser("status", help="List strategy status")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor(args.config)
    if args.command == "data" and args.data_command == "audit":
        return _data_audit()
    if args.command == "strategies" and args.strategies_command == "status":
        return _strategies_status()
    print("NOT IMPLEMENTED", file=sys.stderr)
    return 3

