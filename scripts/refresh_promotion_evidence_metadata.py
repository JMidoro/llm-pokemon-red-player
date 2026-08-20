from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.promotion_evidence_io import (  # noqa: E402
    PROMOTION_EVIDENCE_SCHEMA,
    enrich_derived_assertion_facts,
    enrich_visual_assertion_facts,
    infer_assertions_for_promotion,
)
from pokemon_player.pokedex import read_pokedex  # noqa: E402
from pokemon_player.pyboy_lab import load_state, open_emulator, snapshot  # noqa: E402
from pokemon_player.repo_paths import portable_repo_path, resolve_repo_path  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict  # noqa: E402


EVIDENCE_ROOT = ROOT / "research" / "promotions" / "evidence"


def refresh_one(metadata_path: Path, *, rom_path: Path, infer_assertions: bool, force_assertions: bool) -> None:
    record = json.loads(metadata_path.read_text(encoding="utf-8"))
    if record.get("schema") != PROMOTION_EVIDENCE_SCHEMA:
        raise ValueError(f"{metadata_path} is not a {PROMOTION_EVIDENCE_SCHEMA} record.")

    state_path = resolve_repo_path(record["local_state_file"], repo_root=ROOT)
    if not state_path.exists():
        raise FileNotFoundError(state_path)

    rom = fingerprint_rom(rom_path)
    pyboy = open_emulator(rom.path)
    try:
        load_state(pyboy, state_path)
        current = snapshot(pyboy)
        pokedex = read_pokedex(pyboy.memory)
    finally:
        pyboy.stop(False)

    record["rom"] = {
        "path": portable_repo_path(rom.path, repo_root=ROOT),
        "title": rom.title,
        "size_bytes": rom.size_bytes,
        "md5": rom.md5,
        "sha256": rom.sha256,
    }
    record["snapshot"] = snapshot_to_dict(current)
    record["snapshot_hash"] = snapshot_hash(current)
    record["pokedex"] = pokedex
    enrich_derived_assertion_facts(record)
    enrich_visual_assertion_facts(record)

    if infer_assertions and (force_assertions or not record.get("assertions")):
        promotion_id = str(record.get("promotion_id", ""))
        inferred = infer_assertions_for_promotion(
            promotion_id,
            str(record.get("evidence_id", "")),
            str(record.get("label", "")),
            str(record.get("expected_observation", "")),
        )
        if inferred:
            record["assertions"] = inferred

    metadata_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    print(f"refreshed {metadata_path}")


def evidence_paths(args: argparse.Namespace) -> list[Path]:
    if args.metadata:
        return [Path(path) for path in args.metadata]
    if args.promotion:
        return sorted((EVIDENCE_ROOT / args.promotion).glob("*.promotion-evidence.json"))
    return sorted(EVIDENCE_ROOT.glob("*/*.promotion-evidence.json"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh promotion evidence metadata from local .state files.")
    parser.add_argument("metadata", nargs="*", help="Specific promotion evidence metadata JSON files.")
    parser.add_argument("--promotion", help="Promotion id subdirectory under research/promotions/evidence.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--infer-assertions", action="store_true")
    parser.add_argument("--force-assertions", action="store_true")
    parser.add_argument("--skip-missing", action="store_true")
    args = parser.parse_args()

    for metadata_path in evidence_paths(args):
        try:
            refresh_one(
                metadata_path,
                rom_path=Path(args.rom),
                infer_assertions=args.infer_assertions,
                force_assertions=args.force_assertions,
            )
        except FileNotFoundError as exc:
            if not args.skip_missing:
                raise
            print(f"skipped missing state for {metadata_path}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
