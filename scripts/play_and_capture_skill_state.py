from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import (  # noqa: E402
    load_state,
    open_emulator,
    save_screenshot,
    save_state,
    snapshot,
)
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.skill_state_io import (  # noqa: E402
    sanitize_id,
    skill_state_record,
    write_skill_state_record,
)
from pokemon_player.snapshot_io import snapshot_hash  # noqa: E402


CATALOG_PATH = ROOT / "research" / "skill-states" / "catalog.json"
SEED_CAPTURE_ID = "seed"


def local_state_dir(skill_id: str) -> Path:
    return ROOT / "research" / "skill-states" / "local" / skill_id


def metadata_dir(skill_id: str) -> Path:
    return ROOT / "research" / "skill-states" / skill_id


def default_pyboy_quicksave_path(rom_path: Path) -> Path:
    return Path(str(rom_path) + ".state")


def file_mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def load_skill_definition(skill_id: str) -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    for skill in catalog["skills"]:
        if sanitize_id(skill["id"]) == skill_id:
            return skill
    raise ValueError(f"Skill {skill_id!r} is not in {CATALOG_PATH}.")


def expected_capture_by_id(skill: dict) -> dict[str, dict]:
    return {sanitize_id(item["id"]): item for item in skill["needed_captures"]}


def seed_state_path(skill_id: str) -> Path:
    return local_state_dir(skill_id) / f"{SEED_CAPTURE_ID}.state"


def seed_screenshot_path(skill_id: str) -> Path:
    return local_state_dir(skill_id) / f"{SEED_CAPTURE_ID}.png"


def seed_metadata_path(skill_id: str) -> Path:
    return metadata_dir(skill_id) / f"{SEED_CAPTURE_ID}.skill.json"


def ask_result_code(skill: dict) -> str | None:
    print()
    print("Skill-state capture detected. Emulation is paused until this prompt finishes.")
    expected = expected_capture_by_id(skill)
    print(f"Skill: {skill['id']} ({skill['name']})")
    print("Valid result codes:")
    for capture_id, capture in expected.items():
        print(f"  - {capture_id}: {capture['expected_status']} - {capture['condition']}")
    raw = input("Result code, or blank to reset to seed without capture: ").strip()
    if not raw:
        return None
    capture_id = sanitize_id(raw)
    while capture_id not in expected:
        print(f"{capture_id!r} is not a valid result code for {skill['id']}.")
        raw = input("Enter a valid result code, or blank to reset to seed: ").strip()
        if not raw:
            return None
        capture_id = sanitize_id(raw)
    return capture_id


def confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True
    answer = input(f"{path} already exists. Overwrite? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def capture_seed_state(pyboy: object, rom, skill: dict, quicksave_path: Path) -> None:
    skill_id = sanitize_id(skill["id"])
    state_path = seed_state_path(skill_id)
    screenshot_path = seed_screenshot_path(skill_id)
    metadata_path = seed_metadata_path(skill_id)

    if (
        not confirm_overwrite(state_path)
        or not confirm_overwrite(screenshot_path)
        or not confirm_overwrite(metadata_path)
    ):
        print("Seed capture discarded; existing file was not overwritten.")
        return

    state_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    load_state(pyboy, quicksave_path)
    current = snapshot(pyboy)
    save_state(pyboy, state_path)
    save_screenshot(pyboy, screenshot_path)
    record = skill_state_record(
        skill_id=skill_id,
        capture_id=SEED_CAPTURE_ID,
        phase="seed",
        expected_status="seed",
        expected_reason="skill_seed",
        manual_action="Seed state used as reset point for this skill capture session.",
        paired_capture_id=None,
        rom=rom,
        state_file=state_path,
        screenshot_file=screenshot_path,
        snapshot=current,
        note=f"Seed state for {skill['name']}.",
    )
    write_skill_state_record(record, metadata_path)
    print(f"Wrote skill seed state: {state_path}")
    print(f"Wrote seed screenshot: {screenshot_path}")
    print(f"Wrote seed metadata: {metadata_path}")
    print(current.plaintext_summary())


def capture_skill_state(
    pyboy: object,
    rom,
    skill: dict,
    capture_id: str,
    quicksave_path: Path,
) -> None:
    skill_id = sanitize_id(skill["id"])
    expected = expected_capture_by_id(skill)[capture_id]
    state_path = local_state_dir(skill_id) / f"{capture_id}.state"
    screenshot_path = local_state_dir(skill_id) / f"{capture_id}.png"
    metadata_path = metadata_dir(skill_id) / f"{capture_id}.skill.json"

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
    record = skill_state_record(
        skill_id=skill_id,
        capture_id=capture_id,
        phase=infer_phase(capture_id),
        expected_status=sanitize_id(expected["expected_status"]),
        expected_reason=capture_id,
        manual_action=expected["manual_action"],
        paired_capture_id=infer_pair(capture_id, expected_capture_by_id(skill)),
        rom=rom,
        state_file=state_path,
        screenshot_file=screenshot_path,
        snapshot=current,
        note=expected["condition"],
    )
    write_skill_state_record(record, metadata_path)

    print(f"Wrote local state: {state_path}")
    print(f"Wrote screenshot: {screenshot_path}")
    print(f"Wrote skill metadata: {metadata_path}")
    print(f"Snapshot hash: {snapshot_hash(current)}")
    print(current.plaintext_summary())


def infer_phase(capture_id: str) -> str:
    if capture_id.endswith("_before"):
        return "before"
    if capture_id.endswith("_after") or "_after_" in capture_id:
        return "after"
    if capture_id == SEED_CAPTURE_ID:
        return "seed"
    return "single"


def infer_pair(capture_id: str, expected: dict[str, dict]) -> str | None:
    if capture_id.endswith("_before"):
        paired = capture_id.removesuffix("_before") + "_after"
        return paired if paired in expected else None
    if capture_id.endswith("_after"):
        paired = capture_id.removesuffix("_after") + "_before"
        return paired if paired in expected else None
    return None


def print_controls() -> None:
    print(
        """
Human play controls in the PyBoy window:
  D-pad: Arrow keys
  A: A key
  B: S key
  Start: Enter
  Select: Backspace
  Speed toggle: Space
  Capture skill state: press Z, then return to this terminal and choose a result code
  Quit: Escape in the PyBoy window, or Ctrl+C in this terminal
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Play and capture skill-testing states.")
    parser.add_argument("skill", help="Skill id from research/skill-states/catalog.json")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in", help="Optional PyBoy .state file to load before play.")
    parser.add_argument(
        "--reset-to-state-in",
        action="store_true",
        help="Use --state-in as the session reset point instead of the skill seed.",
    )
    parser.add_argument("--window", default="SDL2")
    parser.add_argument("--keep-default-quicksave", action="store_true")
    args = parser.parse_args()
    if args.reset_to_state_in and not args.state_in:
        parser.error("--reset-to-state-in requires --state-in.")

    skill_id = sanitize_id(args.skill)
    skill = load_skill_definition(skill_id)
    rom = fingerprint_rom(args.rom)
    quicksave_path = default_pyboy_quicksave_path(rom.path)
    last_quicksave_mtime = file_mtime_ns(quicksave_path)
    seed_path = seed_state_path(skill_id)
    session_reset_path = Path(args.state_in) if args.reset_to_state_in and args.state_in else seed_path

    print_controls()
    print(f"Skill: {skill['id']} ({skill['name']})")
    print(f"ROM: {rom.title} sha256={rom.sha256}")

    pyboy = open_emulator(rom.path, window=args.window)
    try:
        pyboy.set_emulation_speed(1)
        if args.reset_to_state_in and args.state_in:
            load_state(pyboy, args.state_in)
            print(f"Loaded recommended start state: {args.state_in}")
            print(f"Session resets will return to: {session_reset_path}")
        elif seed_path.exists():
            load_state(pyboy, seed_path)
            print(f"Loaded existing skill seed: {seed_path}")
        elif args.state_in:
            load_state(pyboy, args.state_in)
            print("No seed exists yet. Press Z to capture the seed state for this skill.")
        else:
            print("No seed exists yet. Press Z to capture the seed state for this skill.")

        while pyboy.tick(1, True, True):
            current_mtime = file_mtime_ns(quicksave_path)
            if current_mtime is None or current_mtime == last_quicksave_mtime:
                continue

            last_quicksave_mtime = current_mtime
            try:
                if not seed_path.exists() and not args.reset_to_state_in:
                    capture_seed_state(pyboy, rom, skill, quicksave_path)
                    seed_path = seed_state_path(skill_id)
                    session_reset_path = seed_path
                else:
                    capture_id = ask_result_code(skill)
                    if capture_id:
                        capture_skill_state(pyboy, rom, skill, capture_id, quicksave_path)
                    else:
                        print("No capture saved; resetting to session start.")
                    load_state(pyboy, session_reset_path)
                    print(f"Reset to session start: {session_reset_path}")
            finally:
                if not args.keep_default_quicksave:
                    quicksave_path.unlink(missing_ok=True)
                    last_quicksave_mtime = None
                print("Resuming play. Press Z again for the next skill-state capture.")
    except KeyboardInterrupt:
        print("\nStopping play session.")
    finally:
        pyboy.stop(False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
