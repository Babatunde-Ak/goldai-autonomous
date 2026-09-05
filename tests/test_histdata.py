from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from goldai.data import DataQualityStatus, HistDataAdapter, audit_histdata


FIXTURE = Path(__file__).parent / "fixtures" / "histdata_sample.csv"


def test_histdata_stream_maps_valid_rows_and_quality_states() -> None:
    records = list(HistDataAdapter(FIXTURE, "xauusd", extreme_spread=0.5).records())
    assert len(records) == 9
    assert [record.status for record in records] == [
        DataQualityStatus.VALID,
        DataQualityStatus.VALID,
        DataQualityStatus.DUPLICATE,
        DataQualityStatus.MALFORMED,
        DataQualityStatus.NON_POSITIVE_PRICE,
        DataQualityStatus.BID_ABOVE_ASK,
        DataQualityStatus.OUT_OF_ORDER,
        DataQualityStatus.EXTREME_SPREAD,
        DataQualityStatus.VALID,
    ]
    ticks = list(HistDataAdapter(FIXTURE, "xauusd", extreme_spread=0.5).ticks())
    assert len(ticks) == 4
    assert ticks[0].symbol == "XAUUSD"
    assert ticks[0].timestamp.isoformat() == "2026-01-02T10:00:00+00:00"
    assert ticks[0].last_volume == 1.0
    assert ticks[2].flags == ("EXTREME_SPREAD",)


def test_histdata_source_fingerprint_matches_original_bytes() -> None:
    expected = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert HistDataAdapter(FIXTURE, "XAUUSD").source_sha256 == expected


def test_histdata_zip_is_streamed_without_changing_source(tmp_path: Path) -> None:
    archive = tmp_path / "ticks.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.write(FIXTURE, "DAT_ASCII_XAUUSD_T_202601.csv")
    before = hashlib.sha256(archive.read_bytes()).hexdigest()
    ticks = list(HistDataAdapter(archive, "XAUUSD").ticks())
    after = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert len(ticks) == 4
    assert before == after
    assert "!DAT_ASCII_XAUUSD_T_202601.csv" in ticks[0].source


def test_histdata_unsupported_format_fails_explicitly(tmp_path: Path) -> None:
    path = tmp_path / "ticks.bin"
    path.write_bytes(b"not supported")
    adapter = HistDataAdapter(path, "XAUUSD")
    try:
        list(adapter.records())
    except ValueError as exc:
        assert "unsupported historical format" in str(exc)
    else:
        raise AssertionError("unsupported input did not fail")


def test_data_audit_reports_counts_and_exact_spread_quantiles() -> None:
    report = audit_histdata(FIXTURE, "XAUUSD", extreme_spread=0.5)
    assert report.accepted_rows == 4
    assert report.rejected_rows == 5
    assert report.duplicate_ticks == 1
    assert report.chronology_violations == 1
    assert report.malformed_rows == 1
    assert report.non_positive_prices == 1
    assert report.bid_above_ask == 1
    assert report.extreme_spreads == 1
    assert report.first_timestamp == "2026-01-02T10:00:00+00:00"
    assert report.last_timestamp == "2026-01-02T10:05:00+00:00"
    assert report.spread.minimum is not None
    assert report.spread.maximum is not None
    assert report.spread.maximum > 0.99
    assert report.tick_count == 4
    assert "Source SHA-256" in report.to_text()


def test_duplicate_detection_covers_non_adjacent_rows(tmp_path: Path) -> None:
    source = tmp_path / "duplicates.csv"
    source.write_text(
        "20260102 100000000,2600.1,2600.2\n"
        "20260102 100001000,2600.2,2600.3\n"
        "20260102 100000000,2600.1,2600.2\n"
    )
    statuses = [record.status for record in HistDataAdapter(source, "XAUUSD").records()]
    assert statuses == [DataQualityStatus.VALID, DataQualityStatus.VALID, DataQualityStatus.DUPLICATE]
