from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import load_state, open_emulator, run_button_trace, save_state, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash  # noqa: E402
from pokemon_player.trace import load_trace  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a JSON button trace from a PyBoy state.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--state-out")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    rom = fingerprint_rom(args.rom)
    trace = load_trace(args.trace)
    pyboy = open_emulator(rom.path)
    try:
        load_state(pyboy, args.state_in)
        before = snapshot(pyboy)
        run_button_trace(pyboy, trace, render=args.render)
        after = snapshot(pyboy)
        if args.state_out:
            save_state(pyboy, args.state_out)
    finally:
        pyboy.stop()

    print(f"ROM: {rom.title} sha256={rom.sha256}")
    print(f"Initial snapshot hash: {snapshot_hash(before)}")
    print(f"Final snapshot hash: {snapshot_hash(after)}")
    print(after.plaintext_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

