from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from goldai.data.audit import DataAuditReport


@dataclass(frozen=True, slots=True)
class DataManifest:
    symbol: str
    period: str
    source: str
    source_sha256: str
    tick_count: int
    first_tick: str | None
    last_tick: str | None
    rejected_rows: int
    duplicate_rows: int
    chronology_anomalies: int
    spread_statistics: dict[str, float | None]
    canonical_output_locations: tuple[str, ...]
    canonical_data_fingerprint: str
    creation_timestamp: str
    schema_version: str = "goldai.canonical-ticks.v1"

    @classmethod
    def from_audit(
        cls,
        audit: DataAuditReport,
        output_locations: tuple[str, ...],
        canonical_fingerprint: str,
        *,
        created_at: datetime | None = None,
    ) -> DataManifest:
        timestamp = (created_at or datetime.now(UTC)).astimezone(UTC)
        period = _period(audit.first_timestamp, audit.last_timestamp)
        return cls(
            symbol=audit.symbol,
            period=period,
            source=audit.source_path,
            source_sha256=audit.source_sha256,
            tick_count=audit.tick_count,
            first_tick=audit.first_timestamp,
            last_tick=audit.last_timestamp,
            rejected_rows=audit.rejected_rows,
            duplicate_rows=audit.duplicate_ticks,
            chronology_anomalies=audit.chronology_violations,
            spread_statistics=audit.spread.to_dict(),
            canonical_output_locations=tuple(sorted(output_locations)),
            canonical_data_fingerprint=canonical_fingerprint,
            creation_timestamp=timestamp.isoformat(),
        )

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["canonical_output_locations"] = list(self.canonical_output_locations)
        return value

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    def write(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_json() + "\n", encoding="utf-8")
        return destination

    @classmethod
    def read(cls, path: str | Path) -> DataManifest:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        value["canonical_output_locations"] = tuple(value["canonical_output_locations"])
        return cls(**value)


def _period(first: str | None, last: str | None) -> str:
    if first is None or last is None:
        return "EMPTY"
    return f"{first}/{last}"
