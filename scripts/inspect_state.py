from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import load_state, open_emulator, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a Pokemon Red emulator state.")
    parser.add_argument("--rom", default="research/PokemonRed.gb")
    parser.add_argument("--state", help="Optional PyBoy .state file to load before inspection.")
    parser.add_argument("--boot-frames", type=int, default=0)
    args = parser.parse_args()

    rom = Path(args.rom)
    fingerprint = fingerprint_rom(rom)
    print(f"ROM: {fingerprint.title} sha256={fingerprint.sha256}")

    pyboy = open_emulator(rom)
    try:
        if args.state:
            load_state(pyboy, args.state)
        if args.boot_frames:
            pyboy.tick(args.boot_frames, False)
        print(snapshot(pyboy).plaintext_summary())
    finally:
        pyboy.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
