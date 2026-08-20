from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import load_state, open_emulator, snapshot  # noqa: E402
from pokemon_player.generated_state_io import find_report_for_state  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402


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
  Quit: Escape in the PyBoy window, or Ctrl+C in this terminal
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Load a PyBoy state and play it without capture prompts.")
    parser.add_argument("state", help="PyBoy .state file to load.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--window", default="SDL2")
    args = parser.parse_args()

    rom = fingerprint_rom(args.rom)
    print_controls()
    print(f"ROM: {rom.title} sha256={rom.sha256}")
    generated_report = find_report_for_state(args.state)
    if generated_report:
        print(f"Generated state: {generated_report.record.get('description')}")
        if generated_report.goal:
            print(f"Goal: {generated_report.goal}")
        print(f"Approval status: {generated_report.approval_status}")

    pyboy = open_emulator(rom.path, window=args.window)
    try:
        pyboy.set_emulation_speed(1)
        load_state(pyboy, args.state)
        print(snapshot(pyboy).plaintext_summary())
        while pyboy.tick(1, True, True):
            pass
    except KeyboardInterrupt:
        print("\nStopping play session.")
    finally:
        pyboy.stop(False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
