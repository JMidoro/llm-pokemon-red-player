from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.capsule_io import discover_state_records, load_capsule_specs  # noqa: E402
from pokemon_player.capsule_model import (  # noqa: E402
    CAPSULE_MANIFEST_SCHEMA,
    assign_split,
    validate_capsule_spec,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Phase 4 capsule start manifest.")
    parser.add_argument("--capsules-dir", default=str(ROOT / "research" / "capsules"))
    parser.add_argument(
        "--out",
        default=str(ROOT / "research" / "artifacts" / "capsules" / "v0_manifest.json"),
    )
    parser.add_argument("--strict", action="store_true", help="Fail if any referenced state is missing or unusable.")
    args = parser.parse_args()

    specs = load_capsule_specs(args.capsules_dir)
    state_records = discover_state_records(ROOT)
    spec_issues = [issue for spec in specs for issue in validate_capsule_spec(spec)]
    if spec_issues:
        print(json.dumps([issue.__dict__ for issue in spec_issues], indent=2))
        return 1

    capsules = []
    unresolved = []
    unusable = []
    for spec in specs:
        split = spec["start_state_policy"]["split"]
        seed = str(split.get("seed", "phase4-v0"))
        holdout_ratio = float(split.get("holdout", 0.2))
        resolved_records = []
        seen_state_ids = set()
        for state_id in spec["base_state_ids"]:
            record = state_records.get(state_id)
            if record is None:
                unresolved.append({"capsule_id": spec["id"], "state_id": state_id})
                continue
            if not record.usable_for_capsule:
                unusable.append(
                    {
                        "capsule_id": spec["id"],
                        "state_id": state_id,
                        "status": record.status,
                    }
                )
                continue
            resolved_records.append(record)
            seen_state_ids.add(record.state_id)

        for record in state_records.values():
            if record.capsule_id != spec["id"] or record.state_id in seen_state_ids:
                continue
            if record.usable_for_capsule:
                resolved_records.append(record)
                seen_state_ids.add(record.state_id)
            else:
                unusable.append(
                    {
                        "capsule_id": spec["id"],
                        "state_id": record.state_id,
                        "status": record.status,
                    }
                )

        assignments = assign_split(
            capsule_id=spec["id"],
            state_ids=[record.state_id for record in resolved_records],
            seed=seed,
            holdout_ratio=holdout_ratio,
        )
        capsules.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "objective": spec["objective"],
                "budgets": spec["budgets"],
                "start_counts": {
                    "usable": len(resolved_records),
                    "tuning": sum(1 for split_name in assignments.values() if split_name == "tuning"),
                    "holdout": sum(1 for split_name in assignments.values() if split_name == "holdout"),
                },
                "starts": [
                    {
                        "state_id": record.state_id,
                        "split": assignments[record.state_id],
                        "source": record.source,
                        "status": record.status,
                        "metadata_path": record.metadata_path,
                        "state_path": record.state_path,
                        "snapshot_hash": record.snapshot_hash,
                        "variant_kind": record.variant_kind,
                        "mode": record.snapshot.get("mode"),
                        "location": (record.snapshot.get("position") or {}).get("map_name"),
                        "party": [
                            member.get("species_name")
                            for member in record.snapshot.get("party", [])
                        ],
                    }
                    for record in sorted(resolved_records, key=lambda item: item.state_id)
                ],
            }
        )

    manifest = {
        "schema": CAPSULE_MANIFEST_SCHEMA,
        "created_utc": datetime.now(UTC).isoformat(),
        "capsules_dir": args.capsules_dir,
        "split_method": "deterministic_hash",
        "capsules": capsules,
        "unresolved_references": unresolved,
        "unusable_references": unusable,
    }

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Manifest: {output_path}")
    for capsule in capsules:
        counts = capsule["start_counts"]
        print(
            f"{capsule['id']}: {counts['usable']} usable "
            f"({counts['tuning']} tuning, {counts['holdout']} holdout)"
        )
    if unresolved:
        print(f"Unresolved references: {len(unresolved)}")
    if unusable:
        print(f"Unusable references: {len(unusable)}")
    if args.strict and (unresolved or unusable):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
