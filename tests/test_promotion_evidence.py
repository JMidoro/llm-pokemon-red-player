from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.promotion_evidence_io import (
    attach_evidence_to_manifest,
    enrich_derived_assertion_facts,
    enrich_visual_assertion_facts,
    evaluate_assertions,
    infer_assertions_for_promotion,
    infer_battle_menu_assertions,
    infer_capsule_a_region_assertions,
    infer_capsule_target_ownership_assertions,
    infer_mode_ui_assertions,
)


ROOT = Path(__file__).resolve().parents[1]


def test_attach_evidence_to_manifest_adds_reference(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "mvp_skill_promotion_manifest_v1",
                "promotions": [
                    {
                        "id": "battle-enemy-facts",
                        "title": "Battle Enemy Facts",
                        "verification_refs": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    metadata_path = tmp_path / "research" / "promotions" / "evidence" / "battle-enemy-facts" / "weedle.json"
    state_path = tmp_path / "research" / "promotions" / "evidence" / "local" / "battle-enemy-facts" / "weedle.state"
    screenshot_path = state_path.with_suffix(".png")
    metadata_path.parent.mkdir(parents=True)
    state_path.parent.mkdir(parents=True)
    metadata_path.write_text("{}", encoding="utf-8")
    state_path.write_bytes(b"state")
    screenshot_path.write_bytes(b"png")

    action = attach_evidence_to_manifest(
        manifest_path=manifest_path,
        repo_root=tmp_path,
        promotion_id="battle-enemy-facts",
        metadata_path=metadata_path,
        state_path=state_path,
        screenshot_path=screenshot_path,
        evidence_id="weedle",
        label="Weedle battle",
        expected_observation="Wild Weedle battle is visible.",
        notes="Captured through unified workflow.",
    )

    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    refs = updated["promotions"][0]["verification_refs"]
    assert action == "attached"
    assert refs == [
        {
            "id": "weedle",
            "label": "Weedle battle",
            "kind": "promotion_evidence",
            "metadata_path": "research/promotions/evidence/battle-enemy-facts/weedle.json",
            "state_path": "research/promotions/evidence/local/battle-enemy-facts/weedle.state",
            "expected_observation": "Wild Weedle battle is visible.",
            "notes": "Captured through unified workflow.",
            "screenshot_path": "research/promotions/evidence/local/battle-enemy-facts/weedle.png",
        }
    ]


def test_attach_evidence_to_manifest_updates_existing_reference(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "mvp_skill_promotion_manifest_v1",
                "promotions": [
                    {
                        "id": "battle-enemy-facts",
                        "title": "Battle Enemy Facts",
                        "verification_refs": [{"id": "weedle", "label": "Old"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    metadata_path = tmp_path / "evidence.json"
    state_path = tmp_path / "evidence.state"

    action = attach_evidence_to_manifest(
        manifest_path=manifest_path,
        repo_root=tmp_path,
        promotion_id="battle-enemy-facts",
        metadata_path=metadata_path,
        state_path=state_path,
        screenshot_path=None,
        evidence_id="weedle",
        label="New Weedle battle",
        expected_observation="Updated observation.",
        notes="Updated notes.",
    )

    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    refs = updated["promotions"][0]["verification_refs"]
    assert action == "updated"
    assert len(refs) == 1
    assert refs[0]["label"] == "New Weedle battle"


def test_infer_battle_menu_assertions_for_pre_action_fight_menu():
    assertions = infer_battle_menu_assertions(
        "step_01_pre_action_wild_battle",
        "pre-action_wild_battle",
        'Top level battle menu. Cursor is on "Fight" (default)',
    )

    expected = {assertion["id"]: assertion for assertion in assertions}
    assert expected["mode_is_battle"]["expected"] == "battle"
    assert expected["battle_ui_kind"]["expected"] == "action_menu"
    assert expected["battle_ui_cursor"]["expected"] == "fight"


def test_infer_battle_dialogue_advancement_assertions_for_waiting_text():
    assertions = infer_assertions_for_promotion(
        "battle-dialogue-advancement-contract",
        "battle_dialogue_waiting",
        "Wild battle dialogue is visible. Safe next input is A.",
    )

    expected = {assertion["id"]: assertion for assertion in assertions}
    assert expected["mode_is_battle"]["expected"] == "battle"
    assert expected["battle_ui_kind"]["expected"] == "dialogue"
    assert expected["battle_type_is_wild"]["expected"] == 1
    assert expected["battle_dialogue_advances_with_a"]["expected"] == "dialogue"


def test_battle_dialogue_promotion_evidence_assertions_pass():
    evidence_dir = ROOT / "research" / "promotions" / "evidence" / "battle_dialogue_advancement_contract"
    evidence_files = sorted(evidence_dir.glob("*.promotion-evidence.json"))

    assert evidence_files
    for evidence_file in evidence_files:
        record = json.loads(evidence_file.read_text(encoding="utf-8"))
        assert record["assertions"]
        assert all(result["passed"] for result in evaluate_assertions(record))


def test_infer_battle_move_selection_assertions_for_slot_label():
    assertions = infer_assertions_for_promotion(
        "battle-move-selection-and-result",
        "move menu slot 3",
        "Move menu is visible and the cursor/requested move is on slot 3.",
    )

    expected = {assertion["id"]: assertion for assertion in assertions}
    assert expected["mode_is_battle"]["expected"] == "battle"
    assert expected["battle_ui_kind"]["expected"] == "move_menu"
    assert expected["battle_ui_cursor"]["expected"] == "move_3"


def test_battle_move_selection_assertions_check_requested_move_presence():
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": "",
        "snapshot": {
            "mode": "battle",
            "active_party_member": {
                "species_name": "Wartortle",
                "moves": [
                    {"slot": 1, "move_name": "Tackle", "pp": 35},
                    {"slot": 2, "move_name": "Tail Whip", "pp": 30},
                    {"slot": 3, "move_name": "Bubble", "pp": 30},
                    {"slot": 4, "move_name": "Water Gun", "pp": 25},
                ],
            },
        },
        "visual": {"battle_ui": {"kind": "move_menu", "cursor": "move_4"}},
        "assertions": infer_assertions_for_promotion(
            "battle-move-selection-and-result",
            "use_move water_gun",
            "Requested move Water Gun selected in move menu.",
        ),
    }

    enrich_derived_assertion_facts(record)
    expected = {assertion["id"]: assertion for assertion in record["assertions"]}
    assert expected["requested_move_water_gun_present"]["actual_path"] == (
        "derived.active_moves_by_name.water_gun.move_name"
    )
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_battle_move_selection_assertions_check_requested_move_missing():
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": "",
        "snapshot": {
            "mode": "battle",
            "active_party_member": {
                "species_name": "Wartortle",
                "moves": [
                    {"slot": 1, "move_name": "Tackle", "pp": 35},
                    {"slot": 2, "move_name": "Tail Whip", "pp": 30},
                    {"slot": 3, "move_name": "Bubble", "pp": 30},
                    {"slot": 4, "move_name": "Water Gun", "pp": 25},
                ],
            },
        },
        "assertions": infer_assertions_for_promotion(
            "battle-move-selection-and-result",
            "blocked_missing_hyper_beam",
            "Requested move Hyper Beam is missing from the active battler moveset.",
        ),
    }

    enrich_derived_assertion_facts(record)
    expected = {assertion["id"]: assertion for assertion in record["assertions"]}
    assert expected["requested_move_missing_from_active_moveset"]["op"] == "not_contains"
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_battle_move_selection_assertions_check_requested_move_zero_pp():
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": "",
        "snapshot": {
            "mode": "battle",
            "active_party_member": {
                "species_name": "Squirtle",
                "moves": [
                    {"slot": 1, "move_name": "Tackle", "pp": 0},
                    {"slot": 2, "move_name": "Tail Whip", "pp": 30},
                ],
            },
        },
        "assertions": infer_assertions_for_promotion(
            "battle-move-selection-and-result",
            "blocked_no_pp_tackle",
            "Requested move Tackle has 0 PP and should be blocked.",
        ),
    }

    enrich_derived_assertion_facts(record)
    expected = {assertion["id"]: assertion for assertion in record["assertions"]}
    assert expected["requested_move_tackle_has_zero_pp"]["expected"] == 0
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_item_use_bag_selection_assertions_check_battle_bag_inventory():
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": "",
        "snapshot": {
            "mode": "battle",
            "inventory": [
                {"slot": 1, "item_name": "Town Map", "quantity": 1},
                {"slot": 2, "item_name": "Poke Ball", "quantity": 4},
                {"slot": 3, "item_name": "Potion", "quantity": 1},
            ],
        },
        "visual": {"battle_ui": {"kind": "item_menu", "cursor": "unknown"}},
        "assertions": infer_assertions_for_promotion(
            "item-use-and-bag-selection",
            "battle_bag_pokeball",
            "In battle item menu. Town map, poke ball x4, potion x1. Cursor is on poke ball.",
        ),
    }

    enrich_derived_assertion_facts(record)
    expected = {assertion["id"]: assertion for assertion in record["assertions"]}
    assert expected["battle_ui_kind"]["expected"] == "item_menu"
    assert expected["inventory_poke_ball_quantity"]["expected"] == 4
    assert expected["inventory_potion_quantity"]["expected"] == 1
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_item_use_bag_selection_assertions_check_invalid_battle_item():
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": "",
        "snapshot": {
            "mode": "battle",
            "inventory": [
                {"slot": 1, "item_name": "Town Map", "quantity": 1},
                {"slot": 2, "item_name": "Poke Ball", "quantity": 4},
            ],
        },
        "visual": {"battle_ui": {"kind": "item_menu", "cursor": "unknown"}},
        "assertions": infer_assertions_for_promotion(
            "item-use-and-bag-selection",
            "battle_bag_town_map",
            "In battle item menu. Cursor on Town Map (invalid item for battle use).",
        ),
    }

    enrich_derived_assertion_facts(record)
    expected = {assertion["id"]: assertion for assertion in record["assertions"]}
    assert expected["selected_item_town_map_not_battle_usable"]["expected"] is False
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_infer_party_switch_assertions_for_active_baseline():
    assertions = infer_assertions_for_promotion(
        "party-switch-and-active-battler",
        "active_battler_baseline",
        'lv3 spearow active, fighting lv4 weedle. Cursor on "Fight" on top level battle menu.',
    )

    expected = {assertion["id"]: assertion for assertion in assertions}
    assert expected["mode_is_battle"]["expected"] == "battle"
    assert expected["battle_ui_kind"]["expected"] == "action_menu"
    assert expected["battle_ui_cursor"]["expected"] == "fight"
    assert expected["enemy_species_name"]["expected"] == "Weedle"
    assert expected["enemy_level"]["expected"] == 4
    assert expected["active_party_species"]["expected"] == "Spearow"
    assert expected["party_contains_spearow"]["actual_path"] == "derived.party_by_species.spearow.species_name"


def test_party_switch_assertions_use_derived_party_fainted_facts():
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": "",
        "snapshot": {
            "mode": "battle",
            "party": [
                {"slot": 1, "species_name": "Spearow", "hp": 0},
                {"slot": 2, "species_name": "Squirtle", "hp": 29},
            ],
        },
        "visual": {"battle_ui": {"kind": "party_menu", "cursor": "unknown"}},
        "assertions": infer_assertions_for_promotion(
            "party-switch-and-active-battler",
            "pokemon_menu_fainted_spearow",
            "In party menu. Cursor selected Spearow (Fainted)",
        ),
    }

    enrich_derived_assertion_facts(record)
    expected = {assertion["id"]: assertion for assertion in record["assertions"]}
    assert expected["party_spearow_is_fainted"]["actual_path"] == "derived.party_by_species.spearow.hp"
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_battle_menu_visual_assertions_pass_against_captured_screenshot():
    screenshot_path = (
        ROOT
        / "research"
        / "promotions"
        / "evidence"
        / "local"
        / "battle_menu_and_cursor_detection"
        / "step_01_pre_action_wild_battle.png"
    )
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": str(screenshot_path),
        "snapshot": {"mode": "battle"},
        "assertions": infer_battle_menu_assertions(
            "step_01_pre_action_wild_battle",
            "pre-action_wild_battle",
            'Top level battle menu. Cursor is on "Fight" (default)',
        ),
    }

    enrich_visual_assertion_facts(record)
    assert record["visual"]["battle_ui"] == {"kind": "action_menu", "cursor": "fight"}
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_infer_mode_ui_assertions_for_clean_overworld():
    assertions = infer_mode_ui_assertions(
        "mode-clean-overworld",
        "Clean overworld fixture",
        "Mode is overworld. No bottom text box. No upper menu.",
    )

    expected = {assertion["id"]: assertion for assertion in assertions}
    assert expected["snapshot_mode"]["expected"] == "overworld"
    assert expected["visual_bottom_text_box"]["expected"] is False
    assert expected["visual_upper_menu"]["expected"] is False


def test_mode_ui_visual_assertions_pass_against_existing_golden_screenshot():
    screenshot_path = ROOT / "research" / "golden-states" / "local" / "menu_open_bag_state.png"
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": str(screenshot_path),
        "snapshot": {"mode": "menu"},
        "assertions": infer_mode_ui_assertions(
            "mode-menu-bag",
            "Bag menu fixture",
            "Mode is menu. Upper menu is visible. No bottom text box.",
        ),
    }

    enrich_visual_assertion_facts(record)
    assert record["visual"]["ui"] == {"bottom_text_box": False, "upper_menu": True}
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_contains_assertion_matches_warning_substring():
    record = {
        "snapshot": {
            "warnings": ["Screen tiles indicate overworld despite stale text/menu WRAM flags."]
        },
        "assertions": [
            {
                "id": "stale_flag_warning",
                "actual_path": "snapshot.warnings.0",
                "op": "contains",
                "expected": "stale text/menu WRAM flags",
            }
        ],
    }

    assert evaluate_assertions(record)[0]["passed"]


def test_infer_capsule_target_before_uses_pokedex_owned_false():
    assertions = infer_capsule_target_ownership_assertions(
        "step_02_target_before_battle_pikachu",
        "target-before_battle_pikachu",
        "In a battle against un-owned weakened Pikachu",
    )

    expected = {assertion["id"]: assertion for assertion in assertions}
    assert expected["target_pikachu_pokedex_owned"]["actual_path"] == "pokedex.by_dex_number.25.owned"
    assert expected["target_pikachu_pokedex_owned"]["expected"] is False


def test_infer_capsule_target_after_uses_pokedex_owned_true():
    assertions = infer_capsule_target_ownership_assertions(
        "step_02_target_after_pikachu_caught",
        "target-after_pikachu_caught",
        "Post-capture Pikachu pokedex owned",
    )

    expected = {assertion["id"]: assertion for assertion in assertions}
    assert expected["target_pikachu_pokedex_owned"]["actual_path"] == "pokedex.by_dex_number.25.owned"
    assert expected["target_pikachu_pokedex_owned"]["expected"] is True


def test_infer_capsule_a_region_assertions_for_allowed_landmark():
    assertions = infer_capsule_a_region_assertions(
        "step_01_viridian_forest_grass_1",
        "viridian_forest_grass_1",
        "Each landmark has map id/name, x/y, screenshot, and state path.",
    )

    expected = {assertion["id"]: assertion for assertion in assertions}
    assert expected["snapshot_mode_overworld"]["expected"] == "overworld"
    assert expected["landmark_map_id"]["expected"] == 0x33
    assert expected["landmark_x"]["expected"] == 28
    assert expected["landmark_y"]["expected"] == 43
    assert expected["capsule_a_allowed_region"]["expected"] is True
    assert expected["capsule_a_boundary_region"]["expected"] is False


def test_capsule_a_region_assertions_mark_route_22_grass_approved():
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": "",
        "snapshot": {
            "mode": "overworld",
            "position": {
                "map_id": 0x21,
                "x": 33,
                "y": 11,
            },
        },
        "assertions": infer_assertions_for_promotion(
            "capsule-a-region-and-landmarks",
            "step_01_route_22_grass",
            "route 22 grass",
        ),
    }

    enrich_derived_assertion_facts(record)
    expected = {assertion["id"]: assertion for assertion in record["assertions"]}
    assert expected["capsule_a_allowed_region"]["expected"] is True
    assert expected["capsule_a_boundary_region"]["expected"] is False
    assert all(result["passed"] for result in evaluate_assertions(record))


def test_grass_patch_assertions_mark_near_inside_and_blocked_states():
    cases = [
        (
            "step_01_near_viridian_approved_grass",
            {"mode": "overworld", "position": {"map_id": 0x33, "x": 26, "y": 43}},
            "near_approved_grass",
            True,
        ),
        (
            "step_01_standing_in_viridian_approved_grass",
            {"mode": "overworld", "position": {"map_id": 0x33, "x": 28, "y": 43}},
            "in_approved_grass",
            True,
        ),
        (
            "step_01_blocked_not_near_grass",
            {"mode": "overworld", "position": {"map_id": 0x32, "x": 5, "y": 1}},
            "not_near_approved_grass",
            False,
        ),
    ]

    for evidence_id, snapshot, assertion_id, expected_value in cases:
        record = {
            "schema": "promotion_evidence_capture_v1",
            "screenshot_file": "",
            "snapshot": snapshot,
            "assertions": infer_assertions_for_promotion(
                "grass-patch-and-encounter-search",
                evidence_id,
                evidence_id.replace("_", " "),
            ),
        }
        enrich_derived_assertion_facts(record)
        expected = {assertion["id"]: assertion for assertion in record["assertions"]}
        assert expected[assertion_id]["expected"] == expected_value
        assert all(result["passed"] for result in evaluate_assertions(record))


def test_grass_patch_assertions_mark_wild_battle_from_approved_grass():
    record = {
        "schema": "promotion_evidence_capture_v1",
        "screenshot_file": "",
        "snapshot": {
            "mode": "battle",
            "battle_type_raw": 1,
            "position": {"map_id": 0x33, "x": 32, "y": 41},
        },
        "assertions": infer_assertions_for_promotion(
            "grass-patch-and-encounter-search",
            "step_01_wild_battle_in_approved_grass",
            "At the very beginning of the encounter.",
        ),
    }

    enrich_derived_assertion_facts(record)
    expected = {assertion["id"]: assertion for assertion in record["assertions"]}
    assert expected["battle_type_is_wild"]["expected"] == 1
    assert expected["encounter_started_in_approved_grass"]["expected"] is True
    assert all(result["passed"] for result in evaluate_assertions(record))
