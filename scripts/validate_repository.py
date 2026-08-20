from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.repo_paths import REPO_ANCHORS, WINDOWS_ABSOLUTE_RE  # noqa: E402


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
TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
USER_HOME_RE = re.compile(
    r"(?i)(?:[A-Za-z]:[\\/]" r"Users[\\/][^\\/\s\"']+[\\/]"
    r"|/" r"Users/[^/\s\"']+/|/" r"home/[^/\s\"']+/)"
)
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk-proj|sk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def tracked_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def validate_portable_path(path: Path, field: str, value: Any) -> list[str]:
    if value is None and field == "screenshot_file":
        return []
    if not isinstance(value, str) or not value:
        return [f"{path.relative_to(ROOT)}: {field} must be a non-empty string"]
    if "\\" in value:
        return [f"{path.relative_to(ROOT)}: {field} must use forward slashes: {value}"]
    pure = PurePosixPath(value)
    if pure.is_absolute() or WINDOWS_ABSOLUTE_RE.match(value) or ".." in pure.parts:
        return [f"{path.relative_to(ROOT)}: {field} must be repository-relative: {value}"]
    if not pure.parts or pure.parts[0].casefold() not in REPO_ANCHORS:
        return [f"{path.relative_to(ROOT)}: {field} lacks a repository anchor: {value}"]
    return []


def validate_metadata(path: Path, record: dict[str, Any]) -> list[str]:
    schema = record.get("schema")
    if schema not in PORTABLE_SCHEMAS | RECURSIVE_PATH_SCHEMAS:
        return []
    issues: list[str] = []
    for field in TOP_LEVEL_PATH_FIELDS:
        if field in record:
            issues.extend(validate_portable_path(path, field, record[field]))
    rom = record.get("rom")
    if isinstance(rom, dict) and "path" in rom:
        issues.extend(validate_portable_path(path, "rom.path", rom["path"]))
    if schema in RECURSIVE_PATH_SCHEMAS:
        issues.extend(validate_nested_paths(path, record))
    return issues


def validate_nested_paths(path: Path, value: Any) -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in RECURSIVE_PATH_FIELDS:
                issues.extend(validate_portable_path(path, key, item))
            else:
                issues.extend(validate_nested_paths(path, item))
    elif isinstance(value, list):
        for item in value:
            issues.extend(validate_nested_paths(path, item))
    return issues


def validate_text(path: Path, text: str) -> list[str]:
    relative = path.relative_to(ROOT).as_posix()
    issues: list[str] = []
    if USER_HOME_RE.search(text):
        issues.append(f"{relative}: contains a machine-specific user home path")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            issues.append(f"{relative}: contains text resembling a committed secret")
            break
    return issues


def main() -> int:
    paths = tracked_paths()
    issues: list[str] = []
    metadata_checked = 0
    text_checked = 0

    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(".env") and relative != ".env.example":
            issues.append(f"{relative}: environment files must not be tracked")
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        text_checked += 1
        issues.extend(validate_text(path, text))
        if path.suffix.lower() != ".json":
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError as exc:
            issues.append(f"{relative}: invalid JSON ({exc})")
            continue
        if isinstance(record, dict) and record.get("schema") in (
            PORTABLE_SCHEMAS | RECURSIVE_PATH_SCHEMAS
        ):
            metadata_checked += 1
            issues.extend(validate_metadata(path, record))

    if issues:
        print("Repository validation failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print(
        f"Repository validation passed: {metadata_checked} portable metadata records and "
        f"{text_checked} tracked text files checked."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
