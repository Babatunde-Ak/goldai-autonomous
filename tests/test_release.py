from pathlib import Path

from scripts.create_release_zip import should_include


def test_release_excludes_runtime_data_and_preserves_placeholders(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    output = tmp_path / "release.zip"
    assert should_include(root / "data" / "raw" / ".gitkeep", root, output)
    assert not should_include(root / "data" / "raw" / "private-ticks.csv", root, output)
    assert not should_include(root / "data" / "canonical" / "prepared.parquet", root, output)


def test_release_excludes_secrets_and_virtual_environments(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    output = tmp_path / "release.zip"
    assert not should_include(root / ".env", root, output)
    assert not should_include(root / ".venv" / "pyvenv.cfg", root, output)
    assert should_include(root / ".env.example", root, output)
