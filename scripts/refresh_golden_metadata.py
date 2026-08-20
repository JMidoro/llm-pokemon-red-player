from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.golden_state_io import expected_record, write_expected_record  # noqa: E402
from pokemon_player.pyboy_lab import load_state, open_emulator, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402


def refresh_one(expected_path: Path, *, rom_path: Path, human_verified: bool | None) -> None:
    existing = json.loads(expected_path.read_text(encoding="utf-8"))
    rom = fingerprint_rom(rom_path)
    state_path = Path(existing["local_state_file"])
    if not state_path.exists():
        raise FileNotFoundError(state_path)

    pyboy = open_emulator(rom.path)
    try:
        load_state(pyboy, state_path)
        state = snapshot(pyboy)
    finally:
        pyboy.stop(False)

    verified = existing.get("human_verified", False) if human_verified is None else human_verified
    record = expected_record(
        name=existing["name"],
        rom=rom,
        state_file=state_path,
        screenshot_file=Path(existing["screenshot_file"]) if existing.get("screenshot_file") else None,
        snapshot=state,
        note=existing.get("note", ""),
        boot_frames=existing.get("boot_frames", 0),
        human_verified=verified,
    )
    record["created_utc"] = existing.get("created_utc", record["created_utc"])
    write_expected_record(record, expected_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh golden-state metadata from local .state files.")
    parser.add_argument("expected", nargs="*", help="Specific expected JSON files. Defaults to all.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--mark-human-verified", action="store_true")
    parser.add_argument("--skip-missing", action="store_true")
    args = parser.parse_args()

    expected_paths = [Path(path) for path in args.expected]
    if not expected_paths:
        expected_paths = sorted((ROOT / "research" / "golden-states").glob("*.expected.json"))

    human_verified = True if args.mark_human_verified else None
    for expected_path in expected_paths:
        try:
            refresh_one(expected_path, rom_path=Path(args.rom), human_verified=human_verified)
            print(f"refreshed {expected_path}")
        except FileNotFoundError as exc:
            if not args.skip_missing:
                raise
            print(f"skipped missing state for {expected_path}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
