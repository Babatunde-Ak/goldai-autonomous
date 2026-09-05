from __future__ import annotations

import json
import math
import sqlite3
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from goldai.data.histdata import HistDataAdapter
from goldai.data.quality import DataQualityStatus


@dataclass(frozen=True, slots=True)
class SpreadStatistics:
    minimum: float | None
    median: float | None
    mean: float | None
    p75: float | None
    p90: float | None
    p95: float | None
    p99: float | None
    maximum: float | None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DataAuditReport:
    symbol: str
    source_path: str
    source_sha256: str
    tick_count: int
    accepted_rows: int
    rejected_rows: int
    duplicate_ticks: int
    chronology_violations: int
    malformed_rows: int
    non_positive_prices: int
    bid_above_ask: int
    extreme_spreads: int
    first_timestamp: str | None
    last_timestamp: str | None
    spread: SpreadStatistics
    elapsed_seconds: float
    rows_per_second: float
    schema_version: str = "goldai.data-audit.v1"

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["spread"] = self.spread.to_dict()
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    def to_text(self) -> str:
        rows = (
            ("Symbol", self.symbol),
            ("Source path", self.source_path),
            ("Source SHA-256", self.source_sha256),
            ("Tick count", self.tick_count),
            ("Accepted rows", self.accepted_rows),
            ("Rejected rows", self.rejected_rows),
            ("Duplicate ticks", self.duplicate_ticks),
            ("Chronology violations", self.chronology_violations),
            ("Malformed rows", self.malformed_rows),
            ("Non-positive prices", self.non_positive_prices),
            ("Bid above Ask", self.bid_above_ask),
            ("Extreme spreads", self.extreme_spreads),
            ("First timestamp", self.first_timestamp or "NONE"),
            ("Last timestamp", self.last_timestamp or "NONE"),
            ("Minimum spread", self.spread.minimum),
            ("Median spread", self.spread.median),
            ("Mean spread", self.spread.mean),
            ("P75 spread", self.spread.p75),
            ("P90 spread", self.spread.p90),
            ("P95 spread", self.spread.p95),
            ("P99 spread", self.spread.p99),
            ("Maximum spread", self.spread.maximum),
            ("Elapsed seconds", round(self.elapsed_seconds, 6)),
            ("Rows per second", round(self.rows_per_second, 2)),
        )
        return "\n".join(f"{label:.<28} {value}" for label, value in rows)


class _DiskSpreadAccumulator:
    """Exact spread quantiles using temporary disk storage instead of tick-sized RAM."""

    def __init__(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="goldai-spreads-")
        self._connection = sqlite3.connect(Path(self._temporary.name) / "spreads.sqlite")
        self._connection.execute("CREATE TABLE spreads (value REAL NOT NULL)")
        self._buffer: list[tuple[float]] = []

    def add(self, value: float) -> None:
        self._buffer.append((value,))
        if len(self._buffer) >= 10_000:
            self._flush()

    def _flush(self) -> None:
        if self._buffer:
            self._connection.executemany("INSERT INTO spreads(value) VALUES (?)", self._buffer)
            self._connection.commit()
            self._buffer.clear()

    def _value_at(self, offset: int) -> float:
        row = self._connection.execute(
            "SELECT value FROM spreads ORDER BY value LIMIT 1 OFFSET ?", (offset,)
        ).fetchone()
        if row is None:
            raise RuntimeError("spread offset is unavailable")
        return float(row[0])

    def _percentile(self, count: int, percentile: float) -> float:
        position = (count - 1) * percentile
        lower = math.floor(position)
        upper = math.ceil(position)
        lower_value = self._value_at(lower)
        if lower == upper:
            return lower_value
        upper_value = self._value_at(upper)
        return lower_value + (upper_value - lower_value) * (position - lower)

    def statistics(self) -> SpreadStatistics:
        self._flush()
        self._connection.execute("CREATE INDEX IF NOT EXISTS spreads_value_idx ON spreads(value)")
        row = self._connection.execute(
            "SELECT COUNT(*), MIN(value), AVG(value), MAX(value) FROM spreads"
        ).fetchone()
        assert row is not None
        count = int(row[0])
        if count == 0:
            return SpreadStatistics(None, None, None, None, None, None, None, None)
        return SpreadStatistics(
            minimum=float(row[1]),
            median=self._percentile(count, 0.50),
            mean=float(row[2]),
            p75=self._percentile(count, 0.75),
            p90=self._percentile(count, 0.90),
            p95=self._percentile(count, 0.95),
            p99=self._percentile(count, 0.99),
            maximum=float(row[3]),
        )

    def close(self) -> None:
        self._connection.close()
        self._temporary.cleanup()

    def __enter__(self) -> _DiskSpreadAccumulator:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def audit_histdata(
    path: str | Path,
    symbol: str,
    *,
    extreme_spread: float | None = None,
) -> DataAuditReport:
    started = time.perf_counter()
    adapter = HistDataAdapter(path, symbol, extreme_spread=extreme_spread)
    source_sha256 = adapter.source_sha256
    counts = {status: 0 for status in DataQualityStatus}
    first: datetime | None = None
    last: datetime | None = None
    total = 0
    accepted = 0
    with _DiskSpreadAccumulator() as spreads:
        for record in adapter.records():
            total += 1
            counts[record.status] += 1
            if record.accepted and record.tick is not None:
                accepted += 1
                first = first or record.tick.timestamp
                last = record.tick.timestamp
                spreads.add(record.tick.spread)
        spread_statistics = spreads.statistics()
    if adapter.source_sha256 != source_sha256:
        raise RuntimeError("historical source changed during audit")
    elapsed = time.perf_counter() - started
    return DataAuditReport(
        symbol=adapter.symbol,
        source_path=str(adapter.path.resolve()),
        source_sha256=source_sha256,
        tick_count=accepted,
        accepted_rows=accepted,
        rejected_rows=total - accepted,
        duplicate_ticks=counts[DataQualityStatus.DUPLICATE],
        chronology_violations=counts[DataQualityStatus.OUT_OF_ORDER],
        malformed_rows=counts[DataQualityStatus.MALFORMED],
        non_positive_prices=counts[DataQualityStatus.NON_POSITIVE_PRICE],
        bid_above_ask=counts[DataQualityStatus.BID_ABOVE_ASK],
        extreme_spreads=counts[DataQualityStatus.EXTREME_SPREAD],
        first_timestamp=first.isoformat() if first else None,
        last_timestamp=last.isoformat() if last else None,
        spread=spread_statistics,
        elapsed_seconds=elapsed,
        rows_per_second=(total / elapsed) if elapsed else 0.0,
    )
