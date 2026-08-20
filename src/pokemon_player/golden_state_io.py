from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_player.rom import RomFingerprint
from pokemon_player.repo_paths import portable_repo_path
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict
from pokemon_player.state_model import GameSnapshot


GOLDEN_STATE_SCHEMA = "golden_state_expected_v1"


def sanitize_state_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    if not cleaned:
        raise ValueError("State name cannot be empty.")
    return cleaned


def expected_record(
    *,
    name: str,
    rom: RomFingerprint,
    state_file: Path,
    snapshot: GameSnapshot,
    screenshot_file: Path | None = None,
    note: str = "",
    boot_frames: int = 0,
    human_verified: bool = False,
) -> dict[str, Any]:
    return {
        "schema": GOLDEN_STATE_SCHEMA,
        "name": name,
        "human_verified": human_verified,
        "created_utc": datetime.now(UTC).isoformat(),
        "note": note,
        "rom": {
            "path": portable_repo_path(rom.path),
            "title": rom.title,
            "size_bytes": rom.size_bytes,
            "md5": rom.md5,
            "sha256": rom.sha256,
        },
        "local_state_file": portable_repo_path(state_file),
        "screenshot_file": portable_repo_path(screenshot_file) if screenshot_file else None,
        "boot_frames": boot_frames,
        "snapshot_hash": snapshot_hash(snapshot),
        "snapshot": snapshot_to_dict(snapshot),
    }


def write_expected_record(record: dict[str, Any], expected_path: str | Path) -> None:
    Path(expected_path).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
