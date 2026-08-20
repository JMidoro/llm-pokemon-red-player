from __future__ import annotations

import argparse
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
from pokemon_player.golden_state_io import expected_record, sanitize_state_name, write_expected_record  # noqa: E402


def default_state_path(name: str) -> Path:
    return ROOT / "research" / "golden-states" / "local" / f"{name}.state"


def default_expected_path(name: str) -> Path:
    return ROOT / "research" / "golden-states" / f"{name}.expected.json"


def default_screenshot_path(name: str) -> Path:
    return ROOT / "research" / "golden-states" / "local" / f"{name}.png"


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a local PyBoy state and expected metadata.")
    parser.add_argument("name", help="Stable golden-state name, e.g. viridian_forest_entrance")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in", help="Optional existing PyBoy .state file to load first.")
    parser.add_argument("--state-out", help="Local .state destination; defaults under golden-states/local.")
    parser.add_argument("--screenshot-out", help="Local screenshot destination; defaults under golden-states/local.")
    parser.add_argument(
        "--expected-out",
        help="Commit-safe expected metadata destination; defaults under golden-states.",
    )
    parser.add_argument("--boot-frames", type=int, default=0)
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    name = sanitize_state_name(args.name)

    state_out = Path(args.state_out) if args.state_out else default_state_path(name)
    screenshot_out = (
        Path(args.screenshot_out) if args.screenshot_out else default_screenshot_path(name)
    )
    expected_out = Path(args.expected_out) if args.expected_out else default_expected_path(name)
    state_out.parent.mkdir(parents=True, exist_ok=True)
    screenshot_out.parent.mkdir(parents=True, exist_ok=True)
    expected_out.parent.mkdir(parents=True, exist_ok=True)

    rom = fingerprint_rom(args.rom)
    pyboy = open_emulator(rom.path)
    try:
        if args.state_in:
            load_state(pyboy, args.state_in)
        if args.boot_frames:
            pyboy.tick(args.boot_frames, False)
        state = snapshot(pyboy)
        save_state(pyboy, state_out)
        save_screenshot(pyboy, screenshot_out)
    finally:
        pyboy.stop()

    record = expected_record(
        name=name,
        rom=rom,
        state_file=state_out,
        screenshot_file=screenshot_out,
        snapshot=state,
        note=args.note,
        boot_frames=args.boot_frames,
    )
    write_expected_record(record, expected_out)

    print(f"Wrote local state: {state_out}")
    print(f"Wrote screenshot: {screenshot_out}")
    print(f"Wrote expected metadata: {expected_out}")
    print(f"Snapshot hash: {record['snapshot_hash']}")
    print(state.plaintext_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
