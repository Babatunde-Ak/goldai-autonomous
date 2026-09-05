from __future__ import annotations

import json
from pathlib import Path

from goldai.cli.main import main
from goldai.data import DataManifest, audit_histdata


FIXTURE = Path(__file__).parent / "fixtures" / "histdata_sample.csv"
SOURCE_ROOT = Path(__file__).parents[1] / "src"


def test_data_audit_cli_supports_json(capsys) -> None:
    result = main(["data", "audit", str(FIXTURE), "--symbol", "XAUUSD", "--extreme-spread", "0.5", "--json"])
    value = json.loads(capsys.readouterr().out)
    assert result == 1
    assert value["accepted_rows"] == 4
    assert value["rejected_rows"] == 5


def test_data_audit_cli_returns_success_for_clean_input(tmp_path: Path, capsys) -> None:
    source = tmp_path / "clean.csv"
    source.write_text("20260102 100000000,2600.1,2600.2\n")
    assert main(["data", "audit", str(source), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["tick_count"] == 1


def test_doctor_reports_optional_components_and_broker_mutation(capsys) -> None:
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "Parquet support" in output
    assert "DuckDB support" in output
    assert "MT5 dependency" in output
    assert "Broker mutation" in output
    assert "DISABLED" in output
    assert "OBSERVE_ONLY" in output


def test_source_contains_no_broker_mutation_call() -> None:
    forbidden = "order" + "_send"
    python_source = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE_ROOT.rglob("*.py"))
    assert forbidden not in python_source


def test_no_secret_files_are_tracked() -> None:
    repository = Path(__file__).parents[1]
    forbidden_names = {".env", "id_rsa", "id_ed25519"}
    assert not any(path.name in forbidden_names for path in repository.rglob("*"))


def test_data_inspect_cli_reads_manifest(tmp_path: Path, capsys) -> None:
    report = audit_histdata(FIXTURE, "XAUUSD", extreme_spread=0.5)
    manifest = DataManifest.from_audit(report, ("XAUUSD/2026/01/ticks.parquet",), "abc")
    path = manifest.write(tmp_path / "manifest.json")
    assert main(["data", "inspect", str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["canonical_data_fingerprint"] == "abc"


def test_data_prepare_cli_writes_parquet_and_manifest(tmp_path: Path, capsys) -> None:
    output = tmp_path / "canonical"
    result = main(
        [
            "data",
            "prepare",
            str(FIXTURE),
            "--symbol",
            "XAUUSD",
            "--extreme-spread",
            "0.5",
            "--output",
            str(output),
            "--chunk-size",
            "2",
            "--json",
        ]
    )
    manifest = json.loads(capsys.readouterr().out)
    assert result == 1
    assert manifest["tick_count"] == 4
    assert (output / "XAUUSD" / "manifest.json").is_file()
    assert list(output.rglob("*.parquet"))


def test_doctor_check_mt5_reports_unavailable_dependency(monkeypatch, capsys) -> None:
    from goldai.mt5 import MT5DependencyStatus, MT5ObserveMarketDataAdapter

    monkeypatch.setattr(
        MT5ObserveMarketDataAdapter,
        "dependency_status",
        staticmethod(lambda: MT5DependencyStatus.NOT_INSTALLED),
    )
    assert main(["doctor", "--check-mt5"]) == 3
    assert "dependency not installed" in capsys.readouterr().out
