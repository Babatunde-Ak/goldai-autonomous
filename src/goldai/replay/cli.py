from dataclasses import asdict
import json
import sys
from pathlib import Path

from goldai.replay import STRATEGIES
from goldai.replay.contracts import CostModel, ReplayConfig, canonical, fingerprint
from goldai.replay.engine import StrategyReplayRunner
from goldai.replay.io import (commit_sha, synthetic_ticks, tick_fingerprint, prepared_source,
                              save_result, inspect_result, compare_results)


def add_commands(commands):
    p = commands.add_parser("replay", help="Offline deterministic per-strategy research")
    sub = p.add_subparsers(dest="replay_command", required=True)
    sub.add_parser("list-strategies")
    run = sub.add_parser("run")
    run.add_argument("--strategy", required=True, choices=STRATEGIES)
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--data", type=Path, help="M1 prepared manifest.json")
    source.add_argument("--synthetic", action="store_true")
    run.add_argument("--usage", type=Path, help="Explicit DATA_USAGE_DECLARATION JSON")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--exit-mode", choices=("ACCEPTED","FIXED_R","SOURCE_CONTROL"), default="ACCEPTED")
    run.add_argument("--commission-r", type=float, default=0)
    run.add_argument("--swap-r-per-day", type=float, default=0)
    run.add_argument("--slippage", type=float, default=0)
    run.add_argument("--delay-ticks", type=int, default=0)
    run.add_argument("--delay-seconds", type=float, default=0)
    run.add_argument("--resume", type=Path)
    run.add_argument("--checkpoint-at", type=int)
    run.add_argument("--checkpoint-output", type=Path)
    run.add_argument("--parquet", action="store_true")
    run.add_argument("--json", action="store_true")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--json", action="store_true")
    compare = sub.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    compare.add_argument("--json", action="store_true")


def execute(args):
    if args.replay_command == "list-strategies":
        print("\n".join(STRATEGIES))
        return 0
    if args.replay_command == "inspect":
        print(canonical(inspect_result(args.path)[0]))
        return 0
    if args.replay_command == "compare":
        print(canonical(compare_results(args.left, args.right)))
        return 0
    if args.output.exists():
        raise FileExistsError("refusing to overwrite a replay result")
    if args.synthetic:
        factory = synthetic_ticks
        data_hash = tick_fingerprint(factory())
        declaration = {"classification":"SYNTHETIC","locked":False,"fixture":"m3-v1",
                       "data_fingerprint":data_hash,"period":"2025-01-06 synthetic timestamps"}
        manifest_sha = fingerprint(declaration)
    else:
        if not args.usage:
            raise ValueError("real replay requires --usage DATA_USAGE_DECLARATION.json")
        declaration = json.loads(args.usage.read_text())
        manifest, manifest_sha, factory = prepared_source(args.data, declaration)
        data_hash = manifest.canonical_data_fingerprint
    config = ReplayConfig(args.strategy, data_hash, manifest_sha, commit_sha(),
        declaration["classification"], args.exit_mode,
        CostModel(args.commission_r, args.swap_r_per_day, args.slippage, args.delay_ticks, args.delay_seconds))
    # Persist the declaration before consuming the selected price stream.
    declaration_path = args.output.parent/(args.output.name+".usage.json")
    declaration_path.parent.mkdir(parents=True, exist_ok=True)
    with declaration_path.open("x") as f:
        f.write(canonical(declaration)+"\n")
    print("DATA_USAGE_DECLARATION "+canonical(declaration), file=sys.stderr if args.json else sys.stdout)
    runner = StrategyReplayRunner(config)
    if args.checkpoint_at is not None:
        if args.checkpoint_at < 1 or not args.checkpoint_output or args.resume:
            raise ValueError("checkpoint needs positive tick count, output path and no resume")
        for index, tick in enumerate(factory(), 1):
            runner.push(tick)
            if index == args.checkpoint_at:
                with args.checkpoint_output.open("x") as f:
                    f.write(canonical(runner.checkpoint())+"\n")
                print("CHECKPOINT_SAVED")
                return 0
        raise ValueError("checkpoint count exceeds input")
    checkpoint = json.loads(args.resume.read_text()) if args.resume else None
    manifest, ledger = runner.run(factory(), checkpoint=checkpoint)
    save_result(args.output, manifest, ledger, declaration, args.parquet)
    print(canonical(manifest))
    return 0
