from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_player.rom import RomFingerprint
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict
from pokemon_player.state_model import GameSnapshot


SKILL_STATE_SCHEMA = "skill_state_capture_v1"
SKILL_CATALOG_SCHEMA = "skill_catalog_v1"


def sanitize_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    if not cleaned:
        raise ValueError("Identifier cannot be empty.")
    return cleaned


def skill_state_record(
    *,
    skill_id: str,
    capture_id: str,
    phase: str,
    expected_status: str,
    expected_reason: str,
    rom: RomFingerprint,
    state_file: Path,
    screenshot_file: Path | None,
    snapshot: GameSnapshot,
    note: str = "",
    manual_action: str = "",
    paired_capture_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": SKILL_STATE_SCHEMA,
        "skill_id": skill_id,
        "capture_id": capture_id,
        "phase": phase,
        "expected_status": expected_status,
        "expected_reason": expected_reason,
        "manual_action": manual_action,
        "paired_capture_id": paired_capture_id,
        "created_utc": datetime.now(UTC).isoformat(),
        "note": note,
        "rom": {
            "path": str(rom.path),
            "title": rom.title,
            "size_bytes": rom.size_bytes,
            "md5": rom.md5,
            "sha256": rom.sha256,
        },
        "local_state_file": str(state_file),
        "screenshot_file": str(screenshot_file) if screenshot_file else None,
        "snapshot_hash": snapshot_hash(snapshot),
        "snapshot": snapshot_to_dict(snapshot),
    }


def write_skill_state_record(record: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")


def load_skill_state_record(path: str | Path) -> dict[str, Any]:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("schema") != SKILL_STATE_SCHEMA:
        raise ValueError(f"{path} is not a {SKILL_STATE_SCHEMA} record.")
    return record
