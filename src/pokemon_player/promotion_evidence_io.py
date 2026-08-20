from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_player.battle_ui import BattleUiState, inspect_battle_ui_screenshot
from pokemon_player.capsule_a_navigation import (
    ALLOWED_MAP_IDS,
    APPROVED_GRASS_PATCHES,
    BOUNDARY_MAP_IDS,
    LANDMARKS,
    Position,
    approved_grass_patch_for_position,
    normalize_target,
)
from pokemon_player.memory_map import SPECIES_NAMES, dex_number_for_species_id
from pokemon_player.rom import RomFingerprint
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict
from pokemon_player.state_model import GameSnapshot
from pokemon_player.skills.visual_state import UiVisualState, inspect_ui_visual_state


PROMOTION_EVIDENCE_SCHEMA = "promotion_evidence_capture_v1"
PROMOTION_STEPS_SCHEMA = "promotion_evidence_collection_steps_v1"


def sanitize_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    if not cleaned:
        raise ValueError("Identifier cannot be empty.")
    return cleaned


SPECIES_FACT_ALIASES = {
    "weedle": "Weedle",
    "pikachu": "Pikachu",
    "kakuna": "Kakuna",
    "caterpie": "Caterpie",
    "pidgey": "Pidgey",
    "rattata": "Rattata",
    "spearow": "Spearow",
    "squirtle": "Squirtle",
    "nidoran f": "Nidoran F",
    "nidoran_f": "Nidoran F",
    "nidoran female": "Nidoran F",
    "nidoran m": "Nidoran M",
    "nidoran_m": "Nidoran M",
    "nidoran male": "Nidoran M",
}
SPECIES_ID_ALIASES = {species_id: name for species_id, name in SPECIES_NAMES.items()}
PARTY_SPECIES_NAMES = {"Spearow", "Squirtle", "Nidoran F", "Nidoran M"}
MOVE_FACT_ALIASES = {
    "bubble": "Bubble",
    "growl": "Growl",
    "horn attack": "Horn Attack",
    "horn_attack": "Horn Attack",
    "hyper beam": "Hyper Beam",
    "hyper_beam": "Hyper Beam",
    "hyperbeam": "Hyper Beam",
    "leer": "Leer",
    "peck": "Peck",
    "poison sting": "Poison Sting",
    "poison_sting": "Poison Sting",
    "quick attack": "Quick Attack",
    "quick_attack": "Quick Attack",
    "scratch": "Scratch",
    "string shot": "String Shot",
    "string_shot": "String Shot",
    "tackle": "Tackle",
    "tail whip": "Tail Whip",
    "tail_whip": "Tail Whip",
    "tailwhip": "Tail Whip",
    "thundershock": "ThunderShock",
    "thunder shock": "ThunderShock",
    "thunder_shock": "ThunderShock",
    "thunder wave": "Thunder Wave",
    "thunder_wave": "Thunder Wave",
    "water gun": "Water Gun",
    "water_gun": "Water Gun",
    "watergun": "Water Gun",
}
ITEM_FACT_ALIASES = {
    "antidote": "Antidote",
    "great ball": "Great Ball",
    "great_ball": "Great Ball",
    "greatball": "Great Ball",
    "master ball": "Master Ball",
    "master_ball": "Master Ball",
    "masterball": "Master Ball",
    "pokeball": "Poke Ball",
    "poke ball": "Poke Ball",
    "poke_ball": "Poke Ball",
    "poké ball": "Poke Ball",
    "potion": "Potion",
    "super potion": "Super Potion",
    "super_potion": "Super Potion",
    "superpotion": "Super Potion",
    "town map": "Town Map",
    "town_map": "Town Map",
    "townmap": "Town Map",
    "ultra ball": "Ultra Ball",
    "ultra_ball": "Ultra Ball",
    "ultraball": "Ultra Ball",
}
MVP_BATTLE_USABLE_ITEMS = {
    "Antidote",
    "Great Ball",
    "Master Ball",
    "Poke Ball",
    "Potion",
    "Super Potion",
    "Ultra Ball",
}

BATTLE_ENEMY_FACT_PROMOTIONS = {"battle_enemy_facts", "battle-enemy-facts"}
BATTLE_MENU_FACT_PROMOTIONS = {
    "battle_menu_and_cursor_detection",
    "battle-menu-and-cursor-detection",
}
BATTLE_MOVE_SELECTION_PROMOTIONS = {
    "battle_move_selection_and_result",
    "battle-move-selection-and-result",
}
BATTLE_DIALOGUE_ADVANCEMENT_PROMOTIONS = {
    "battle_dialogue_advancement_contract",
    "battle-dialogue-advancement-contract",
}
MODE_UI_STATE_PROMOTIONS = {
    "mode_and_ui_state_classification",
    "mode-and-ui-state-classification",
}
CAPSULE_SUCCESS_TARGET_OWNERSHIP_PROMOTIONS = {
    "capsule_success_target_ownership",
    "capsule-success-target-ownership",
}
PARTY_SWITCH_ACTIVE_BATTLER_PROMOTIONS = {
    "party_switch_and_active_battler",
    "party-switch-and-active-battler",
}
ITEM_USE_BAG_SELECTION_PROMOTIONS = {
    "item_use_and_bag_selection",
    "item-use-and-bag-selection",
}
CAPSULE_A_REGION_PROMOTIONS = {
    "capsule_a_region_and_landmarks",
    "capsule-a-region-and-landmarks",
}
GRASS_PATCH_ENCOUNTER_PROMOTIONS = {
    "grass_patch_and_encounter_search",
    "grass-patch-and-encounter-search",
}
CAPSULE_A_BOUNDARY_FIXTURES = {
    "route_22_grass": Position(0x21, 33, 11),
    "pewter_city_start": Position(0x02, 18, 31),
}
CAPSULE_A_LANDMARK_ALIASES = {
    "route_2_corridor": "viridian_city_north_corridor",
    "route_2_north_exit_threshold": "route_2_south_gate_threshold",
    "viridan_forest_south_gate_from_south": "viridian_forest_south_gate_from_south",
}


def promotion_evidence_record(
    *,
    promotion_id: str,
    step_number: int,
    step_title: str,
    evidence_id: str,
    label: str,
    expected_observation: str,
    rom: RomFingerprint,
    state_file: Path,
    screenshot_file: Path | None,
    snapshot: GameSnapshot,
    assertions: list[dict[str, Any]] | None = None,
    pokedex: dict[str, Any] | None = None,
    note: str = "",
) -> dict[str, Any]:
    record = {
        "schema": PROMOTION_EVIDENCE_SCHEMA,
        "promotion_id": promotion_id,
        "step_number": step_number,
        "step_title": step_title,
        "evidence_id": evidence_id,
        "label": label,
        "expected_observation": expected_observation,
        "created_utc": datetime.now(UTC).isoformat(),
        "note": note,
        "rom": {
            "path": str(rom.path),
            "title": rom.title,
            "size_bytes": rom.size_bytes,
            "md5": rom.md5,
            "sha256": rom.sha256,
        },
        "local_state_file": str(state_file),
        "screenshot_file": str(screenshot_file) if screenshot_file else None,
        "snapshot_hash": snapshot_hash(snapshot),
        "snapshot": snapshot_to_dict(snapshot),
        "assertions": assertions or [],
    }
    if pokedex:
        record["pokedex"] = pokedex
    enrich_derived_assertion_facts(record)
    enrich_visual_assertion_facts(record)
    return record


def write_promotion_evidence_record(record: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")


def load_promotion_steps(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    if record.get("schema") != PROMOTION_STEPS_SCHEMA:
        raise ValueError(f"{path} is not a {PROMOTION_STEPS_SCHEMA} record.")
    steps_by_promotion = record.get("steps_by_promotion", {})
    if not isinstance(steps_by_promotion, dict):
        return {}
    return {
        sanitize_id(promotion_id): list(steps)
        for promotion_id, steps in steps_by_promotion.items()
        if isinstance(steps, list)
    }


def get_promotion_step(
    steps_by_promotion: dict[str, list[dict[str, Any]]],
    promotion_id: str,
    step_number: int,
) -> dict[str, Any]:
    promotion_steps = steps_by_promotion.get(sanitize_id(promotion_id), [])
    if step_number < 1 or step_number > len(promotion_steps):
        raise ValueError(
            f"Promotion {promotion_id!r} does not have evidence step {step_number}. "
            f"Valid range is 1-{len(promotion_steps)}."
        )
    return promotion_steps[step_number - 1]


def attach_evidence_to_manifest(
    *,
    manifest_path: str | Path,
    repo_root: str | Path,
    promotion_id: str,
    metadata_path: str | Path,
    state_path: str | Path,
    screenshot_path: str | Path | None,
    evidence_id: str,
    label: str,
    expected_observation: str,
    notes: str,
) -> str:
    manifest_path = Path(manifest_path)
    repo_root = Path(repo_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    promotions = manifest.get("promotions", [])
    for promotion in promotions:
        if sanitize_id(str(promotion.get("id", ""))) == sanitize_id(promotion_id):
            refs = promotion.setdefault("verification_refs", [])
            reference = {
                "id": evidence_id,
                "label": label,
                "kind": "promotion_evidence",
                "metadata_path": repo_relative(repo_root, metadata_path),
                "state_path": repo_relative(repo_root, state_path),
                "expected_observation": expected_observation,
                "notes": notes,
            }
            if screenshot_path:
                reference["screenshot_path"] = repo_relative(repo_root, screenshot_path)
            existing_index = next(
                (index for index, item in enumerate(refs) if item.get("id") == evidence_id),
                None,
            )
            if existing_index is None:
                refs.append(reference)
                action = "attached"
            else:
                refs[existing_index] = reference
                action = "updated"
            promotion["review"] = {
                "reviewed_by": "promotion evidence capture",
                "reviewed_at": datetime.now(UTC).isoformat(),
                "notes": f"Evidence {evidence_id!r} {action}.",
            }
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            return action
    raise ValueError(f"Promotion {promotion_id!r} was not found in {manifest_path}.")


def repo_relative(repo_root: str | Path, value: str | Path) -> str:
    return Path(value).resolve().relative_to(Path(repo_root).resolve()).as_posix()


def infer_battle_enemy_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    assertions: list[dict[str, Any]] = [
        {
            "id": "mode_is_battle",
            "description": "State is a battle state.",
            "actual_path": "snapshot.mode",
            "op": "equals",
            "expected": "battle",
            "source": "human_visible",
        }
    ]

    enemy_token = ""
    for token, species in SPECIES_FACT_ALIASES.items():
        if token in text:
            enemy_token = token
            assertions.append(
                {
                    "id": "enemy_species_name",
                    "description": "Enemy species matches the human-visible battle.",
                    "actual_path": "snapshot.enemy.species_name",
                    "op": "equals",
                    "expected": species,
                    "source": "human_visible",
                }
            )
            break

    level_match = enemy_level_match(text, enemy_token) if enemy_token else None
    if level_match is None:
        level_match = re.search(r"(?:^|[^a-z0-9])(?:level|lv|l)[_\s-]*(\d{1,2})(?=$|[^a-z0-9])", text)
    if level_match:
        level_value = next(group for group in level_match.groups() if group is not None)
        assertions.append(
            {
                "id": "enemy_level",
                "description": "Enemy level matches the human-visible battle.",
                "actual_path": "snapshot.enemy.level",
                "op": "equals",
                "expected": int(level_value),
                "source": "human_visible",
            }
        )

    if any(token in text for token in ("low", "damaged", "weakened")):
        assertions.append(
            {
                "id": "enemy_hp_damaged",
                "description": "Enemy current HP is below max HP.",
                "actual_path": "snapshot.enemy.hp",
                "op": "less_than_path",
                "expected_path": "snapshot.enemy.max_hp",
                "source": "human_visible",
            }
        )
    elif any(token in text for token in ("full", "fullhealth", "full_health")):
        assertions.append(
            {
                "id": "enemy_hp_full",
                "description": "Enemy current HP is full.",
                "actual_path": "snapshot.enemy.hp",
                "op": "equals_path",
                "expected_path": "snapshot.enemy.max_hp",
                "source": "human_visible",
            }
        )
    return assertions


def enemy_level_match(text: str, enemy_token: str) -> re.Match[str] | None:
    escaped = re.escape(enemy_token)
    return re.search(
        rf"(?:level|lv|l)[_\s-]*(\d{{1,2}})[_\s-]*{escaped}|{escaped}[_\s-]*(?:level|lv|l)[_\s-]*(\d{{1,2}})",
        text,
    )


def infer_assertions_for_promotion(promotion_id: str, *texts: str) -> list[dict[str, Any]]:
    normalized = sanitize_id(promotion_id)
    if normalized in {sanitize_id(value) for value in BATTLE_ENEMY_FACT_PROMOTIONS}:
        return infer_battle_enemy_assertions(*texts)
    if normalized in {sanitize_id(value) for value in BATTLE_MOVE_SELECTION_PROMOTIONS}:
        return infer_battle_move_selection_assertions(*texts)
    if normalized in {sanitize_id(value) for value in BATTLE_DIALOGUE_ADVANCEMENT_PROMOTIONS}:
        return infer_battle_dialogue_advancement_assertions(*texts)
    if normalized in {sanitize_id(value) for value in BATTLE_MENU_FACT_PROMOTIONS}:
        return infer_battle_menu_assertions(*texts)
    if normalized in {sanitize_id(value) for value in MODE_UI_STATE_PROMOTIONS}:
        return infer_mode_ui_assertions(*texts)
    if normalized in {sanitize_id(value) for value in CAPSULE_SUCCESS_TARGET_OWNERSHIP_PROMOTIONS}:
        return infer_capsule_target_ownership_assertions(*texts)
    if normalized in {sanitize_id(value) for value in PARTY_SWITCH_ACTIVE_BATTLER_PROMOTIONS}:
        return infer_party_switch_active_battler_assertions(*texts)
    if normalized in {sanitize_id(value) for value in ITEM_USE_BAG_SELECTION_PROMOTIONS}:
        return infer_item_use_bag_selection_assertions(*texts)
    if normalized in {sanitize_id(value) for value in CAPSULE_A_REGION_PROMOTIONS}:
        return infer_capsule_a_region_assertions(*texts)
    if normalized in {sanitize_id(value) for value in GRASS_PATCH_ENCOUNTER_PROMOTIONS}:
        return infer_grass_patch_encounter_assertions(*texts)
    return []


def dedupe_assertions(assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for assertion in assertions:
        key = (
            str(assertion.get("id", "")),
            str(assertion.get("actual_path", "")),
            str(assertion.get("op", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(assertion)
    return deduped


def infer_battle_menu_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    assertions: list[dict[str, Any]] = [
        {
            "id": "mode_is_battle",
            "description": "State is a battle state.",
            "actual_path": "snapshot.mode",
            "op": "equals",
            "expected": "battle",
            "source": "human_visible",
        }
    ]

    kind = expected_battle_ui_kind(text)
    cursor = expected_battle_ui_cursor(text, kind)
    if kind:
        assertions.append(
            {
                "id": "battle_ui_kind",
                "description": "Visual classifier identifies the expected battle UI surface.",
                "actual_path": "visual.battle_ui.kind",
                "op": "equals",
                "expected": kind,
                "source": "human_visible",
            }
        )
    if cursor:
        assertions.append(
            {
                "id": "battle_ui_cursor",
                "description": "Visual classifier identifies the expected battle cursor.",
                "actual_path": "visual.battle_ui.cursor",
                "op": "equals",
                "expected": cursor,
                "source": "human_visible",
            }
        )
    return assertions


def infer_battle_dialogue_advancement_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    assertions = infer_battle_menu_assertions(*texts)

    if any(token in text for token in ("wild battle", "battle_type_raw=1", "battle type 1")):
        assertions.append(
            {
                "id": "battle_type_is_wild",
                "description": "Battle-dialogue evidence is an active wild battle.",
                "actual_path": "snapshot.battle_type_raw",
                "op": "equals",
                "expected": 1,
                "source": "battle_type",
            }
        )

    if any(token in text for token in ("safe next input is a", "advance with a", "press a")):
        assertions.append(
            {
                "id": "battle_dialogue_advances_with_a",
                "description": "The evidence labels this battle dialogue as safe for bounded A-press advancement.",
                "actual_path": "visual.battle_ui.kind",
                "op": "equals",
                "expected": "dialogue",
                "source": "human_visible",
            }
        )

    return dedupe_assertions(assertions)


def infer_battle_move_selection_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    assertions: list[dict[str, Any]] = [
        {
            "id": "mode_is_battle",
            "description": "State is a battle state.",
            "actual_path": "snapshot.mode",
            "op": "equals",
            "expected": "battle",
            "source": "human_visible",
        }
    ]
    if explicit_move_slot_mentioned(text):
        assertions.extend(
            assertion
            for assertion in infer_battle_menu_assertions(*texts)
            if assertion.get("id") != "mode_is_battle"
        )

    for move_name in expected_moveset_mentions(text):
        move_key = sanitize_id(move_name)
        assertions.append(
            {
                "id": f"active_moves_include_{move_key}",
                "description": f"Active battler moveset includes {move_name}.",
                "actual_path": "derived.active_move_names",
                "op": "contains",
                "expected": move_name,
                "source": "active_party_member_moves",
            }
        )

    requested_move = expected_requested_move(text)
    if requested_move:
        move_key = sanitize_id(requested_move)
        if expected_requested_move_missing(text):
            assertions.append(
                {
                    "id": "requested_move_missing_from_active_moveset",
                    "description": f"Requested move {requested_move} is absent from the active battler moveset.",
                    "actual_path": "derived.active_move_names",
                    "op": "not_contains",
                    "expected": requested_move,
                    "source": "active_party_member_moves",
                }
            )
        else:
            assertions.append(
                {
                    "id": f"requested_move_{move_key}_present",
                    "description": f"Requested/selected move {requested_move} is present in the active battler moveset.",
                    "actual_path": f"derived.active_moves_by_name.{move_key}.move_name",
                    "op": "equals",
                    "expected": requested_move,
                    "source": "active_party_member_moves",
                }
            )
            if expected_requested_move_no_pp(text):
                assertions.append(
                    {
                        "id": f"requested_move_{move_key}_has_zero_pp",
                        "description": f"Requested move {requested_move} has 0 PP and should be blocked.",
                        "actual_path": f"derived.active_moves_by_name.{move_key}.pp",
                        "op": "equals",
                        "expected": 0,
                        "source": "active_party_member_moves",
                    }
                )

    return dedupe_assertions(assertions)


def infer_party_switch_active_battler_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    assertions = [*infer_battle_menu_assertions(*texts)]
    if any(token in text for token in ("enemy", "fighting", "against", "wild", "used attack")):
        assertions.extend(infer_battle_enemy_assertions(*texts))

    active_species = expected_active_species(text)
    if active_species:
        assertions.append(
            {
                "id": "active_party_species",
                "description": "Active battler species matches the human-visible switch/baseline evidence.",
                "actual_path": "snapshot.active_party_member.species_name",
                "op": "equals",
                "expected": active_species,
                "source": "active_party_index",
            }
        )

    for species_name in expected_party_species_mentions(text):
        species_key = sanitize_id(species_name)
        assertions.append(
            {
                "id": f"party_contains_{species_key}",
                "description": f"Party contains the human-visible Pokemon {species_name}.",
                "actual_path": f"derived.party_by_species.{species_key}.species_name",
                "op": "equals",
                "expected": species_name,
                "source": "party_struct",
            }
        )

        if species_is_described_as_fainted(text, species_name):
            assertions.append(
                {
                    "id": f"party_{species_key}_is_fainted",
                    "description": f"Party member {species_name} is fainted as described by evidence.",
                    "actual_path": f"derived.party_by_species.{species_key}.hp",
                    "op": "equals",
                    "expected": 0,
                    "source": "party_struct",
                }
            )

    return dedupe_assertions(assertions)


def infer_item_use_bag_selection_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    assertions: list[dict[str, Any]] = [
        {
            "id": "mode_is_battle",
            "description": "State is a battle state.",
            "actual_path": "snapshot.mode",
            "op": "equals",
            "expected": "battle",
            "source": "human_visible",
        }
    ]

    if expected_battle_ui_kind(text) == "item_menu" or "battle bag" in text:
        assertions.append(
            {
                "id": "battle_ui_kind",
                "description": "Visual classifier identifies the battle item menu surface.",
                "actual_path": "visual.battle_ui.kind",
                "op": "equals",
                "expected": "item_menu",
                "source": "human_visible",
            }
        )

    for item_name in expected_item_mentions(text):
        item_key = sanitize_id(item_name)
        assertions.append(
            {
                "id": f"inventory_contains_{item_key}",
                "description": f"Inventory contains {item_name}.",
                "actual_path": f"derived.inventory_by_name.{item_key}.item_name",
                "op": "equals",
                "expected": item_name,
                "source": "inventory_struct",
            }
        )
        quantity = expected_item_quantity(text, item_name)
        if quantity is not None:
            assertions.append(
                {
                    "id": f"inventory_{item_key}_quantity",
                    "description": f"Inventory count for {item_name} matches the evidence.",
                    "actual_path": f"derived.inventory_by_name.{item_key}.quantity",
                    "op": "equals",
                    "expected": quantity,
                    "source": "inventory_struct",
                }
            )

    selected_item = expected_selected_item(text)
    if selected_item:
        item_key = sanitize_id(selected_item)
        assertions.append(
            {
                "id": f"selected_item_{item_key}_present",
                "description": f"Selected item claim references an inventory item, {selected_item}.",
                "actual_path": f"derived.inventory_by_name.{item_key}.item_name",
                "op": "equals",
                "expected": selected_item,
                "source": "inventory_struct",
            }
        )
        if expected_item_invalid_for_battle(text):
            assertions.append(
                {
                    "id": f"selected_item_{item_key}_not_battle_usable",
                    "description": f"{selected_item} is not in the MVP battle item whitelist.",
                    "actual_path": f"derived.inventory_by_name.{item_key}.usable_in_battle",
                    "op": "equals",
                    "expected": False,
                    "source": "mvp_item_whitelist",
                }
            )

    if any(token in text for token in ("no pokeball", "no pokeballs", "no poke balls", "no poke ball")):
        assertions.append(
            {
                "id": "inventory_no_poke_ball",
                "description": "Inventory has no Poke Ball entry available.",
                "actual_path": "derived.inventory_names",
                "op": "not_contains",
                "expected": "Poke Ball",
                "source": "inventory_struct",
            }
        )

    return dedupe_assertions(assertions)


def infer_capsule_a_region_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    position = expected_capsule_a_position(text)
    assertions: list[dict[str, Any]] = [
        {
            "id": "snapshot_mode_overworld",
            "description": "Capsule A region landmarks are stable overworld states.",
            "actual_path": "snapshot.mode",
            "op": "equals",
            "expected": "overworld",
            "source": "inspector",
        }
    ]
    if position is None:
        return assertions

    allowed = position.map_id in ALLOWED_MAP_IDS
    boundary = position.map_id in BOUNDARY_MAP_IDS
    assertions.extend(
        [
            {
                "id": "landmark_map_id",
                "description": "Landmark map id matches the approved Capsule A evidence point.",
                "actual_path": "snapshot.position.map_id",
                "op": "equals",
                "expected": position.map_id,
                "source": "human_labeled_landmark",
            },
            {
                "id": "landmark_x",
                "description": "Landmark x coordinate matches the approved Capsule A evidence point.",
                "actual_path": "snapshot.position.x",
                "op": "equals",
                "expected": position.x,
                "source": "human_labeled_landmark",
            },
            {
                "id": "landmark_y",
                "description": "Landmark y coordinate matches the approved Capsule A evidence point.",
                "actual_path": "snapshot.position.y",
                "op": "equals",
                "expected": position.y,
                "source": "human_labeled_landmark",
            },
            {
                "id": "capsule_a_allowed_region",
                "description": "Landmark is classified as inside or outside the Capsule A region.",
                "actual_path": "derived.capsule_a_region.allowed",
                "op": "equals",
                "expected": allowed,
                "source": "capsule_region_contract",
            },
            {
                "id": "capsule_a_boundary_region",
                "description": "Boundary examples are explicitly marked as rejected maps.",
                "actual_path": "derived.capsule_a_region.boundary",
                "op": "equals",
                "expected": boundary,
                "source": "capsule_region_contract",
            },
        ]
    )
    return assertions


def infer_grass_patch_encounter_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    normalized = sanitize_id(text)
    assertions: list[dict[str, Any]] = []

    if "wild_battle" in normalized or "wild battle" in text or "encounter" in text:
        assertions.extend(
            [
                {
                    "id": "mode_is_battle",
                    "description": "Encounter evidence is an active battle state.",
                    "actual_path": "snapshot.mode",
                    "op": "equals",
                    "expected": "battle",
                    "source": "inspector",
                },
                {
                    "id": "battle_type_is_wild",
                    "description": "Encounter evidence is specifically a wild battle.",
                    "actual_path": "snapshot.battle_type_raw",
                    "op": "equals",
                    "expected": 1,
                    "source": "battle_type",
                },
                {
                    "id": "encounter_started_in_approved_grass",
                    "description": "The last recorded overworld coordinate is inside an approved grass patch.",
                    "actual_path": "derived.grass_search.in_approved_grass",
                    "op": "equals",
                    "expected": True,
                    "source": "approved_patch_geometry",
                },
            ]
        )
    else:
        assertions.append(
            {
                "id": "mode_is_overworld",
                "description": "Grass-search setup evidence is a stable overworld state.",
                "actual_path": "snapshot.mode",
                "op": "equals",
                "expected": "overworld",
                "source": "inspector",
            }
        )

    if "blocked_not_near_grass" in normalized or "not_near_grass" in normalized:
        assertions.extend(
            [
                {
                    "id": "not_near_approved_grass",
                    "description": "Blocked setup is outside the supported approved grass patch surface.",
                    "actual_path": "derived.grass_search.near_approved_grass",
                    "op": "equals",
                    "expected": False,
                    "source": "approved_patch_geometry",
                },
                {
                    "id": "not_in_approved_grass",
                    "description": "Blocked setup is not standing inside approved grass.",
                    "actual_path": "derived.grass_search.in_approved_grass",
                    "op": "equals",
                    "expected": False,
                    "source": "approved_patch_geometry",
                },
            ]
        )
    elif "near_viridian_approved_grass" in normalized:
        assertions.extend(
            [
                {
                    "id": "near_approved_grass",
                    "description": "Near setup can enter the supported approved grass patch.",
                    "actual_path": "derived.grass_search.near_approved_grass",
                    "op": "equals",
                    "expected": True,
                    "source": "approved_patch_geometry",
                },
                {
                    "id": "not_yet_in_approved_grass",
                    "description": "Near setup starts adjacent to, not inside, the approved grass patch.",
                    "actual_path": "derived.grass_search.in_approved_grass",
                    "op": "equals",
                    "expected": False,
                    "source": "approved_patch_geometry",
                },
                {
                    "id": "target_patch_is_south_grass",
                    "description": "Near setup is associated with the promoted Viridian Forest south grass patch.",
                    "actual_path": "derived.grass_search.approved_patch_id",
                    "op": "equals",
                    "expected": "viridian_forest_south_grass",
                    "source": "approved_patch_geometry",
                },
            ]
        )
    elif "standing_in_viridian_approved_grass" in normalized or "wild_battle_in_approved_grass" in normalized:
        assertions.extend(
            [
                {
                    "id": "in_approved_grass",
                    "description": "Setup/encounter coordinate is inside the supported approved grass patch.",
                    "actual_path": "derived.grass_search.in_approved_grass",
                    "op": "equals",
                    "expected": True,
                    "source": "approved_patch_geometry",
                },
                {
                    "id": "target_patch_is_south_grass",
                    "description": "Evidence uses the promoted Viridian Forest south grass patch.",
                    "actual_path": "derived.grass_search.approved_patch_id",
                    "op": "equals",
                    "expected": "viridian_forest_south_grass",
                    "source": "approved_patch_geometry",
                },
            ]
        )

    return dedupe_assertions(assertions)


def expected_capsule_a_position(text: str) -> Position | None:
    normalized = sanitize_id(text)
    for alias, landmark_id in CAPSULE_A_LANDMARK_ALIASES.items():
        if alias in normalized:
            return LANDMARKS[landmark_id].position
    for landmark_id, landmark in sorted(LANDMARKS.items(), key=lambda item: len(item[0]), reverse=True):
        if landmark_id in normalized:
            return landmark.position
    for boundary_id, position in sorted(
        CAPSULE_A_BOUNDARY_FIXTURES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if boundary_id in normalized:
            return position

    alias = normalize_target(normalized)
    if alias in LANDMARKS:
        return LANDMARKS[alias].position
    return None


def infer_mode_ui_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    assertions: list[dict[str, Any]] = []

    mode = expected_snapshot_mode(text)
    if mode:
        assertions.append(
            {
                "id": "snapshot_mode",
                "description": "Inspector snapshot mode matches the expected mode contract.",
                "actual_path": "snapshot.mode",
                "op": "equals",
                "expected": mode,
                "source": "inspector",
            }
        )

    bottom_text_box = expected_bottom_text_box(text)
    if bottom_text_box is not None:
        assertions.append(
            {
                "id": "visual_bottom_text_box",
                "description": "Visual classifier identifies bottom text box presence.",
                "actual_path": "visual.ui.bottom_text_box",
                "op": "equals",
                "expected": bottom_text_box,
                "source": "human_visible",
            }
        )

    upper_menu = expected_upper_menu(text)
    if upper_menu is not None:
        assertions.append(
            {
                "id": "visual_upper_menu",
                "description": "Visual classifier identifies upper menu presence.",
                "actual_path": "visual.ui.upper_menu",
                "op": "equals",
                "expected": upper_menu,
                "source": "human_visible",
            }
        )

    if "stale" in text:
        assertions.append(
            {
                "id": "stale_flag_warning",
                "description": "Inspector records the stale text/menu WRAM warning.",
                "actual_path": "snapshot.warnings.0",
                "op": "contains",
                "expected": "stale text/menu WRAM flags",
                "source": "inspector",
            }
        )

    if "battle action menu" in text:
        assertions.append(
            {
                "id": "battle_ui_kind",
                "description": "Visual classifier identifies the battle action menu.",
                "actual_path": "visual.battle_ui.kind",
                "op": "equals",
                "expected": "action_menu",
                "source": "human_visible",
            }
        )
    return assertions


def infer_capsule_target_ownership_assertions(*texts: str) -> list[dict[str, Any]]:
    text = " ".join(texts).lower()
    target = target_species_from_text(text)
    if target is None:
        return []

    species_name, species_id = target
    dex_number = dex_number_for_species_id(species_id)
    if dex_number is None:
        return []

    expected_owned = expected_target_owned(text)
    if expected_owned is None:
        return []

    return [
        {
            "id": f"target_{sanitize_id(species_name)}_pokedex_owned",
            "description": f"Pokedex-owned flag for target species {species_name} matches capsule success expectation.",
            "actual_path": f"pokedex.by_dex_number.{dex_number}.owned",
            "op": "equals",
            "expected": expected_owned,
            "source": "pokedex_owned_bit",
        },
        {
            "id": f"target_{sanitize_id(species_name)}_mapping",
            "description": f"Pokedex entry {dex_number} maps to target species {species_name}.",
            "actual_path": f"pokedex.by_dex_number.{dex_number}.species_name",
            "op": "equals",
            "expected": species_name,
            "source": "species_mapping",
        },
    ]


def target_species_from_text(text: str) -> tuple[str, int] | None:
    for token, species_name in SPECIES_FACT_ALIASES.items():
        if token in text:
            species_id = next(
                (
                    candidate_id
                    for candidate_id, candidate_name in SPECIES_ID_ALIASES.items()
                    if candidate_name == species_name
                ),
                None,
            )
            if species_id is not None:
                return species_name, species_id
    return None


def expected_target_owned(text: str) -> bool | None:
    if any(token in text for token in ("un-owned", "unowned", "not owned", "not already owned", "before")):
        return False
    if any(token in text for token in ("pokedex owned", "owned", "caught", "captured", "after")):
        return True
    return None


def expected_active_species(text: str) -> str | None:
    if "after switching to" in text or "switched to" in text:
        for token, species_name in SPECIES_FACT_ALIASES.items():
            if species_name in PARTY_SPECIES_NAMES and token in text:
                return species_name
    if "active" in text:
        for token, species_name in SPECIES_FACT_ALIASES.items():
            if species_name in PARTY_SPECIES_NAMES and token in text:
                return species_name
    return None


def expected_party_species_mentions(text: str) -> list[str]:
    species: list[str] = []
    party_context = any(
        token in text
        for token in (
            "party",
            "cursor on",
            "cursor selected",
            "selected",
            "active",
            "switching to",
            "switched to",
            "after switching to",
            "fainted",
        )
    )
    if not party_context:
        return species
    for token, species_name in SPECIES_FACT_ALIASES.items():
        if species_name in PARTY_SPECIES_NAMES and token in text and species_name not in species:
            species.append(species_name)
    return species


def species_is_described_as_fainted(text: str, species_name: str) -> bool:
    token = sanitize_id(species_name).replace("_", " ")
    compact = sanitize_id(species_name)
    patterns = (
        f"{token} fainted",
        f"{token} is fainted",
        f"{token} (fainted)",
        f"{token} was fainted",
        f"fainted {token}",
        f"{compact} fainted",
        f"{compact} is fainted",
        f"{compact} (fainted)",
        f"fainted {compact}",
    )
    return any(pattern in text for pattern in patterns)


def expected_item_mentions(text: str) -> list[str]:
    items: list[str] = []
    item_context = any(
        token in text
        for token in (
            "bag",
            "inventory",
            "item",
            "cursor",
            "selected",
            "x1",
            "x2",
            "x3",
            "x4",
            "x5",
            "invalid",
            "not-now",
            "not now",
        )
    )
    if not item_context:
        return items
    for token, item_name in ITEM_FACT_ALIASES.items():
        if item_token_present(text, token) and item_name not in items:
            items.append(item_name)
    return items


def expected_selected_item(text: str) -> str | None:
    for phrase in ("cursor is on", "cursor on", "selected", "selecting"):
        index = text.find(phrase)
        if index < 0:
            continue
        snippet = text[index : index + 100]
        for token, item_name in ITEM_FACT_ALIASES.items():
            if item_token_present(snippet, token):
                return item_name
    for token, item_name in ITEM_FACT_ALIASES.items():
        if item_token_present(text, token):
            return item_name
    return None


def expected_item_quantity(text: str, item_name: str) -> int | None:
    aliases = [token for token, name in ITEM_FACT_ALIASES.items() if name == item_name]
    for token in aliases:
        pattern = item_token_pattern(token)
        after_match = re.search(rf"{pattern}\s*x\s*(\d{{1,2}})", text)
        if after_match:
            return int(after_match.group(1))
        before_match = re.search(rf"(\d{{1,2}})\s*{pattern}", text)
        if before_match:
            return int(before_match.group(1))
    return None


def expected_item_invalid_for_battle(text: str) -> bool:
    return any(token in text for token in ("invalid item", "non-battle item", "invalid for battle", "not-now", "not now"))


def item_token_present(text: str, token: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){item_token_pattern(token)}(?![a-z0-9])", text) is not None


def item_token_pattern(token: str) -> str:
    parts = [part for part in re.split(r"[\s_]+", token.strip().lower()) if part]
    return r"[\s_-]+".join(re.escape(part) for part in parts)


def expected_moveset_mentions(text: str) -> list[str]:
    if expected_requested_move_missing(text):
        return []

    moves: list[str] = []
    moveset_context = any(
        token in text
        for token in (
            "moves are",
            "moves include",
            "moveset",
            "move list",
            "active moves",
            "active-moves",
        )
    )
    selected_move_context = any(
        token in text
        for token in (
            "selected",
            "cursor on",
            "requested move",
            "target move",
            "use_move",
            "use move",
        )
    )
    if not moveset_context and not selected_move_context:
        return moves

    for token, move_name in MOVE_FACT_ALIASES.items():
        if move_token_present(text, token) and move_name not in moves:
            moves.append(move_name)
    return moves


def expected_requested_move(text: str) -> str | None:
    request_context = any(
        token in text
        for token in (
            "requested move",
            "target move",
            "use_move",
            "use move",
            "selected",
            "cursor on",
            "missing",
            "absent",
            "not in",
            "0 pp",
            "no pp",
        )
    )
    if not request_context:
        return None

    for token, move_name in MOVE_FACT_ALIASES.items():
        if move_token_present(text, token):
            return move_name
    return None


def expected_requested_move_missing(text: str) -> bool:
    return any(
        token in text
        for token in (
            "missing",
            "absent",
            "not in",
            "not learned",
            "does not know",
            "doesn't know",
            "wouldn't have learned",
            "would not have learned",
            "unavailable",
        )
    )


def expected_requested_move_no_pp(text: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])0\s*pp(?![a-z0-9])", text)) or any(
        token in text for token in ("no pp", "out of pp", "zero pp")
    )


def explicit_move_slot_mentioned(text: str) -> bool:
    return any(
        token in text
        for token in (
            "slot 1",
            "slot_1",
            "move slot 1",
            "move 1",
            "move_1",
            "slot 2",
            "slot_2",
            "move slot 2",
            "move 2",
            "move_2",
            "slot 3",
            "slot_3",
            "move slot 3",
            "move 3",
            "move_3",
            "slot 4",
            "slot_4",
            "move slot 4",
            "move 4",
            "move_4",
        )
    )


def move_token_present(text: str, token: str) -> bool:
    parts = [part for part in re.split(r"[\s_]+", token.strip().lower()) if part]
    if not parts:
        return False
    pattern = r"[\s_-]+".join(re.escape(part) for part in parts)
    return re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", text) is not None


def expected_snapshot_mode(text: str) -> str | None:
    mode_patterns = [
        ("overworld", ("mode is overworld", "snapshot reports overworld", "clean overworld")),
        ("battle", ("mode is battle", "snapshot reports battle", "battle mode", "battle action menu")),
        ("dialogue", ("mode is dialogue", "snapshot reports dialogue", "dialogue mode")),
        ("menu", ("mode is menu", "snapshot reports menu", "snapshot mode remains menu", "menu mode")),
    ]
    for mode, patterns in mode_patterns:
        if any(pattern in text for pattern in patterns):
            return mode
    return None


def expected_bottom_text_box(text: str) -> bool | None:
    if any(pattern in text for pattern in ("no bottom text box", "no text box", "without text box")):
        return False
    if any(pattern in text for pattern in ("bottom text box", "text box is visible", "dialogue textbox")):
        return True
    return None


def expected_upper_menu(text: str) -> bool | None:
    if any(pattern in text for pattern in ("no upper menu", "no menu", "without menu")):
        return False
    if any(pattern in text for pattern in ("upper menu", "bag menu", "start menu")):
        return True
    return None


def expected_battle_ui_kind(text: str) -> str | None:
    if any(token in text for token in ("party_menu", "party menu", "pokemon menu", "pokémon menu")):
        return "party_menu"
    if any(token in text for token in ("item_menu", "item menu", "item-menu")):
        return "item_menu"
    if any(token in text for token in ("move_menu", "move menu", "move-menu")):
        return "move_menu"
    if any(token in text for token in ("action_menu", "action menu", "top level battle menu", "pre-action")):
        return "action_menu"
    if "dialogue" in text:
        return "dialogue"
    return None


def expected_battle_ui_cursor(text: str, kind: str | None) -> str | None:
    if kind == "action_menu":
        if "item" in text:
            return "item"
        if "pkmn" in text or "pokemon" in text:
            return "pkmn"
        if "run" in text:
            return "run"
        if "fight" in text or "default" in text or "pre-action" in text:
            return "fight"
    if kind == "move_menu":
        if any(token in text for token in ("slot 1", "slot_1", "move slot 1", "move 1", "move_1")):
            return "move_1"
        if any(token in text for token in ("slot 2", "slot_2", "move slot 2", "move 2", "move_2")):
            return "move_2"
        if any(token in text for token in ("slot 3", "slot_3", "move slot 3", "move 3", "move_3")):
            return "move_3"
        if any(token in text for token in ("slot 4", "slot_4", "move slot 4", "move 4", "move_4")):
            return "move_4"
        if "move_2" in text:
            return "move_2"
        if "move_3" in text:
            return "move_3"
        if "move_4" in text:
            return "move_4"
        if "move_1" in text or "default" in text:
            return "move_1"
    return None


def enrich_derived_assertion_facts(record: dict[str, Any]) -> dict[str, Any]:
    snapshot = record.get("snapshot")
    if not isinstance(snapshot, dict):
        return record
    derived = record.setdefault("derived", {})
    if not isinstance(derived, dict):
        return record

    party_by_species: dict[str, dict[str, Any]] = {}
    party_by_slot: dict[str, dict[str, Any]] = {}
    inventory_by_name: dict[str, dict[str, Any]] = {}
    inventory_names: list[str] = []
    for member in snapshot.get("party", []):
        if not isinstance(member, dict):
            continue
        species = member.get("species_name")
        slot = member.get("slot")
        if isinstance(species, str):
            party_by_species[sanitize_id(species)] = member
        if isinstance(slot, int):
            party_by_slot[f"slot_{slot}"] = member

    for index, item in enumerate(snapshot.get("inventory", []), start=1):
        if not isinstance(item, dict):
            continue
        item_name = item.get("item_name")
        if not isinstance(item_name, str):
            continue
        inventory_names.append(item_name)
        inventory_by_name[sanitize_id(item_name)] = {
            **item,
            "slot": index,
            "usable_in_battle": item_name in MVP_BATTLE_USABLE_ITEMS,
        }

    derived["party_by_species"] = party_by_species
    derived["party_by_slot"] = party_by_slot
    derived["inventory_by_name"] = inventory_by_name
    derived["inventory_names"] = inventory_names
    position = snapshot.get("position")
    if isinstance(position, dict):
        map_id = position.get("map_id")
        x = position.get("x")
        y = position.get("y")
        if all(isinstance(value, int) for value in (map_id, x, y)):
            current = Position(int(map_id), int(x), int(y))
            landmark_id = next(
                (
                    landmark.id
                    for landmark in LANDMARKS.values()
                    if landmark.position == current
                ),
                None,
            )
            derived["capsule_a_region"] = {
                "allowed": current.map_id in ALLOWED_MAP_IDS,
                "boundary": current.map_id in BOUNDARY_MAP_IDS,
                "landmark_id": landmark_id,
                "position": current.format(),
            }
            patch = approved_grass_patch_for_position(current)
            derived["grass_search"] = {
                "approved_patch_id": patch.id if patch else None,
                "approved_patch_label": patch.label if patch else None,
                "in_approved_grass": patch.contains(current) if patch else False,
                "near_approved_grass": patch.is_near(current) if patch else False,
                "patch_bounds": patch.format_bounds() if patch else None,
                "supported_patch_ids": sorted(APPROVED_GRASS_PATCHES),
            }
    active = snapshot.get("active_party_member")
    if isinstance(active, dict):
        derived["active_species"] = active.get("species_name")
        derived["active_party_slot"] = snapshot.get("active_party_slot")
        active_move_names: list[str] = []
        active_moves_by_name: dict[str, dict[str, Any]] = {}
        for index, move in enumerate(active.get("moves", []), start=1):
            if not isinstance(move, dict):
                continue
            move_name = move.get("move_name")
            if not isinstance(move_name, str) or move_name == "No Move":
                continue
            active_move_names.append(move_name)
            active_moves_by_name[sanitize_id(move_name)] = {**move, "slot": index}
        derived["active_move_names"] = active_move_names
        derived["active_moves_by_name"] = active_moves_by_name
    return record


def enrich_visual_assertion_facts(record: dict[str, Any]) -> dict[str, Any]:
    screenshot = record.get("screenshot_file")
    if not isinstance(screenshot, str) or not screenshot:
        return record
    screenshot_path = Path(screenshot)
    if not screenshot_path.exists():
        return record
    try:
        ui_visual = inspect_ui_visual_state(screenshot_path)
        ui = inspect_battle_ui_screenshot(screenshot_path)
    except Exception as exc:
        record.setdefault("visual_warnings", []).append(
            f"Could not inspect battle UI screenshot {screenshot_path}: {exc}"
        )
        return record
    record.setdefault("visual", {})["ui"] = ui_visual_to_dict(ui_visual)
    record.setdefault("visual", {})["battle_ui"] = battle_ui_to_dict(ui)
    return record


def battle_ui_to_dict(ui: BattleUiState) -> dict[str, str]:
    return {"kind": ui.kind, "cursor": ui.cursor}


def ui_visual_to_dict(ui: UiVisualState) -> dict[str, bool]:
    return {"bottom_text_box": ui.bottom_text_box, "upper_menu": ui.upper_menu}


def evaluate_assertions(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [evaluate_assertion(record, assertion) for assertion in record.get("assertions", [])]


def evaluate_assertion(record: dict[str, Any], assertion: dict[str, Any]) -> dict[str, Any]:
    actual = value_at_path(record, str(assertion.get("actual_path", "")))
    op = assertion.get("op")
    if op == "equals":
        expected = assertion.get("expected")
        passed = actual == expected
    elif op == "equals_path":
        expected = value_at_path(record, str(assertion.get("expected_path", "")))
        passed = actual == expected
    elif op == "less_than_path":
        expected = value_at_path(record, str(assertion.get("expected_path", "")))
        passed = isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual < expected
    elif op == "greater_than_path":
        expected = value_at_path(record, str(assertion.get("expected_path", "")))
        passed = isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual > expected
    elif op == "contains":
        expected = assertion.get("expected")
        if isinstance(actual, str):
            passed = isinstance(expected, str) and expected in actual
        elif isinstance(actual, list):
            passed = expected in actual
        else:
            passed = False
    elif op == "not_contains":
        expected = assertion.get("expected")
        if isinstance(actual, str):
            passed = isinstance(expected, str) and expected not in actual
        elif isinstance(actual, list):
            passed = expected not in actual
        else:
            passed = False
    else:
        expected = assertion.get("expected")
        passed = False

    return {
        "id": assertion.get("id", "assertion"),
        "description": assertion.get("description", ""),
        "actual_path": assertion.get("actual_path", ""),
        "op": op,
        "expected": expected,
        "actual": actual,
        "passed": passed,
    }


def value_at_path(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current
