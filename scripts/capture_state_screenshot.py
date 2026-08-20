from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import load_state, open_emulator, save_screenshot  # noqa: E402
from pokemon_player.repo_paths import portable_repo_path, resolve_repo_path  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture or refresh a screenshot for state metadata.")
    parser.add_argument("metadata", help="Golden, generated, or skill-state metadata JSON.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--screenshot-out")
    args = parser.parse_args()

    metadata_path = Path(args.metadata)
    record = json.loads(metadata_path.read_text(encoding="utf-8"))
    state_path = resolve_state_path(record)
    screenshot_path = Path(args.screenshot_out) if args.screenshot_out else default_screenshot_path(state_path)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    rom = fingerprint_rom(args.rom)
    pyboy = open_emulator(rom.path)
    try:
        load_state(pyboy, state_path)
        save_screenshot(pyboy, screenshot_path)
    finally:
        pyboy.stop(False)

    record["screenshot_file"] = portable_repo_path(screenshot_path, repo_root=ROOT)
    metadata_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote screenshot: {screenshot_path}")
    print(f"Updated metadata: {metadata_path}")
    return 0


def resolve_state_path(record: dict) -> Path:
    schema = record.get("schema")
    if schema == "golden_state_expected_v1":
        return resolve_repo_path(record["local_state_file"], repo_root=ROOT)
    if schema == "generated_state_report_v1":
        return resolve_repo_path(record["output_state"], repo_root=ROOT)
    if schema == "skill_state_capture_v1":
        return resolve_repo_path(record["local_state_file"], repo_root=ROOT)
    if schema == "promotion_evidence_capture_v1":
        return resolve_repo_path(record["local_state_file"], repo_root=ROOT)
    raise ValueError(f"Unsupported metadata schema {schema!r}.")


def default_screenshot_path(state_path: Path) -> Path:
    if state_path.suffix == ".state":
        return state_path.with_suffix(".png")
    return Path(str(state_path) + ".png")


if __name__ == "__main__":
    raise SystemExit(main())
