from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pokemon_player.capsule_model import StateRecord
from pokemon_player.repo_paths import resolve_repo_path


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_capsule_specs(directory: str | Path) -> list[dict[str, Any]]:
    return [
        load_json(path)
        for path in sorted(Path(directory).glob("*.json"))
        if path.name != "README.md"
    ]


def discover_state_records(root: str | Path) -> dict[str, StateRecord]:
    root_path = Path(root)
    records: dict[str, StateRecord] = {}
    records.update(discover_golden_records(root_path / "research" / "golden-states"))
    records.update(discover_generated_records(root_path / "research" / "artifacts"))
    return records


def discover_golden_records(directory: Path) -> dict[str, StateRecord]:
    records: dict[str, StateRecord] = {}
    for path in sorted(directory.glob("*.expected.json")):
        raw = load_json(path)
        if raw.get("schema") != "golden_state_expected_v1":
            continue
        name = str(raw["name"])
        records[f"golden:{name}"] = StateRecord(
            state_id=f"golden:{name}",
            source="golden",
            status="human_verified" if raw.get("human_verified") else "unverified",
            metadata_path=str(path),
            state_path=str(resolve_repo_path(raw["local_state_file"], repo_root=directory.parents[1]))
            if raw.get("local_state_file")
            else None,
            snapshot_hash=str(raw.get("snapshot_hash", "")),
            snapshot=dict(raw.get("snapshot", {})),
        )
    return records


def discover_generated_records(directory: Path) -> dict[str, StateRecord]:
    records: dict[str, StateRecord] = {}
    if not directory.exists():
        return records
    for path in sorted(directory.rglob("*.report.json")):
        raw = load_json(path)
        if raw.get("schema") != "generated_state_report_v1":
            continue
        stored_output_state = str(raw.get("output_state", ""))
        output_state = (
            str(resolve_repo_path(stored_output_state, repo_root=directory.parents[1]))
            if stored_output_state
            else ""
        )
        name = Path(output_state).name.removesuffix(".state") if output_state else path.name
        approval = raw.get("approval", {})
        status = str(approval.get("status", "loadable_unapproved"))
        patch_metadata = raw.get("patch_metadata", {})
        records[f"generated:{name}"] = StateRecord(
            state_id=f"generated:{name}",
            source="generated",
            status=status,
            metadata_path=str(path),
            state_path=output_state,
            snapshot_hash=str(raw.get("snapshot_hash", "")),
            snapshot=dict(raw.get("snapshot", {})),
            capsule_id=raw.get("capsule_id") or patch_metadata.get("capsule_id"),
            variant_kind=raw.get("variant_kind") or patch_metadata.get("variant_kind"),
        )
    return records
