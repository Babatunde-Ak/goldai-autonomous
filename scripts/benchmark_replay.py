"""Synthetic full-prefix reference benchmark. Never reads historical data."""
import argparse
import json
import platform
import time
import tracemalloc

from goldai.replay import STRATEGIES
from goldai.replay.contracts import ReplayConfig
from goldai.replay.engine import StrategyReplayRunner
from goldai.replay.io import commit_sha, synthetic_ticks, tick_fingerprint
from goldai.strategies.migrated import build_strategy


def benchmark(sizes):
    rows = []
    for identity in STRATEGIES:
        seconds = build_strategy(identity).timeframe.seconds
        for count in sizes:
            factory = lambda: synthetic_ticks(count, seconds)
            cfg = ReplayConfig(identity, tick_fingerprint(factory()), "synthetic-benchmark-v1", commit_sha())
            tracemalloc.start()
            started = time.perf_counter()
            manifest, _ = StrategyReplayRunner(cfg).run(factory())
            elapsed = time.perf_counter()-started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            rows.append({"strategy":identity,"bars":count,"ticks":manifest["tick_count_processed"],
                         "elapsed_seconds":round(elapsed,4),"peak_python_mib":round(peak/1048576,3)})
    return {"classification":"SYNTHETIC_PERFORMANCE_ONLY","mode":"M2_FULL_PREFIX_REFERENCE",
            "python":platform.python_version(),"timing_includes_tracemalloc":True,"results":rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=int, nargs="+", default=[80,160])
    print(json.dumps(benchmark(parser.parse_args().bars), indent=2))
