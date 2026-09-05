from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from goldai.data import DataManifest, audit_histdata
from goldai.data.persistence import DuckDBTickQuery, ParquetTickStore, parquet_available
from goldai.data.prepare import prepare_histdata
from goldai.market import MarketTick


FIXTURE = Path(__file__).parent / "fixtures" / "histdata_sample.csv"


def _ticks() -> list[MarketTick]:
    start = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
    return [
        MarketTick("XAUUSD", start, 100.0, 100.2, "fixture", sequence=0),
        MarketTick("XAUUSD", start + timedelta(minutes=2), 101.0, 101.2, "fixture", sequence=1),
    ]


def test_manifest_serialization_is_deterministic(tmp_path: Path) -> None:
    audit = audit_histdata(FIXTURE, "XAUUSD", extreme_spread=0.5)
    created_at = datetime(2026, 2, 1, tzinfo=UTC)
    first = DataManifest.from_audit(audit, ("b.parquet", "a.parquet"), "abc", created_at=created_at)
    second = DataManifest.from_audit(audit, ("a.parquet", "b.parquet"), "abc", created_at=created_at)
    assert first.to_json() == second.to_json()
    path = first.write(tmp_path / "manifest.json")
    assert DataManifest.read(path) == first
    assert json.loads(path.read_text())["schema_version"] == "goldai.canonical-ticks.v1"


@pytest.mark.skipif(not parquet_available(), reason="optional pyarrow dependency is not installed")
def test_parquet_round_trip_and_partitioning(tmp_path: Path) -> None:
    original = _ticks()
    store = ParquetTickStore(tmp_path / "canonical", chunk_size=1)
    result = store.write_ticks(iter(original))
    restored = list(store.read_ticks(result.output_locations))
    assert result.tick_count == 2
    assert len(result.canonical_fingerprint) == 64
    assert [tick.to_dict() for tick in restored] == [tick.to_dict() for tick in original]
    assert any("XAUUSD/2026/01" in path for path in result.output_locations)
    assert any("XAUUSD/2026/02" in path for path in result.output_locations)


def test_parquet_dependency_failure_is_clear_when_unavailable(tmp_path: Path, monkeypatch) -> None:
    import goldai.data.persistence as persistence

    monkeypatch.setattr(persistence, "parquet_available", lambda: False)
    with pytest.raises(RuntimeError, match="optional"):
        ParquetTickStore(tmp_path).write_ticks(_ticks())


@pytest.mark.skipif(not parquet_available(), reason="optional data dependencies are not installed")
def test_prepare_manifest_and_duckdb_query_round_trip(tmp_path: Path) -> None:
    output = tmp_path / "canonical"
    created_at = datetime(2026, 2, 1, tzinfo=UTC)
    result = prepare_histdata(
        FIXTURE,
        "XAUUSD",
        output,
        extreme_spread=0.5,
        chunk_size=2,
        created_at=created_at,
    )
    assert result.persistence.tick_count == 4
    assert result.manifest.tick_count == 4
    assert result.manifest.creation_timestamp == "2026-02-01T00:00:00+00:00"
    assert all(not Path(location).is_absolute() for location in result.manifest.canonical_output_locations)
    query = DuckDBTickQuery(output)
    rows = query.query("SELECT COUNT(*), MIN(bid), MAX(ask) FROM canonical_ticks")
    assert rows == [(4, 2600.1, 2601.4)]
