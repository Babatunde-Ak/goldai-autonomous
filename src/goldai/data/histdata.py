from __future__ import annotations

import csv
import hashlib
import io
import math
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, TextIO

from goldai.data.quality import DataQualityStatus
from goldai.market import MarketTick


SUPPORTED_SUFFIXES = {".csv", ".txt"}
TIMESTAMP_FORMATS = ("%Y%m%d %H%M%S%f", "%Y%m%d %H%M%S")


@dataclass(frozen=True, slots=True)
class TickRecord:
    row_number: int
    raw: str
    status: DataQualityStatus
    tick: MarketTick | None = None
    reason: str = ""
    source_member: str | None = None

    @property
    def accepted(self) -> bool:
        return self.tick is not None and self.status in {
            DataQualityStatus.VALID,
            DataQualityStatus.EXTREME_SPREAD,
        }


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def parse_histdata_timestamp(raw: str) -> datetime:
    value = raw.strip()
    for timestamp_format in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value, timestamp_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError(f"unsupported HistData timestamp: {raw!r}")


@contextmanager
def _decoded_stream(binary: BinaryIO) -> Iterator[TextIO]:
    wrapper = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
    try:
        yield wrapper
    finally:
        wrapper.detach()


class HistDataAdapter:
    """Stream HistData Generic ASCII Bid/Ask rows into canonical ticks."""

    def __init__(
        self,
        path: str | Path,
        symbol: str,
        *,
        extreme_spread: float | None = None,
        reject_duplicates: bool = True,
        reject_out_of_order: bool = True,
    ) -> None:
        self.path = Path(path)
        self.symbol = symbol.strip().upper()
        self.extreme_spread = extreme_spread
        self.reject_duplicates = reject_duplicates
        self.reject_out_of_order = reject_out_of_order
        if not self.path.is_file():
            raise FileNotFoundError(f"Historical source not found: {self.path}")
        if not self.symbol:
            raise ValueError("symbol must not be blank")
        if extreme_spread is not None and (not math.isfinite(extreme_spread) or extreme_spread <= 0):
            raise ValueError("extreme_spread must be positive and finite")

    @property
    def source_sha256(self) -> str:
        return sha256_file(self.path)

    def _members(self) -> Iterator[tuple[str | None, TextIO]]:
        if self.path.suffix.lower() == ".zip":
            with zipfile.ZipFile(self.path) as archive:
                members = sorted(
                    item for item in archive.infolist()
                    if not item.is_dir() and Path(item.filename).suffix.lower() in SUPPORTED_SUFFIXES
                )
                if not members:
                    raise ValueError("archive has no supported .csv or .txt members")
                for member in members:
                    with archive.open(member, "r") as binary:
                        with _decoded_stream(binary) as stream:
                            yield member.filename, stream
            return
        if self.path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported historical format: {self.path.suffix or '<none>'}")
        with self.path.open("r", encoding="utf-8-sig", newline="") as stream:
            yield None, stream

    def records(self) -> Iterator[TickRecord]:
        previous_timestamp: datetime | None = None
        global_row = 0
        with tempfile.TemporaryDirectory(prefix="goldai-duplicates-") as temporary:
            duplicate_db = sqlite3.connect(Path(temporary) / "seen.sqlite")
            try:
                duplicate_db.execute("PRAGMA journal_mode=OFF")
                duplicate_db.execute("PRAGMA synchronous=OFF")
                duplicate_db.execute("CREATE TABLE seen (fingerprint BLOB PRIMARY KEY)")
                for member_name, stream in self._members():
                    for raw_line in stream:
                        global_row += 1
                        record = self._parse_row(
                            raw_line,
                            global_row,
                            member_name,
                            previous_timestamp,
                            duplicate_db,
                        )
                        yield record
                        if record.accepted and record.tick is not None:
                            previous_timestamp = record.tick.timestamp
            finally:
                duplicate_db.close()

    def _parse_row(
        self,
        raw_line: str,
        global_row: int,
        member_name: str | None,
        previous_timestamp: datetime | None,
        duplicate_db: sqlite3.Connection,
    ) -> TickRecord:
        raw = raw_line.rstrip("\r\n")
        if not raw.strip():
            return TickRecord(global_row, raw, DataQualityStatus.MALFORMED, reason="blank row", source_member=member_name)
        try:
            delimiter = ";" if raw.count(";") > raw.count(",") else ","
            fields = next(csv.reader([raw], delimiter=delimiter))
            if len(fields) not in {3, 4}:
                raise ValueError(f"expected 3 or 4 columns, found {len(fields)}")
            timestamp = parse_histdata_timestamp(fields[0])
            bid = float(fields[1])
            ask = float(fields[2])
            volume = float(fields[3]) if len(fields) == 4 and fields[3].strip() else None
        except (ValueError, csv.Error) as exc:
            return TickRecord(global_row, raw, DataQualityStatus.MALFORMED, reason=str(exc), source_member=member_name)

        if not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0 or ask <= 0:
            return TickRecord(
                global_row,
                raw,
                DataQualityStatus.NON_POSITIVE_PRICE,
                reason="bid and ask must be positive and finite",
                source_member=member_name,
            )
        if bid > ask:
            return TickRecord(
                global_row,
                raw,
                DataQualityStatus.BID_ABOVE_ASK,
                reason="bid exceeds ask",
                source_member=member_name,
            )
        if volume is not None and (not math.isfinite(volume) or volume < 0):
            return TickRecord(
                global_row,
                raw,
                DataQualityStatus.MALFORMED,
                reason="volume must be non-negative and finite",
                source_member=member_name,
            )

        source = f"histdata:{self.path.name}"
        if member_name:
            source = f"{source}!{member_name}"
        tick = MarketTick(
            symbol=self.symbol,
            timestamp=timestamp,
            bid=bid,
            ask=ask,
            source=source,
            sequence=global_row - 1,
            last_volume=volume,
            metadata={"row_number": global_row, "source_member": member_name},
        )
        fingerprint = hashlib.sha256(tick.semantic_json().encode("utf-8")).digest()
        duplicate = duplicate_db.execute(
            "INSERT OR IGNORE INTO seen(fingerprint) VALUES (?)", (fingerprint,)
        ).rowcount == 0
        if duplicate and self.reject_duplicates:
            return TickRecord(
                global_row,
                raw,
                DataQualityStatus.DUPLICATE,
                reason="duplicate tick",
                source_member=member_name,
            )
        if previous_timestamp is not None and timestamp < previous_timestamp and self.reject_out_of_order:
            duplicate_db.execute("DELETE FROM seen WHERE fingerprint = ?", (fingerprint,))
            return TickRecord(
                global_row,
                raw,
                DataQualityStatus.OUT_OF_ORDER,
                reason="timestamp is earlier than the previous accepted tick",
                source_member=member_name,
            )

        status = DataQualityStatus.VALID
        if self.extreme_spread is not None and tick.spread > self.extreme_spread:
            status = DataQualityStatus.EXTREME_SPREAD
            tick = MarketTick(
                symbol=tick.symbol,
                timestamp=tick.timestamp,
                bid=tick.bid,
                ask=tick.ask,
                source=tick.source,
                sequence=tick.sequence,
                last_volume=tick.last_volume,
                flags=(DataQualityStatus.EXTREME_SPREAD.value,),
                metadata=tick.metadata,
            )
        return TickRecord(global_row, raw, status, tick=tick, source_member=member_name)

    def ticks(self) -> Iterator[MarketTick]:
        for record in self.records():
            if record.accepted and record.tick is not None:
                yield record.tick
