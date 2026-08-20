from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.golden_state_io import (  # noqa: E402
    expected_record,
    sanitize_state_name,
    write_expected_record,
)
from pokemon_player.pyboy_lab import (  # noqa: E402
    load_state,
    open_emulator,
    save_screenshot,
    save_state,
    snapshot,
)
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash  # noqa: E402


def local_state_dir() -> Path:
    return ROOT / "research" / "golden-states" / "local"


def expected_dir() -> Path:
    return ROOT / "research" / "golden-states"


def default_pyboy_quicksave_path(rom_path: Path) -> Path:
    return Path(str(rom_path) + ".state")


def file_mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def ask_state_name() -> str | None:
    print()
    print("Capture detected. Emulation is paused until this prompt finishes.")
    print("Enter a golden-state name like 'pallet_overworld_started'.")
    raw = input("State name, or blank to discard: ").strip()
    if not raw:
        return None
    return sanitize_state_name(raw)


def confirm_overwrite(path: Path) -> bool:
    if not path.exists():
        return True
    answer = input(f"{path} already exists. Overwrite? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def capture_named_state(pyboy: object, rom, state_name: str, quicksave_path: Path) -> None:
    state_path = local_state_dir() / f"{state_name}.state"
    screenshot_path = local_state_dir() / f"{state_name}.png"
    expected_path = expected_dir() / f"{state_name}.expected.json"

    if (
        not confirm_overwrite(state_path)
        or not confirm_overwrite(screenshot_path)
        or not confirm_overwrite(expected_path)
    ):
        print("Capture discarded; existing file was not overwritten.")
        return

    load_state(pyboy, quicksave_path)
    current = snapshot(pyboy)
    save_state(pyboy, state_path)
    save_screenshot(pyboy, screenshot_path)
    record = expected_record(
        name=state_name,
        rom=rom,
        state_file=state_path,
        screenshot_file=screenshot_path,
        snapshot=current,
        note="Captured during human play; needs human verification.",
    )
    write_expected_record(record, expected_path)

    print(f"Wrote local state: {state_path}")
    print(f"Wrote screenshot: {screenshot_path}")
    print(f"Wrote expected metadata: {expected_path}")
    print(f"Snapshot hash: {snapshot_hash(current)}")
    print(current.plaintext_summary())


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
  Capture named state: press Z, then return to this terminal and name it
  Quit: Escape in the PyBoy window, or Ctrl+C in this terminal

Captured .state files go to research/golden-states/local/.
Captured metadata goes to research/golden-states/<name>.expected.json.
Metadata starts with human_verified=false until we inspect it.
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Play Pokemon Red in PyBoy and capture named states.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in", help="Optional PyBoy .state file to load before play.")
    parser.add_argument("--window", default="SDL2", help="PyBoy window backend. Default: SDL2")
    parser.add_argument(
        "--keep-default-quicksave",
        action="store_true",
        help="Keep PyBoy's temporary <rom>.state file after a named capture.",
    )
    args = parser.parse_args()

    local_state_dir().mkdir(parents=True, exist_ok=True)
    expected_dir().mkdir(parents=True, exist_ok=True)

    rom = fingerprint_rom(args.rom)
    quicksave_path = default_pyboy_quicksave_path(rom.path)
    last_quicksave_mtime = file_mtime_ns(quicksave_path)

    print_controls()
    print(f"ROM: {rom.title} sha256={rom.sha256}")

    pyboy = open_emulator(rom.path, window=args.window)
    try:
        pyboy.set_emulation_speed(1)
        if args.state_in:
            load_state(pyboy, args.state_in)

        while pyboy.tick(1, True, True):
            current_mtime = file_mtime_ns(quicksave_path)
            if current_mtime is None or current_mtime == last_quicksave_mtime:
                continue

            last_quicksave_mtime = current_mtime
            try:
                state_name = ask_state_name()
                if state_name:
                    capture_named_state(pyboy, rom, state_name, quicksave_path)
                else:
                    print("Capture discarded.")
            finally:
                if not args.keep_default_quicksave:
                    quicksave_path.unlink(missing_ok=True)
                    last_quicksave_mtime = None
                print("Resuming play. Press Z again for the next named capture.")
    except KeyboardInterrupt:
        print("\nStopping play session.")
    finally:
        pyboy.stop(False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
