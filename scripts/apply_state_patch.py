from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.patch_io import load_patch  # noqa: E402
from pokemon_player.generated_state_io import (  # noqa: E402
    default_report_path,
    generated_state_record,
    write_generated_state_report,
)
from pokemon_player.invariants import check_snapshot_invariants  # noqa: E402
from pokemon_player.pyboy_lab import load_state, open_emulator, save_state, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.state_patch import StatePatchApplier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a structured runtime patch to a PyBoy state.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in", required=True)
    parser.add_argument("--patch", required=True)
    parser.add_argument("--state-out", required=True)
    parser.add_argument("--report-out")
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()

    patch = load_patch(args.patch)
    rom = fingerprint_rom(args.rom)
    pyboy = open_emulator(rom.path)
    try:
        load_state(pyboy, args.state_in)
        report = StatePatchApplier(pyboy.memory).apply(patch)
        if report.loud_warnings() and not args.allow_unverified:
            print("Patch produced warnings and was not saved. Re-run with --allow-unverified.")
            for warning in report.loud_warnings():
                print(warning)
            return 2
        save_state(pyboy, args.state_out)
        state = snapshot(pyboy)
    finally:
        pyboy.stop(False)

    invariants = check_snapshot_invariants(state)

    report_path = Path(args.report_out) if args.report_out else default_report_path(args.state_out)
    record = generated_state_record(
        base_state=args.state_in,
        output_state=args.state_out,
        patch_path=args.patch,
        patch=patch,
        patch_report=report,
        rom=rom,
        snapshot=state,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_generated_state_report(record, report_path)

    print(f"ROM: {rom.title} sha256={rom.sha256}")
    print(f"Patch: {patch.description}")
    if patch.goal:
        print(f"Goal: {patch.goal}")
    for operation in report.operations:
        print(f"- {operation}")
    for warning in report.loud_warnings():
        print(warning)
    if invariants.errors:
        print("Invariant errors:")
        for error in invariants.errors:
            print(f"- {error}")
    if invariants.warnings:
        print("Invariant warnings:")
        for warning in invariants.warnings:
            print(f"- {warning}")
    print(f"Generated-state report: {report_path}")
    print(state.plaintext_summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
