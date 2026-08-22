from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.generated_state_io import (  # noqa: E402
    default_report_path,
    generated_state_record,
    write_generated_state_report,
)
from pokemon_player.invariants import check_snapshot_invariants  # noqa: E402
from pokemon_player.patch_io import patch_from_dict  # noqa: E402
from pokemon_player.pyboy_lab import load_state, open_emulator, save_state, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.state_patch import StatePatchApplier  # noqa: E402


OUT_ROOT = ROOT / "research" / "artifacts" / "capsule-derivatives"
GOLDEN_LOCAL = ROOT / "research" / "golden-states" / "local"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local derivative states for Phase 4 capsule coverage.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--out-root", default=str(OUT_ROOT))
    parser.add_argument("--per-capsule-valid", type=int, default=25)
    parser.add_argument("--per-capsule-degraded", type=int, default=5)
    parser.add_argument(
        "--capsule",
        action="append",
        choices=("viridian_forest_catching", "cerulean_misty"),
        help="Generate only the selected capsule; may be supplied more than once.",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    rom = fingerprint_rom(args.rom)
    variants = capsule_variants(args.per_capsule_valid, args.per_capsule_degraded)
    if args.capsule:
        selected_capsules = set(args.capsule)
        variants = [
            variant
            for variant in variants
            if variant["capsule_id"] in selected_capsules
        ]
    generated = []
    failed = []

    pyboy = open_emulator(rom.path)
    try:
        for variant in variants:
            try:
                result = generate_variant(
                    pyboy=pyboy,
                    rom=rom,
                    variant=variant,
                    out_root=Path(args.out_root),
                    overwrite=args.overwrite,
                )
                generated.append(result)
            except Exception as exc:  # noqa: BLE001 - preserve batch generation failures.
                failed.append(
                    {
                        "id": variant["id"],
                        "capsule_id": variant["capsule_id"],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    finally:
        pyboy.stop(False)

    print(f"Generated: {len(generated)}")
    print(f"Failed: {len(failed)}")
    by_capsule: dict[str, dict[str, int]] = {}
    for item in generated:
        counts = by_capsule.setdefault(item["capsule_id"], {"valid": 0, "degraded": 0})
        counts[item["variant_kind"]] += 1
    for capsule_id, counts in sorted(by_capsule.items()):
        print(f"{capsule_id}: {counts['valid']} valid, {counts['degraded']} degraded")

    coverage_path = Path(args.out_root) / "coverage_manifest.json"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(
        json.dumps(
            {
                "schema": "capsule_derivative_coverage_v1",
                "created_utc": datetime.now(UTC).isoformat(),
                "counts": by_capsule,
                "generated": generated,
                "failed": failed,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"Coverage manifest: {coverage_path}")
    if failed:
        print(json.dumps(failed, indent=2))
        return 1
    return 0


def generate_variant(
    *,
    pyboy: object,
    rom,
    variant: dict[str, Any],
    out_root: Path,
    overwrite: bool,
) -> dict[str, str]:
    capsule_id = variant["capsule_id"]
    variant_kind = variant["variant_kind"]
    output_dir = out_root / capsule_id / variant_kind
    output_dir.mkdir(parents=True, exist_ok=True)
    state_out = output_dir / f"{variant['id']}.state"
    patch_out = output_dir / f"{variant['id']}.patch.json"
    report_out = default_report_path(state_out)
    if state_out.exists() and report_out.exists() and not overwrite:
        return {
            "id": variant["id"],
            "capsule_id": capsule_id,
            "variant_kind": variant_kind,
            "state_out": str(state_out),
        }

    patch_raw = {
        "description": variant["description"],
        "goal": variant["goal"],
        "metadata": {
            "capsule_id": capsule_id,
            "variant_id": variant["id"],
            "variant_kind": variant_kind,
            "mvp_coverage": True,
        },
        "operations": variant["operations"],
    }
    patch = patch_from_dict(patch_raw)
    patch_out.write_text(json.dumps(patch_raw, indent=2, sort_keys=True), encoding="utf-8")

    load_state(pyboy, variant["base_state"])
    report = StatePatchApplier(pyboy.memory).apply(patch)
    save_state(pyboy, state_out)
    state = snapshot(pyboy)
    invariants = check_snapshot_invariants(state)
    if invariants.errors:
        raise RuntimeError(f"Invariant errors: {invariants.errors}")

    record = generated_state_record(
        base_state=variant["base_state"],
        output_state=state_out,
        patch_path=patch_out,
        patch=patch,
        patch_report=report,
        rom=rom,
        snapshot=state,
    )
    record["approval"]["notes"] = "Generated as Phase 4 MVP coverage candidate; needs human goal approval."
    record["capsule_id"] = capsule_id
    record["variant_id"] = variant["id"]
    record["variant_kind"] = variant_kind
    write_generated_state_report(record, report_out)
    return {
        "id": variant["id"],
        "capsule_id": capsule_id,
        "variant_kind": variant_kind,
        "state_out": str(state_out),
    }


def capsule_variants(valid_count: int, degraded_count: int) -> list[dict[str, Any]]:
    return [
        *viridian_variants(valid_count, degraded_count),
        *misty_variants(valid_count, degraded_count),
    ]


def viridian_variants(valid_count: int, degraded_count: int) -> list[dict[str, Any]]:
    bases = [
        GOLDEN_LOCAL / "viridian_forest_grass.state",
        GOLDEN_LOCAL / "viridian_forest_south_gate.state",
        GOLDEN_LOCAL / "viridian_forest_wild_battle_weedle.state",
        GOLDEN_LOCAL / "viridian_forest_wild_battle_pikachu_full_health.state",
        GOLDEN_LOCAL / "viridian_forest_wild_battle_pikachu_weakened.state",
    ]
    leads = [
        ("Nidoran M", 8, 26, ["Leer", "Tackle", "Horn Attack"]),
        ("Squirtle", 9, 29, ["Tackle", "Tail Whip", "Bubble"]),
        ("Spearow", 7, 22, ["Peck", "Growl"]),
        ("Butterfree", 10, 35, ["Tackle", "String Shot"]),
    ]
    variants = []
    for index in range(valid_count):
        species, level, max_hp, moves = leads[index % len(leads)]
        hp = max(4, max_hp - (index % 7))
        variants.append(
            variant(
                capsule_id="viridian_forest_catching",
                variant_kind="valid",
                index=index + 1,
                base_state=bases[index % len(bases)],
                description=f"Viridian catching valid MVP variant {index + 1}.",
                goal="Catch a wild Pokemon in Viridian Forest without blacking out.",
                operations=[
                    set_species(1, species),
                    set_stats(1, level=level, hp=hp, max_hp=max_hp, status="ok"),
                    set_moves(1, moves),
                    set_item("Poke Ball", 2 + (index % 6)),
                    set_item("Potion", index % 3),
                    set_item("Antidote", index % 4),
                    set_money(200 + index * 73),
                ],
            )
        )
    for index in range(degraded_count):
        species, level, max_hp, moves = leads[index % len(leads)]
        no_balls = index % 2 == 0
        variants.append(
            variant(
                capsule_id="viridian_forest_catching",
                variant_kind="degraded",
                index=index + 1,
                base_state=bases[index % len(bases)],
                description=f"Viridian catching degraded MVP variant {index + 1}.",
                goal="Exercise impossible/degraded handling for Viridian Forest catching.",
                operations=[
                    set_species(1, species),
                    set_stats(1, level=level, hp=1 + index, max_hp=max_hp, status="poison" if index == 1 else "ok"),
                    set_moves(1, moves),
                    set_item("Poke Ball", 0 if no_balls else 1),
                    set_item("Potion", 0),
                    set_item("Antidote", 0 if index != 1 else 1),
                    set_money(index * 50),
                ],
            )
        )
    return variants


def misty_variants(valid_count: int, degraded_count: int) -> list[dict[str, Any]]:
    bases = [
        GOLDEN_LOCAL / "cerulean_city_overworld.state",
        GOLDEN_LOCAL / "cerulean_pokecenter_overworld.state",
        GOLDEN_LOCAL / "cerulean_gym_overworld.state",
        GOLDEN_LOCAL / "mid_misty_battle.state",
    ]
    lead_plans = [
        ("Pikachu", 18, 44, ["ThunderShock", "Growl", "Thunder Wave", "Quick Attack"]),
        ("Wartortle", 19, 58, ["Tackle", "Tail Whip", "Bubble", "Water Gun"]),
        ("Butterfree", 16, 50, ["Tackle", "String Shot"]),
        ("Nidoran F", 17, 52, ["Growl", "Tackle", "Scratch", "Poison Sting"]),
    ]
    variants = []
    for index in range(valid_count):
        species, level, max_hp, moves = lead_plans[index % len(lead_plans)]
        variants.append(
            variant(
                capsule_id="cerulean_misty",
                variant_kind="valid",
                index=index + 1,
                base_state=bases[index % len(bases)],
                description=f"Cerulean/Misty valid MVP variant {index + 1}.",
                goal="Prepare for and defeat Misty without blacking out.",
                operations=[
                    set_badges(["Boulder Badge"]),
                    set_species(1, species),
                    set_stats(1, level=level, hp=max_hp - (index % 9), max_hp=max_hp, status="ok"),
                    set_moves(1, moves),
                    set_item("Potion", 1 + (index % 5)),
                    set_item("Super Potion", index % 2),
                    set_item("Poke Ball", index % 5),
                    set_money(500 + index * 111),
                ],
            )
        )
    for index in range(degraded_count):
        species, level, max_hp, moves = lead_plans[(index + 1) % len(lead_plans)]
        variants.append(
            variant(
                capsule_id="cerulean_misty",
                variant_kind="degraded",
                index=index + 1,
                base_state=bases[index % len(bases)],
                description=f"Cerulean/Misty degraded MVP variant {index + 1}.",
                goal="Exercise degraded or likely-impossible Misty preparation handling.",
                operations=[
                    set_badges(["Boulder Badge"]),
                    set_species(1, species),
                    set_stats(
                        1,
                        level=max(10, level - 7 - index),
                        hp=1 + index,
                        max_hp=max_hp,
                        status="paralysis" if index == 2 else "ok",
                    ),
                    set_moves(1, moves),
                    set_item("Potion", 0),
                    set_item("Super Potion", 0),
                    set_item("Poke Ball", 0),
                    set_money(index * 100),
                ],
            )
        )
    return variants


def variant(
    *,
    capsule_id: str,
    variant_kind: str,
    index: int,
    base_state: Path,
    description: str,
    goal: str,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": f"{capsule_id}_{variant_kind}_{index:02d}",
        "capsule_id": capsule_id,
        "variant_kind": variant_kind,
        "base_state": str(base_state),
        "description": description,
        "goal": goal,
        "operations": operations,
    }


def set_species(slot: int, species: str) -> dict[str, Any]:
    return {"type": "set_party_species", "slot": slot, "species": species}


def set_stats(
    slot: int,
    *,
    level: int,
    hp: int,
    max_hp: int,
    status: str,
) -> dict[str, Any]:
    return {
        "type": "set_party_stats",
        "slot": slot,
        "level": level,
        "current_hp": hp,
        "max_hp": max_hp,
        "attack": max(8, level * 3),
        "defense": max(8, level * 3),
        "speed": max(8, level * 3),
        "special": max(8, level * 3),
        "status": status,
    }


def set_moves(slot: int, moves: list[str]) -> dict[str, Any]:
    return {
        "type": "set_party_moves",
        "slot": slot,
        "moves": moves,
        "pp": [35 for _ in moves],
    }


def set_item(item: str, quantity: int) -> dict[str, Any]:
    return {"type": "set_item_quantity", "item": item, "quantity": quantity}


def set_money(amount: int) -> dict[str, Any]:
    return {"type": "set_money", "amount": amount}


def set_badges(badge_names: list[str]) -> dict[str, Any]:
    return {"type": "set_badges", "badge_names": badge_names}


if __name__ == "__main__":
    raise SystemExit(main())
