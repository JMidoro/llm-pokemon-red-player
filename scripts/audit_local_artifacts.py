from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.repo_paths import resolve_repo_path  # noqa: E402


CAPTURE_SCHEMAS = {
    "generated_state_report_v1",
    "golden_state_expected_v1",
    "policy_state_capture_v1",
    "promotion_evidence_capture_v1",
    "skill_state_capture_v1",
}
CAPTURE_PATH_FIELDS = {
    "base_state",
    "local_state_file",
    "output_state",
    "patch_path",
    "screenshot_file",
    "source_metadata_file",
}
CATALOG_PATH_FIELDS = {"metadata_path", "screenshot_path", "state_path"}


def tracked_json_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def path_references(path: Path, record: dict[str, Any]) -> Iterator[tuple[str, str, Path]]:
    schema = record.get("schema")
    if schema in CAPTURE_SCHEMAS:
        for field in CAPTURE_PATH_FIELDS:
            value = record.get(field)
            if isinstance(value, str) and value:
                yield field, value, path
        rom = record.get("rom")
        if isinstance(rom, dict) and isinstance(rom.get("path"), str):
            yield "rom.path", rom["path"], path
    elif schema == "skill_catalog_v1":
        yield from nested_catalog_references(path, record)


def nested_catalog_references(
    metadata_path: Path, value: Any
) -> Iterator[tuple[str, str, Path]]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in CATALOG_PATH_FIELDS and isinstance(item, str) and item:
                yield key, item, metadata_path
            else:
                yield from nested_catalog_references(metadata_path, item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_catalog_references(metadata_path, item)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit ignored ROM, state, screenshot, and run-artifact references."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any referenced local artifact is missing.",
    )
    args = parser.parse_args()

    references: dict[tuple[str, str], set[str]] = {}
    for path in tracked_json_paths():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        for field, value, source in path_references(path, record):
            references.setdefault((field, value), set()).add(source.relative_to(ROOT).as_posix())

    missing: list[tuple[str, str, Path, set[str]]] = []
    for (field, value), sources in sorted(references.items()):
        resolved = resolve_repo_path(value, repo_root=ROOT)
        if not resolved.is_file():
            missing.append((field, value, resolved, sources))

    available = len(references) - len(missing)
    print(
        f"Local artifact audit: {available}/{len(references)} unique references resolve "
        f"in this checkout."
    )
    for field, value, resolved, sources in missing:
        print(f"MISSING {field}: {value}")
        print(f"  resolves to: {resolved}")
        print(f"  referenced by: {', '.join(sorted(sources))}")
    return 1 if args.strict and missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
