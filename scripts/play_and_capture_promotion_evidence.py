from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.promotion_evidence_io import (  # noqa: E402
    attach_evidence_to_manifest,
    infer_assertions_for_promotion,
    get_promotion_step,
    load_promotion_steps,
    promotion_evidence_record,
    sanitize_id,
    write_promotion_evidence_record,
)
from pokemon_player.pokedex import read_pokedex  # noqa: E402
from pokemon_player.pyboy_lab import (  # noqa: E402
    load_state,
    open_emulator,
    save_screenshot,
    save_state,
    snapshot,
)
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash  # noqa: E402


PROMOTION_MANIFEST = ROOT / "research" / "promotions" / "mvp-skill-promotions.json"
PROMOTION_STEPS = ROOT / "research" / "promotions" / "evidence-collection-steps.json"


def local_state_dir(promotion_id: str) -> Path:
    return ROOT / "research" / "promotions" / "evidence" / "local" / promotion_id


def metadata_dir(promotion_id: str) -> Path:
    return ROOT / "research" / "promotions" / "evidence" / promotion_id


def default_pyboy_quicksave_path(rom_path: Path) -> Path:
    return Path(str(rom_path) + ".state")


def file_mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def prompt_with_default(prompt: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw or default


def confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True
    answer = input(f"{path} already exists. Overwrite? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def auto_evidence_label(step_number: int, step: dict[str, Any]) -> str:
    title = str(step.get("title", "promotion evidence"))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"Step {step_number}: {title} {stamp}"


def capture_promotion_evidence(
    pyboy: object,
    rom,
    args: argparse.Namespace,
    promotion_id: str,
    step: dict[str, Any],
    quicksave_path: Path,
) -> None:
    step_title = str(step.get("title", "Evidence step"))
    default_label = args.label or auto_evidence_label(args.step, step)
    default_expected = args.expected_observation or str(step.get("expected_evidence", ""))

    print()
    print("Promotion evidence capture detected. Emulation is paused until this prompt finishes.")
    print(f"Promotion: {promotion_id}")
    print(f"Step {args.step}: {step_title}")
    label = prompt_with_default("Evidence label", default_label)
    evidence_id = sanitize_id(args.evidence_id or f"step_{args.step:02d}_{label}")
    expected_observation = prompt_with_default("Expected observation", default_expected)
    note = prompt_with_default("Notes", args.note or f"Captured for promotion step {args.step}: {step_title}")
    assertions = infer_assertions_for_capture(
        promotion_id=promotion_id,
        evidence_id=evidence_id,
        label=label,
        expected_observation=expected_observation,
        force_no_infer=args.no_infer_assertions,
    )

    state_path = local_state_dir(promotion_id) / f"{evidence_id}.state"
    screenshot_path = local_state_dir(promotion_id) / f"{evidence_id}.png"
    metadata_path = metadata_dir(promotion_id) / f"{evidence_id}.promotion-evidence.json"

    if (
        not confirm_overwrite(state_path)
        or not confirm_overwrite(screenshot_path)
        or not confirm_overwrite(metadata_path)
    ):
        print("Capture discarded; existing file was not overwritten.")
        return

    state_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    load_state(pyboy, quicksave_path)
    current = snapshot(pyboy)
    save_state(pyboy, state_path)
    save_screenshot(pyboy, screenshot_path)
    record = promotion_evidence_record(
        promotion_id=promotion_id,
        step_number=args.step,
        step_title=step_title,
        evidence_id=evidence_id,
        label=label,
        expected_observation=expected_observation,
        rom=rom,
        state_file=state_path,
        screenshot_file=screenshot_path,
        snapshot=current,
        assertions=assertions,
        pokedex=read_pokedex(pyboy.memory),
        note=note,
    )
    write_promotion_evidence_record(record, metadata_path)

    print(f"Wrote promotion evidence state: {state_path}")
    print(f"Wrote promotion evidence screenshot: {screenshot_path}")
    print(f"Wrote promotion evidence metadata: {metadata_path}")
    print(f"Snapshot hash: {snapshot_hash(current)}")

    if args.no_attach:
        print("Manifest attachment skipped because --no-attach was provided.")
    else:
        action = attach_evidence_to_manifest(
            manifest_path=PROMOTION_MANIFEST,
            repo_root=ROOT,
            promotion_id=promotion_id,
            metadata_path=metadata_path,
            state_path=state_path,
            screenshot_path=screenshot_path,
            evidence_id=evidence_id,
            label=label,
            expected_observation=expected_observation,
            notes=note,
        )
        print(f"Promotion manifest {action} evidence ref: {PROMOTION_MANIFEST}")
    print(current.plaintext_summary())


def infer_assertions_for_capture(
    *,
    promotion_id: str,
    evidence_id: str,
    label: str,
    expected_observation: str,
    force_no_infer: bool,
) -> list[dict[str, Any]]:
    if force_no_infer:
        return []
    inferred = infer_assertions_for_promotion(promotion_id, evidence_id, label, expected_observation)
    if not inferred:
        return []
    print()
    print("Inferred WRAM assertions for this evidence:")
    for assertion in inferred:
        expected = assertion.get("expected", assertion.get("expected_path", ""))
        print(f"  - {assertion['actual_path']} {assertion['op']} {expected}")
    answer = input("Attach these assertions? [Y/n] ").strip().lower()
    if answer in {"n", "no"}:
        return []
    return inferred


def print_controls(promotion_id: str, step_number: int, step: dict[str, Any]) -> None:
    print(
        f"""
Human play controls in the PyBoy window:
  D-pad: Arrow keys
  A: A key
  B: S key
  Start: Enter
  Select: Backspace
  Speed toggle: Space
  Capture promotion evidence: press Z, then return to this terminal
  Quit: Escape in the PyBoy window, or Ctrl+C in this terminal

Promotion: {promotion_id}
Step {step_number}: {step.get("title", "Evidence step")}

Captured .state and .png files go to:
  research/promotions/evidence/local/{promotion_id}/

Captured metadata goes to:
  research/promotions/evidence/{promotion_id}/

Unless --no-attach is used, each capture is automatically attached to:
  research/promotions/mvp-skill-promotions.json
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Play Pokemon Red and capture evidence directly against a promotion step."
    )
    parser.add_argument("promotion", help="Promotion id from research/promotions/mvp-skill-promotions.json")
    parser.add_argument("--step", type=int, required=True, help="1-based evidence collection step number.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in", help="Optional PyBoy .state file to load before play.")
    parser.add_argument("--window", default="SDL2", help="PyBoy window backend. Default: SDL2")
    parser.add_argument("--evidence-id", help="Optional stable evidence id. Defaults from label and step.")
    parser.add_argument("--label", help="Optional default evidence label.")
    parser.add_argument("--expected-observation", help="Optional default expected observation.")
    parser.add_argument("--note", default="", help="Optional default evidence note.")
    parser.add_argument("--no-infer-assertions", action="store_true", help="Do not infer promotion-specific assertions.")
    parser.add_argument("--no-attach", action="store_true", help="Write files but do not update the promotion manifest.")
    parser.add_argument("--keep-default-quicksave", action="store_true")
    args = parser.parse_args()

    promotion_id = sanitize_id(args.promotion)
    steps = load_promotion_steps(PROMOTION_STEPS)
    step = get_promotion_step(steps, promotion_id, args.step)

    rom = fingerprint_rom(args.rom)
    quicksave_path = default_pyboy_quicksave_path(rom.path)
    last_quicksave_mtime = file_mtime_ns(quicksave_path)

    print_controls(promotion_id, args.step, step)
    print(f"ROM: {rom.title} sha256={rom.sha256}")

    pyboy = open_emulator(rom.path, window=args.window)
    try:
        pyboy.set_emulation_speed(1)
        if args.state_in:
            load_state(pyboy, args.state_in)
            print(f"Loaded start state: {args.state_in}")
        else:
            print("No start state provided; starting from the ROM boot state.")

        while pyboy.tick(1, True, True):
            current_mtime = file_mtime_ns(quicksave_path)
            if current_mtime is None or current_mtime == last_quicksave_mtime:
                continue

            last_quicksave_mtime = current_mtime
            try:
                capture_promotion_evidence(pyboy, rom, args, promotion_id, step, quicksave_path)
            finally:
                if not args.keep_default_quicksave:
                    quicksave_path.unlink(missing_ok=True)
                    last_quicksave_mtime = None
                print("Resuming play. Press Z again for the next promotion evidence capture.")
    except KeyboardInterrupt:
        print("\nStopping promotion evidence capture session.")
    finally:
        pyboy.stop(False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
