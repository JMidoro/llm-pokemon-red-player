from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict  # noqa: E402


SCHEMA = "policy_state_capture_v1"
DEFAULT_POLICY = "battle_menu_throw"


def sanitize_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    if not cleaned:
        raise ValueError("Identifier cannot be empty.")
    return cleaned


def local_state_dir(policy_id: str) -> Path:
    return ROOT / "research" / "policy-states" / "local" / policy_id


def metadata_dir(policy_id: str) -> Path:
    return ROOT / "research" / "policy-states" / policy_id


def default_pyboy_quicksave_path(rom_path: Path) -> Path:
    return Path(str(rom_path) + ".state")


def file_mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def ask_capture_id(policy_id: str) -> str | None:
    print()
    print("Policy-state capture detected. Emulation is paused until this prompt finishes.")
    print(f"Policy: {policy_id}")
    print("Suggested names:")
    print("  - action_menu_fight")
    print("  - action_menu_item")
    print("  - item_menu_top")
    print("  - failed_throw_dialogue")
    print("  - no_balls_action_menu")
    raw = input("Capture name, or blank to discard: ").strip()
    if not raw:
        return None
    return sanitize_id(raw)


def ask_tags() -> list[str]:
    raw = input("Optional comma-separated tags: ").strip()
    if not raw:
        return []
    return [sanitize_id(part) for part in raw.split(",") if part.strip()]


def confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True
    answer = input(f"{path} already exists. Overwrite? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def capture_policy_state(
    pyboy: object,
    *,
    rom: Any,
    policy_id: str,
    capture_id: str,
    quicksave_path: Path,
    tags: list[str],
    note: str,
) -> None:
    state_path = local_state_dir(policy_id) / f"{capture_id}.state"
    screenshot_path = local_state_dir(policy_id) / f"{capture_id}.png"
    metadata_path = metadata_dir(policy_id) / f"{capture_id}.policy-state.json"

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
    record = {
        "schema": SCHEMA,
        "policy_id": policy_id,
        "capture_id": capture_id,
        "created_utc": datetime.now(UTC).isoformat(),
        "tags": tags,
        "note": note,
        "rom": {
            "path": str(rom.path),
            "title": rom.title,
            "size_bytes": rom.size_bytes,
            "md5": rom.md5,
            "sha256": rom.sha256,
        },
        "local_state_file": str(state_path),
        "screenshot_file": str(screenshot_path),
        "snapshot_hash": snapshot_hash(current),
        "snapshot": snapshot_to_dict(current),
    }
    metadata_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote local policy state: {state_path}")
    print(f"Wrote screenshot: {screenshot_path}")
    print(f"Wrote policy metadata: {metadata_path}")
    print(f"Snapshot hash: {snapshot_hash(current)}")
    print(current.plaintext_summary())


def print_controls(policy_id: str) -> None:
    print(
        f"""
Human play controls in the PyBoy window:
  D-pad: Arrow keys
  A: A key
  B: S key
  Start: Enter
  Select: Backspace
  Speed toggle: Space
  Capture policy state: press Z, then return to this terminal and name it
  Quit: Escape in the PyBoy window, or Ctrl+C in this terminal

Policy: {policy_id}
Captured .state/.png files go to research/policy-states/local/{policy_id}/.
Tracked metadata goes to research/policy-states/{policy_id}/.
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Play and capture policy-training states.")
    parser.add_argument("--policy", default=DEFAULT_POLICY)
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in", help="Optional PyBoy .state file to load before play.")
    parser.add_argument("--window", default="SDL2", help="PyBoy window backend. Default: SDL2")
    parser.add_argument("--note", default="", help="Note to attach to every capture in this session.")
    parser.add_argument(
        "--keep-default-quicksave",
        action="store_true",
        help="Keep PyBoy's temporary <rom>.state file after a named capture.",
    )
    args = parser.parse_args()

    policy_id = sanitize_id(args.policy)
    local_state_dir(policy_id).mkdir(parents=True, exist_ok=True)
    metadata_dir(policy_id).mkdir(parents=True, exist_ok=True)

    rom = fingerprint_rom(args.rom)
    quicksave_path = default_pyboy_quicksave_path(rom.path)
    last_quicksave_mtime = file_mtime_ns(quicksave_path)

    print_controls(policy_id)
    print(f"ROM: {rom.title} sha256={rom.sha256}")

    pyboy = open_emulator(rom.path, window=args.window)
    try:
        pyboy.set_emulation_speed(1)
        if args.state_in:
            load_state(pyboy, args.state_in)
            print(f"Loaded initial state: {args.state_in}")

        while pyboy.tick(1, True, True):
            current_mtime = file_mtime_ns(quicksave_path)
            if current_mtime is None or current_mtime == last_quicksave_mtime:
                continue

            last_quicksave_mtime = current_mtime
            try:
                capture_id = ask_capture_id(policy_id)
                if capture_id:
                    tags = ask_tags()
                    capture_policy_state(
                        pyboy,
                        rom=rom,
                        policy_id=policy_id,
                        capture_id=capture_id,
                        quicksave_path=quicksave_path,
                        tags=tags,
                        note=args.note,
                    )
                else:
                    print("Capture discarded.")
            finally:
                if not args.keep_default_quicksave:
                    quicksave_path.unlink(missing_ok=True)
                    last_quicksave_mtime = None
                print("Resuming play. Press Z again for the next policy-state capture.")
    except KeyboardInterrupt:
        print("\nStopping play session.")
    finally:
        pyboy.stop(False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
