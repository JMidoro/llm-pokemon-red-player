from __future__ import annotations

from scripts.run_local_gemma_chapter import (
    apply_chapter_skill_policy,
    default_active_battle_move,
    default_purchase_quantity,
    infer_missing_skill_args,
    normalize_selected_skill,
)
from scripts.chapter_segment_support import (
    missing_skill_argument_result,
    requested_success_reached,
)
from pokemon_player.chapter_direction import current_chapter_goal


def enabled_ids(skills: list[dict[str, object]]) -> set[str]:
    return {str(skill["id"]) for skill in skills}


def test_capsule_a_success_target_requires_pikachu_and_north_exit() -> None:
    at_exit = {
        "party": [{"species_name": "Pikachu"}],
        "position": {"map_id": 0x33, "x": 1, "y": 0},
    }
    in_grass = {
        "party": [{"species_name": "Pikachu"}],
        "position": {"map_id": 0x33, "x": 28, "y": 43},
    }
    chapter = current_chapter_goal(in_grass)

    assert requested_success_reached("capsule-a", at_exit, chapter)[0] is True
    assert requested_success_reached("capsule-a", in_grass, chapter)[0] is False


def available_skills() -> list[dict[str, object]]:
    return [
        {"id": "close_menu_or_cancel", "enabled": True},
        {"id": "attempt_catch", "enabled": True},
        {"id": "advance_dialogue", "enabled": True},
        {"id": "heal_at_pokecenter", "enabled": True},
        {"id": "literal_button_press", "enabled": True},
        {"id": "navigate_within_viridian_forest_region", "enabled": True},
        {"id": "navigate_within_pallet_region", "enabled": True},
        {"id": "purchase_pokemart_item", "enabled": True},
        {"id": "recover_to_overworld", "enabled": True},
        {"id": "run_from_wild_battle", "enabled": True},
        {"id": "talk_to_npc", "enabled": True},
        {"id": "use_move", "enabled": True},
    ]


def test_execute_move_alias_normalizes_to_use_move() -> None:
    skill_id, args = normalize_selected_skill(
        {"skillId": "execute_move", "args": {"move": "Tackle"}},
        available_skills(),
    )

    assert skill_id == "use_move"
    assert args == {"move": "Tackle"}


def test_use_move_does_not_replace_strategy_when_multiple_moves_are_usable() -> None:
    snapshot = {
        "active_party_member": {
            "moves": [
                {"move_name": "Tail Whip", "pp": 30},
                {"move_name": "Tackle", "pp": 35},
            ]
        }
    }

    assert default_active_battle_move(snapshot) is None


def test_use_move_infers_the_only_usable_active_move() -> None:
    snapshot = {
        "active_party_member": {
            "moves": [
                {"move_name": "Tail Whip", "pp": 0},
                {"move_name": "Tackle", "pp": 35},
            ]
        }
    }

    assert default_active_battle_move(snapshot) == "Tackle"


def test_pikachu_chapter_suppresses_attempt_catch_for_non_target() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x33, "x": 32, "y": 43},
        "party": [{"species_name": "Squirtle"}, {"species_name": "Spearow"}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 5}],
        "enemy": {"species_id": 0x70, "species_name": "Weedle"},
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal)

    assert goal.chapter_id == "chapter_6_capsule_a_pikachu_catch"
    assert "attempt_catch" not in enabled_ids(filtered)
    assert notes


def test_pikachu_chapter_allows_attempt_catch_for_target_species_id() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x33, "x": 30, "y": 43},
        "party": [{"species_name": "Squirtle"}, {"species_name": "Spearow"}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 5}],
        "enemy": {"species_id": 0x54, "species_name": "Species 0x54"},
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal)

    assert goal.chapter_id == "chapter_6_capsule_a_pikachu_catch"
    assert "attempt_catch" in enabled_ids(filtered)
    assert notes == []


def test_route_22_chapter_suppresses_attempt_catch_for_non_spearow() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x21, "x": 31, "y": 11},
        "party": [{"species_name": "Squirtle"}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 5}],
        "enemy": {"species_id": 0xA5, "species_name": "Rattata"},
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal)

    assert goal.chapter_id == "chapter_5b_route_22_spearow_catch"
    assert "attempt_catch" not in enabled_ids(filtered)
    assert notes


def test_target_search_suppresses_non_target_damage_when_active_hp_is_low() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x21, "x": 31, "y": 11},
        "active_party_member": {"species_name": "Squirtle", "hp": 9, "max_hp": 21},
        "party": [{"species_name": "Squirtle", "hp": 9, "max_hp": 21}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 15}],
        "enemy": {"species_id": 0xA5, "species_name": "Rattata"},
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal)

    assert goal.chapter_id == "chapter_5b_route_22_spearow_catch"
    assert "attempt_catch" not in enabled_ids(filtered)
    assert "use_move" not in enabled_ids(filtered)
    assert any("50% HP" in note for note in notes)


def test_acquire_poke_balls_suppresses_noop_mart_counter_navigation() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "x": 2, "y": 5},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [],
        "money": 3175,
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal)

    assert goal.chapter_id == "chapter_5_acquire_poke_balls"
    assert enabled_ids(filtered) == {"talk_to_npc"}
    assert "navigate_within_pallet_region" not in enabled_ids(filtered)
    assert notes


def test_brock_checkpoint_exposes_only_semantic_npc_interaction() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x36, "x": 5, "y": 1},
        "party": [
            {
                "species_name": "Squirtle",
                "hp": 41,
                "max_hp": 41,
                "status": 0,
                "moves": [{"move_name": "Bubble"}],
            },
            {"species_name": "Pikachu", "hp": 20, "max_hp": 20, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal)
    args = infer_missing_skill_args("talk_to_npc", {}, goal, snapshot)

    assert goal.chapter_id == "chapter_7_defeat_brock"
    assert enabled_ids(filtered) == {"talk_to_npc"}
    assert args == {"target": "brock"}
    assert any("already at brock" in note for note in notes)


def test_brock_checkpoint_hands_active_dialogue_to_advance_skill() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x36, "x": 5, "y": 1},
        "party": [
            {
                "species_name": "Squirtle",
                "hp": 41,
                "max_hp": 41,
                "status": 0,
                "moves": [{"move_name": "Bubble"}],
            },
            {"species_name": "Pikachu", "hp": 20, "max_hp": 20, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)
    available = [skill for skill in available_skills() if skill["id"] != "talk_to_npc"]

    filtered, notes = apply_chapter_skill_policy(available, snapshot, goal)

    assert goal.chapter_id == "chapter_7_defeat_brock"
    assert enabled_ids(filtered) == {"advance_dialogue"}
    assert any("already started" in note for note in notes)


def test_level_for_brock_policy_notes_healing_priority() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x02, "x": 20, "y": 26},
        "party": [
            {"species_name": "Squirtle", "hp": 0, "max_hp": 20, "status": 0},
            {"species_name": "Pikachu", "hp": 9, "max_hp": 20, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal)

    assert goal.chapter_id == "chapter_7_level_for_brock"
    assert enabled_ids(filtered) == enabled_ids(available_skills())
    assert any("pewter_pokecenter_counter" in note for note in notes)


def test_route_22_spearow_requires_viridian_checkpoint_before_travel() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x01, "x": 20, "y": 26},
        "party": [{"species_name": "Squirtle", "hp": 20, "max_hp": 20, "status": 0}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 15}],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal, history=[])
    nav_args = infer_missing_skill_args(
        "navigate_within_viridian_forest_region",
        {},
        goal,
        snapshot,
        history=[],
    )

    assert goal.chapter_id == "chapter_5b_route_22_spearow"
    assert "attempt_catch" not in enabled_ids(filtered)
    assert "run_from_wild_battle" not in enabled_ids(filtered)
    assert nav_args == {"target": "viridian_pokecenter"}
    assert any("Viridian PokeCenter checkpoint" in note for note in notes)


def test_route_22_spearow_uses_grass_after_viridian_checkpoint() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x01, "x": 20, "y": 26},
        "party": [{"species_name": "Squirtle", "hp": 20, "max_hp": 20, "status": 0}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 15}],
        "badge_names": [],
    }
    history = [
        {
            "skillId": "heal_at_pokecenter",
            "result": {
                "status": "succeeded",
                "evidence": ["position=map=0x29,x=3,y=4"],
            },
        }
    ]
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal, history=history)
    nav_args = infer_missing_skill_args(
        "navigate_within_viridian_forest_region",
        {},
        goal,
        snapshot,
        history=history,
    )

    assert goal.chapter_id == "chapter_5b_route_22_spearow"
    assert enabled_ids(filtered) == enabled_ids(available_skills())
    assert nav_args == {"target": "route_22_grass"}
    assert notes == []


def test_capsule_a_chapter_start_inside_forest_does_not_backtrack_for_checkpoint() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x33, "x": 28, "y": 43},
        "party": [{"species_name": "Squirtle", "hp": 20, "max_hp": 20, "status": 0}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 5}],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal, history=[])

    assert goal.chapter_id == "chapter_6_capsule_a"
    assert enabled_ids(filtered) == enabled_ids(available_skills())
    assert notes == []


def test_level_for_brock_training_battle_suppresses_running_and_catching() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x0D, "x": 6, "y": 6},
        "active_party_member": {
            "species_name": "Squirtle",
            "hp": 20,
            "max_hp": 20,
            "status": 0,
            "moves": [{"move_name": "Tackle"}],
        },
        "party": [
            {
                "species_name": "Squirtle",
                "hp": 20,
                "max_hp": 20,
                "status": 0,
                "moves": [{"move_name": "Tackle"}],
            },
            {"species_name": "Spearow", "hp": 19, "max_hp": 19, "status": 0},
            {"species_name": "Pikachu", "hp": 17, "max_hp": 17, "status": 0},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 2}],
        "enemy": {"species_name": "Pidgey", "hp": 14, "max_hp": 14},
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    filtered, notes = apply_chapter_skill_policy(available_skills(), snapshot, goal)

    assert goal.chapter_id == "chapter_7_level_for_brock"
    assert "run_from_wild_battle" not in enabled_ids(filtered)
    assert "attempt_catch" not in enabled_ids(filtered)
    assert "use_move" in enabled_ids(filtered)
    assert any("requires experience" in note for note in notes)


def test_level_for_brock_infers_pokecenter_target_when_party_is_damaged() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x02, "x": 20, "y": 26},
        "party": [
            {"species_name": "Squirtle", "hp": 0, "max_hp": 20, "status": 0},
            {"species_name": "Pikachu", "hp": 9, "max_hp": 20, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    args = infer_missing_skill_args("navigate_within_pewter_region", {}, goal, snapshot)

    assert args == {"target": "pewter_pokecenter_counter"}


def test_level_for_brock_overrides_gym_navigation_target_to_training_grass() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x02, "x": 20, "y": 26},
        "party": [
            {"species_name": "Squirtle", "hp": 20, "max_hp": 20, "status": 0, "moves": [{"move_name": "Tackle"}]},
            {"species_name": "Pikachu", "hp": 19, "max_hp": 19, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    args = infer_missing_skill_args(
        "navigate_within_pewter_region",
        {"target": "pewter_gym_brock_pre_battle"},
        goal,
        snapshot,
    )

    assert goal.chapter_id == "chapter_7_level_for_brock"
    assert args == {"target": "pewter_route2_grass"}


def test_capsule_a_exit_interior_infers_forest_exit_target() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x33, "x": 17, "y": 9},
        "party": [
            {"species_name": "Squirtle", "hp": 0, "max_hp": 20, "status": 0, "moves": [{"move_name": "Tackle"}]},
            {"species_name": "Pikachu", "hp": 17, "max_hp": 17, "status": 0},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 2}],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    args = infer_missing_skill_args("navigate_within_viridian_forest_region", {}, goal, snapshot)

    assert goal.chapter_id == "chapter_6_capsule_a_exit_forest"
    assert args == {"target": "forest_north_exit"}


def test_level_for_brock_at_forest_exit_infers_north_gate_target() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x33, "x": 1, "y": 0},
        "party": [
            {"species_name": "Squirtle", "hp": 0, "max_hp": 20, "status": 0, "moves": [{"move_name": "Tackle"}]},
            {"species_name": "Pikachu", "hp": 17, "max_hp": 17, "status": 0},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 2}],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    args = infer_missing_skill_args(
        "navigate_within_viridian_forest_region",
        {"target": "route_2"},
        goal,
        snapshot,
    )

    assert goal.chapter_id == "chapter_7_level_for_brock"
    assert args == {"target": "north_gate_north"}


def test_capsule_a_exit_overrides_route_2_navigation_to_forest_exit() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x33, "x": 17, "y": 9},
        "party": [
            {"species_name": "Squirtle", "hp": 0, "max_hp": 20, "status": 0},
            {"species_name": "Spearow", "hp": 19, "max_hp": 19, "status": 0},
            {"species_name": "Pikachu", "hp": 17, "max_hp": 17, "status": 0},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 2}],
        "badge_names": [],
    }
    goal = current_chapter_goal(snapshot)

    args = infer_missing_skill_args(
        "navigate_within_viridian_forest_region",
        {"target": "route_2"},
        goal,
        snapshot,
    )

    assert goal.chapter_id == "chapter_6_capsule_a_exit_forest"
    assert args == {"target": "forest_north_exit"}


def test_local_runner_defaults_omitted_poke_ball_quantity_to_affordable_sentinel() -> None:
    assert default_purchase_quantity({}, "Poke Ball") == 99
    assert default_purchase_quantity({"quantity": 7}, "Poke Ball") == 7
    assert default_purchase_quantity({}, "Potion") == 1


def test_normalize_selected_skill_unwraps_nested_execute_skill_payload() -> None:
    skill_id, args = normalize_selected_skill(
        {
            "skillId": "execute_skill",
            "args": {
                "skillId": "navigate_within_viridian_forest_region",
                "args": {"target": "forest_north_exit"},
            },
        },
        [{"id": "navigate_within_viridian_forest_region", "enabled": True}],
    )

    assert skill_id == "navigate_within_viridian_forest_region"
    assert args == {"target": "forest_north_exit"}


def test_missing_required_semantic_argument_is_rejected_before_input() -> None:
    result = missing_skill_argument_result("switch_party_member", "target")

    assert result["actionStarted"] is False
    assert result["status"] == "blocked"
    assert "action_started=false" in result["evidence"]
