from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "runs",
}
EXCLUDED_NAMES = {".env", ".coverage", "checkpoint.json"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".sqlite", ".db", ".pem", ".key", ".zip"}
EXCLUDED_RUNTIME_DATA = {"data/raw", "data/canonical", "data/bars", "data/features"}


def should_include(path: Path, root: Path, output: Path) -> bool:
    relative = path.relative_to(root)
    if path == output or any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if any(part.endswith(".egg-info") for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.name.endswith(".usage.json"):
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    relative_parent = relative.parent.as_posix()
    if any(relative_parent == item or relative_parent.startswith(f"{item}/") for item in EXCLUDED_RUNTIME_DATA):
        return path.name == ".gitkeep"
    return path.is_file()


def build_zip(root: Path, output: Path) -> int:
    root = root.resolve()
    output = output.resolve()
    files = sorted(path for path in root.rglob("*") if should_include(path, root, output))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, Path(root.name) / path.relative_to(root))
    return len(files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    count = build_zip(root, args.output)
    print(f"Created {args.output.resolve()} with {count} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
