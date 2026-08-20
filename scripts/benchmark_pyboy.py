from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import load_state, open_emulator  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure PyBoy headless frame throughput.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in")
    parser.add_argument("--frames", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    if args.frames <= 0:
        raise ValueError("--frames must be positive")
    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")

    rom = fingerprint_rom(args.rom)
    pyboy = open_emulator(rom.path)
    try:
        pyboy.set_emulation_speed(0)
        if args.state_in:
            load_state(pyboy, args.state_in)

        remaining = args.frames
        start = time.perf_counter()
        while remaining > 0:
            step = min(args.batch_size, remaining)
            pyboy.tick(step, False, False)
            remaining -= step
        elapsed = time.perf_counter() - start
    finally:
        pyboy.stop(False)

    fps = args.frames / elapsed
    realtime = fps / 60
    print(f"ROM: {rom.title} sha256={rom.sha256}")
    print(f"Frames: {args.frames}")
    print(f"Elapsed seconds: {elapsed:.3f}")
    print(f"Frames per second: {fps:.1f}")
    print(f"Approx real-time multiplier: {realtime:.1f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

