from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_player.patch_model import PatchReport, StatePatch
from pokemon_player.rom import RomFingerprint
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict
from pokemon_player.state_model import GameSnapshot
from pokemon_player.invariants import check_snapshot_invariants


GENERATED_STATE_SCHEMA = "generated_state_report_v1"


@dataclass(frozen=True)
class GeneratedStateReport:
    path: Path
    record: dict[str, Any]

    @property
    def goal(self) -> str | None:
        return self.record.get("goal")

    @property
    def approval_status(self) -> str:
        approval = self.record.get("approval", {})
        return str(approval.get("status", "loadable_unapproved"))


def default_report_path(state_path: str | Path) -> Path:
    path = Path(state_path)
    return path.with_suffix(path.suffix + ".report.json")


def generated_state_record(
    *,
    base_state: str | Path,
    output_state: str | Path,
    patch_path: str | Path,
    patch: StatePatch,
    patch_report: PatchReport,
    rom: RomFingerprint,
    snapshot: GameSnapshot,
) -> dict[str, Any]:
    invariants = check_snapshot_invariants(snapshot)
    return {
        "schema": GENERATED_STATE_SCHEMA,
        "created_utc": datetime.now(UTC).isoformat(),
        "description": patch.description,
        "goal": patch.goal,
        "base_state": str(base_state),
        "output_state": str(output_state),
        "patch_path": str(patch_path),
        "patch_metadata": dict(patch.metadata),
        "rom": {
            "title": rom.title,
            "size_bytes": rom.size_bytes,
            "md5": rom.md5,
            "sha256": rom.sha256,
        },
        "patch_report": {
            "applied": patch_report.applied,
            "operations": list(patch_report.operations),
            "warnings": [
                {"severity": warning.severity, "message": warning.message}
                for warning in patch_report.warnings
            ],
        },
        "snapshot_hash": snapshot_hash(snapshot),
        "snapshot": snapshot_to_dict(snapshot),
        "invariants": {
            "ok": invariants.ok,
            "errors": list(invariants.errors),
            "warnings": list(invariants.warnings),
        },
        "approval": {
            "status": "loadable_unapproved",
            "approved_by": None,
            "approved_at": None,
            "notes": "",
        },
    }


def write_generated_state_report(record: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")


def load_generated_state_report(path: str | Path) -> GeneratedStateReport:
    report_path = Path(path)
    record = json.loads(report_path.read_text(encoding="utf-8"))
    if record.get("schema") != GENERATED_STATE_SCHEMA:
        raise ValueError(f"{report_path} is not a {GENERATED_STATE_SCHEMA} file.")
    return GeneratedStateReport(path=report_path, record=record)


def find_report_for_state(state_path: str | Path) -> GeneratedStateReport | None:
    path = Path(state_path)
    candidates = [
        default_report_path(path),
        path.with_suffix(".report.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return load_generated_state_report(candidate)
    return None
