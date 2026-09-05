from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from goldai.market import MarketTick


PARQUET_SCHEMA_VERSION = "goldai.canonical-ticks.v1"


def parquet_available() -> bool:
    return importlib.util.find_spec("pyarrow") is not None


def duckdb_available() -> bool:
    return importlib.util.find_spec("duckdb") is not None


@dataclass(frozen=True, slots=True)
class PersistenceResult:
    output_locations: tuple[str, ...]
    canonical_fingerprint: str
    tick_count: int


class ParquetTickStore:
    """Chunked, partitioned Parquet persistence with lazy optional imports."""

    def __init__(self, root: str | Path, *, chunk_size: int = 100_000) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive")
        self.root = Path(root)
        self.chunk_size = chunk_size

    @staticmethod
    def _dependencies() -> tuple[Any, Any]:
        if not parquet_available():
            raise RuntimeError('Parquet support is optional. Install with: pip install -e ".[data]"')
        import pyarrow as pa
        import pyarrow.parquet as pq

        return pa, pq

    def write_ticks(self, ticks: Iterable[MarketTick]) -> PersistenceResult:
        pa, pq = self._dependencies()
        self.root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        locations: list[str] = []
        buffers: dict[tuple[str, int, int], list[dict[str, object]]] = {}
        part_numbers: dict[tuple[str, int, int], int] = {}
        count = 0

        def flush(partition: tuple[str, int, int]) -> None:
            rows = buffers.get(partition, [])
            if not rows:
                return
            symbol, year, month = partition
            directory = self.root / symbol / f"{year:04d}" / f"{month:02d}"
            directory.mkdir(parents=True, exist_ok=True)
            part_number = part_numbers.get(partition, 0)
            destination = directory / f"ticks-{part_number:05d}.parquet"
            if destination.exists():
                raise FileExistsError(f"refusing to overwrite canonical partition: {destination}")
            table = pa.Table.from_pylist(rows)
            metadata = dict(table.schema.metadata or {})
            metadata[b"goldai_schema_version"] = PARQUET_SCHEMA_VERSION.encode()
            table = table.replace_schema_metadata(metadata)
            pq.write_table(table, destination, compression="zstd")
            locations.append(str(destination.resolve()))
            part_numbers[partition] = part_number + 1
            buffers[partition] = []

        for tick in ticks:
            canonical = tick.semantic_json()
            digest.update(canonical.encode("utf-8"))
            digest.update(b"\n")
            partition = (tick.symbol, tick.timestamp.year, tick.timestamp.month)
            row = tick.to_dict()
            row["timestamp"] = tick.timestamp
            row["flags"] = json.dumps(row["flags"], separators=(",", ":"))
            row["metadata"] = json.dumps(row["metadata"], sort_keys=True, separators=(",", ":"), default=str)
            buffers.setdefault(partition, []).append(row)
            count += 1
            if len(buffers[partition]) >= self.chunk_size:
                flush(partition)
        for partition in sorted(buffers):
            flush(partition)
        return PersistenceResult(tuple(sorted(locations)), digest.hexdigest(), count)

    def read_ticks(self, paths: Iterable[str | Path] | None = None) -> Iterator[MarketTick]:
        _, pq = self._dependencies()
        selected = sorted(Path(path) for path in paths) if paths is not None else sorted(self.root.rglob("*.parquet"))
        for path in selected:
            parquet = pq.ParquetFile(path)
            for batch in parquet.iter_batches(batch_size=self.chunk_size):
                for row in batch.to_pylist():
                    timestamp = row["timestamp"]
                    if isinstance(timestamp, str):
                        timestamp = datetime.fromisoformat(timestamp)
                    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                        timestamp = timestamp.replace(tzinfo=UTC)
                    yield MarketTick(
                        symbol=row["symbol"],
                        timestamp=timestamp,
                        bid=row["bid"],
                        ask=row["ask"],
                        last=row.get("last"),
                        bid_volume=row.get("bid_volume"),
                        ask_volume=row.get("ask_volume"),
                        last_volume=row.get("last_volume"),
                        source=row["source"],
                        sequence=row.get("sequence"),
                        flags=tuple(json.loads(row.get("flags") or "[]")),
                        metadata=json.loads(row.get("metadata") or "{}"),
                    )


class DuckDBTickQuery:
    def __init__(self, parquet_root: str | Path) -> None:
        if not duckdb_available():
            raise RuntimeError('DuckDB support is optional. Install with: pip install -e ".[data]"')
        self.parquet_root = Path(parquet_root)

    def query(self, sql: str, parameters: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
        import duckdb

        pattern = str((self.parquet_root / "**" / "*.parquet").resolve())
        connection = duckdb.connect(database=":memory:")
        try:
            connection.read_parquet(pattern, union_by_name=True).create_view("canonical_ticks")
            return connection.execute(sql, parameters).fetchall()
        finally:
            connection.close()
