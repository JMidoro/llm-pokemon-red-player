from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.promotion_evidence_io import (  # noqa: E402
    attach_evidence_to_manifest,
    infer_assertions_for_promotion,
    promotion_evidence_record,
    sanitize_id,
    write_promotion_evidence_record,
)
from pokemon_player.pokedex import read_pokedex  # noqa: E402
from pokemon_player.pyboy_lab import load_state, open_emulator, save_screenshot, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash  # noqa: E402


PROMOTION_MANIFEST = ROOT / "research" / "promotions" / "mvp-skill-promotions.json"
EVIDENCE_ROOT = ROOT / "research" / "promotions" / "evidence"


def resolve_state_path(record: dict[str, Any]) -> Path:
    schema = record.get("schema")
    if schema in {"golden_state_expected_v1", "skill_state_capture_v1", "promotion_evidence_capture_v1"}:
        return Path(record["local_state_file"])
    if schema == "generated_state_report_v1":
        return Path(record["output_state"])
    if schema == "policy_state_capture_v1":
        return Path(record["local_state_file"])
    raise ValueError(f"Unsupported metadata schema {schema!r}.")


def resolve_screenshot_path(record: dict[str, Any], state_path: Path) -> Path:
    screenshot = record.get("screenshot_file")
    if isinstance(screenshot, str) and screenshot:
        return Path(screenshot)
    if state_path.suffix == ".state":
        return state_path.with_suffix(".png")
    return Path(str(state_path) + ".png")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Attach an existing state metadata file as machine-checkable promotion evidence."
    )
    parser.add_argument("promotion", help="Promotion id from research/promotions/mvp-skill-promotions.json")
    parser.add_argument("source_metadata", help="Existing golden, skill, policy, generated, or promotion metadata.")
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--expected-observation", required=True)
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--step-title", default="Attach existing state evidence")
    parser.add_argument("--note", default="")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--capture-missing-screenshot", action="store_true")
    parser.add_argument("--no-attach", action="store_true")
    args = parser.parse_args()

    promotion_id = sanitize_id(args.promotion)
    source_metadata = Path(args.source_metadata)
    source_record = json.loads(source_metadata.read_text(encoding="utf-8"))
    state_path = resolve_state_path(source_record)
    screenshot_path = resolve_screenshot_path(source_record, state_path)

    rom = fingerprint_rom(args.rom)
    pyboy = open_emulator(rom.path)
    try:
        load_state(pyboy, state_path)
        if args.capture_missing_screenshot and not screenshot_path.exists():
            save_screenshot(pyboy, screenshot_path)
            source_record["screenshot_file"] = str(screenshot_path)
            source_metadata.write_text(json.dumps(source_record, indent=2, sort_keys=True), encoding="utf-8")
        current = snapshot(pyboy)
        pokedex = read_pokedex(pyboy.memory)
    finally:
        pyboy.stop(False)

    if not screenshot_path.exists():
        raise FileNotFoundError(
            f"{screenshot_path} does not exist. Re-run with --capture-missing-screenshot."
        )

    assertions = infer_assertions_for_promotion(
        promotion_id,
        args.evidence_id,
        args.label,
        args.expected_observation,
    )
    evidence_id = args.evidence_id.strip()
    metadata_path = EVIDENCE_ROOT / promotion_id / f"{sanitize_id(evidence_id)}.promotion-evidence.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    record = promotion_evidence_record(
        promotion_id=promotion_id,
        step_number=args.step,
        step_title=args.step_title,
        evidence_id=evidence_id,
        label=args.label,
        expected_observation=args.expected_observation,
        rom=rom,
        state_file=state_path,
        screenshot_file=screenshot_path,
        snapshot=current,
        assertions=assertions,
        pokedex=pokedex,
        note=args.note or f"Attached from existing metadata: {source_metadata.as_posix()}",
    )
    record["source_metadata_file"] = str(source_metadata)
    write_promotion_evidence_record(record, metadata_path)

    if not args.no_attach:
        action = attach_evidence_to_manifest(
            manifest_path=PROMOTION_MANIFEST,
            repo_root=ROOT,
            promotion_id=promotion_id,
            metadata_path=metadata_path,
            state_path=state_path,
            screenshot_path=screenshot_path,
            evidence_id=evidence_id,
            label=args.label,
            expected_observation=args.expected_observation,
            notes=record["note"],
        )
        print(f"Promotion manifest {action} evidence ref: {PROMOTION_MANIFEST}")

    print(f"Wrote promotion evidence metadata: {metadata_path}")
    print(f"State: {state_path}")
    print(f"Screenshot: {screenshot_path}")
    print(f"Snapshot hash: {snapshot_hash(current)}")
    if assertions:
        print("Assertions:")
        for assertion in assertions:
            expected = assertion.get("expected", assertion.get("expected_path", ""))
            print(f"  - {assertion['actual_path']} {assertion['op']} {expected}")
    else:
        print("No assertions inferred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
