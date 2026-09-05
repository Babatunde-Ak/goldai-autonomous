from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from goldai.data.audit import DataAuditReport, audit_histdata
from goldai.data.histdata import HistDataAdapter
from goldai.data.manifest import DataManifest
from goldai.data.persistence import ParquetTickStore, PersistenceResult


@dataclass(frozen=True, slots=True)
class PreparationResult:
    audit: DataAuditReport
    persistence: PersistenceResult
    manifest: DataManifest
    manifest_path: Path


def prepare_histdata(
    source_path: str | Path,
    symbol: str,
    output_root: str | Path,
    *,
    extreme_spread: float | None = None,
    chunk_size: int = 100_000,
    created_at: datetime | None = None,
) -> PreparationResult:
    manifest_path = Path(output_root) / symbol.strip().upper() / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite existing manifest: {manifest_path}")
    audit = audit_histdata(source_path, symbol, extreme_spread=extreme_spread)
    adapter = HistDataAdapter(source_path, symbol, extreme_spread=extreme_spread)
    store = ParquetTickStore(output_root, chunk_size=chunk_size)
    persistence = store.write_ticks(adapter.ticks())
    if persistence.tick_count != audit.tick_count:
        raise RuntimeError("audit and persistence tick counts differ")
    root = Path(output_root).resolve()
    manifest_locations = tuple(
        Path(location).resolve().relative_to(root).as_posix()
        for location in persistence.output_locations
    )
    manifest = DataManifest.from_audit(
        audit,
        manifest_locations,
        persistence.canonical_fingerprint,
        created_at=created_at,
    )
    manifest.write(manifest_path)
    return PreparationResult(audit, persistence, manifest, manifest_path)
