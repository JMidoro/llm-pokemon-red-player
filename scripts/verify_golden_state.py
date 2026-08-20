from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import load_state, open_emulator, snapshot  # noqa: E402
from pokemon_player.repo_paths import resolve_repo_path  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a golden-state expected metadata file.")
    parser.add_argument("expected", help="Path to <name>.expected.json")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state", help="Override local state file path from expected metadata.")
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()

    expected_path = Path(args.expected)
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    if expected.get("schema") != "golden_state_expected_v1":
        raise ValueError(f"{expected_path} is not a golden_state_expected_v1 record.")

    if not expected.get("human_verified") and not args.allow_unverified:
        print(
            "Expected metadata has human_verified=false. "
            "Use --allow-unverified for capture smoke checks."
        )
        return 2

    state_path = (
        Path(args.state)
        if args.state
        else resolve_repo_path(expected["local_state_file"], repo_root=ROOT)
    )
    rom = fingerprint_rom(args.rom)
    expected_sha = expected["rom"]["sha256"]
    if rom.sha256 != expected_sha:
        print(f"ROM hash mismatch: expected {expected_sha}, got {rom.sha256}")
        return 3

    pyboy = open_emulator(rom.path)
    try:
        load_state(pyboy, state_path)
        state = snapshot(pyboy)
    finally:
        pyboy.stop()

    actual_hash = snapshot_hash(state)
    expected_hash = expected["snapshot_hash"]
    if actual_hash != expected_hash:
        print(f"Snapshot hash mismatch: expected {expected_hash}, got {actual_hash}")
        print(state.plaintext_summary())
        return 4

    print(f"Verified {expected_path}")
    print(f"Snapshot hash: {actual_hash}")
    print(state.plaintext_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
