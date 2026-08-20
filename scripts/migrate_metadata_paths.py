from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.repo_paths import portable_repo_path  # noqa: E402


PORTABLE_SCHEMAS = {
    "generated_state_report_v1",
    "golden_state_expected_v1",
    "policy_state_capture_v1",
    "promotion_evidence_capture_v1",
    "skill_state_capture_v1",
}
RECURSIVE_PATH_SCHEMAS = {"skill_catalog_v1"}
RECURSIVE_PATH_FIELDS = {"metadata_path", "screenshot_path", "state_path"}
TOP_LEVEL_PATH_FIELDS = (
    "base_state",
    "local_state_file",
    "output_state",
    "patch_path",
    "screenshot_file",
    "source_metadata_file",
)


def tracked_json_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def migrate_record(record: dict[str, Any]) -> bool:
    schema = record.get("schema")
    if schema not in PORTABLE_SCHEMAS | RECURSIVE_PATH_SCHEMAS:
        return False

    changed = False
    for field in TOP_LEVEL_PATH_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value:
            portable = portable_repo_path(value, repo_root=ROOT)
            if portable != value:
                record[field] = portable
                changed = True

    rom = record.get("rom")
    if isinstance(rom, dict):
        value = rom.get("path")
        if isinstance(value, str) and value:
            portable = portable_repo_path(value, repo_root=ROOT)
            if portable != value:
                rom["path"] = portable
                changed = True
    if schema in RECURSIVE_PATH_SCHEMAS:
        changed = migrate_nested_paths(record) or changed
    return changed


def migrate_nested_paths(value: Any) -> bool:
    changed = False
    if isinstance(value, dict):
        for key, item in value.items():
            if key in RECURSIVE_PATH_FIELDS and isinstance(item, str) and item:
                portable = portable_repo_path(item, repo_root=ROOT)
                if portable != item:
                    value[key] = portable
                    changed = True
            else:
                changed = migrate_nested_paths(item) or changed
    elif isinstance(value, list):
        for item in value:
            changed = migrate_nested_paths(item) or changed
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate durable metadata paths to repository-relative identifiers."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report records needing migration without changing them.",
    )
    args = parser.parse_args()

    changed_paths: list[Path] = []
    for path in tracked_json_paths():
        try:
            original_text = path.read_text(encoding="utf-8")
            original_record = json.loads(original_text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        record = copy.deepcopy(original_record)
        if not isinstance(record, dict) or not migrate_record(record):
            continue
        changed_paths.append(path)
        if not args.check:
            path.write_text(
                render_migrated_json(original_text, original_record, record),
                encoding="utf-8",
            )

    action = "need migration" if args.check else "migrated"
    print(f"{len(changed_paths)} metadata records {action}.")
    for path in changed_paths:
        print(path.relative_to(ROOT).as_posix())
    return 1 if args.check and changed_paths else 0


def render_migrated_json(original_text: str, before: Any, after: Any) -> str:
    migrated = original_text
    for old, new in changed_strings(before, after):
        migrated = migrated.replace(json.dumps(old), json.dumps(new))
    if json.loads(migrated) != after:
        raise ValueError("Could not preserve JSON formatting while migrating path values.")
    return migrated


def changed_strings(before: Any, after: Any) -> list[tuple[str, str]]:
    changes: list[tuple[str, str]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in before.keys() & after.keys():
            changes.extend(changed_strings(before[key], after[key]))
    elif isinstance(before, list) and isinstance(after, list):
        for old, new in zip(before, after, strict=True):
            changes.extend(changed_strings(old, new))
    elif isinstance(before, str) and isinstance(after, str) and before != after:
        changes.append((before, after))
    return changes


if __name__ == "__main__":
    raise SystemExit(main())
