from __future__ import annotations

from pokemon_player.chapter_direction import current_chapter_goal
from pokemon_player.pallet_navigation import default_navigation_target
from pokemon_player.capsule_a_navigation import Position
from pokemon_player.skill_execution import (
    oak_lab_exit_completed,
    oak_lab_exit_story_progress,
    plan_oak_lab_post_rival_exit_route,
    plan_viridian_mart_counter_route,
)


def test_pallet_town_map_zero_remains_a_valid_chapter_context() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0, "x": 10, "y": 0},
        "party": [{"species_name": "Squirtle"}],
        "inventory": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_3_reach_route_1"
    assert "map=0x00" in goal.evidence


def test_clean_boot_sentinel_requests_prologue() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0, "x": 0, "y": 0},
        "party": [],
        "inventory": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_0_prologue"
    assert any("complete_prologue" in hint for hint in goal.hints)


def test_red_house_without_party_requests_leave_home() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x26, "x": 3, "y": 6},
        "party": [],
        "inventory": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_1_leave_home"
    assert any("pallet_home_1f_exit" in hint for hint in goal.hints)


def test_route_one_chapter_points_to_viridian_and_navigation_defaults_forward() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x0C, "x": 10, "y": 31},
        "party": [{"species_name": "Squirtle"}],
        "inventory": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_3_route_1_to_viridian"
    assert default_navigation_target(snapshot) == "viridian_city_south_entrance"
    assert any("target=viridian_city_south_entrance" in hint for hint in goal.hints)


def test_viridian_mart_door_navigation_default_steps_inside() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x01, "x": 29, "y": 20},
        "party": [{"species_name": "Squirtle"}],
        "inventory": [],
    }

    assert default_navigation_target(snapshot) == "viridian_mart_entrance"


def test_oaks_lab_after_rival_battle_points_to_exit() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 5, "y": 6},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5_acquire_poke_balls"
    assert default_navigation_target(snapshot) == "oaks_lab_exit"


def test_post_parcel_event_flags_route_level_five_to_buy_balls() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "x": 2, "y": 5},
        "party": [{"species_name": "Squirtle", "level": 5}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 1}],
        "story_events": {
            "got_pokedex": True,
            "got_oaks_parcel": True,
            "oak_got_parcel": True,
        },
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5_acquire_poke_balls"
    assert "story.oak_got_parcel=true" in goal.evidence
    assert "story.got_pokedex=true" in goal.evidence


def test_explicit_clear_parcel_events_disable_level_fallback() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 5, "y": 6},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [],
        "story_events": {
            "got_pokedex": False,
            "got_oaks_parcel": False,
            "oak_got_parcel": False,
        },
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_2_leave_oaks_lab"
    assert "story.oak_got_parcel=false" in goal.evidence


def test_oaks_lab_after_starter_points_to_exit_even_before_rival_battle() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 5, "y": 6},
        "party": [{"species_name": "Squirtle", "level": 5}],
        "inventory": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_2_leave_oaks_lab"
    assert default_navigation_target(snapshot) == "oaks_lab_exit"


def test_oaks_lab_exit_tile_points_to_route_1() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 5, "y": 11},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5_acquire_poke_balls"
    assert default_navigation_target(snapshot) == "oaks_lab_exit"
    assert any("oaks_lab_exit" in hint for hint in goal.hints)


def test_parcel_item_id_overrides_viridian_mart_retrieval_loop() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "x": 2, "y": 5},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [{"item_id": 0x46, "item_name": "Nugget", "quantity": 1}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_4_exit_mart_with_parcel"
    assert any("viridian_mart_exit" in hint for hint in goal.hints)
    assert default_navigation_target(snapshot) == "oaks_lab_entrance"


def test_parcel_in_mart_text_state_finishes_dialogue_before_returning_to_oak() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "x": 2, "y": 5},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [{"item_id": 0x46, "item_name": "Oak's Parcel", "quantity": 1}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_4_exit_mart_with_parcel"
    assert "Finish the Mart clerk dialogue" in goal.objective


def test_parcel_inside_oaks_lab_points_to_parcel_handoff() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 5, "y": 11},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [{"item_id": 0x46, "item_name": "Oak's Parcel", "quantity": 1}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_4_return_parcel_in_lab"
    assert default_navigation_target(snapshot) == "oaks_lab_starter_table"
    assert any("oaks_lab_starter_table" in hint for hint in goal.hints)


def test_one_poke_ball_still_requires_resupply_to_five() -> None:
    snapshot = {
        "mode": "dialogue",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "x": 2, "y": 5},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 1}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5_acquire_poke_balls"
    assert "at least 5 Poke Balls" in goal.objective
    assert any("quantity=99" in hint for hint in goal.hints)


def test_five_poke_balls_in_viridian_hands_off_to_capsule_a() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x01, "x": 29, "y": 20},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 5}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5b_route_22_spearow"
    assert any("target=route_22_grass" in hint for hint in goal.hints)


def test_five_poke_balls_on_route_1_still_targets_route_22_spearow() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x0C, "x": 10, "y": 8},
        "party": [{"species_name": "Squirtle", "level": 6}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 5}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5b_route_22_spearow"
    assert any("viridian_city_south_entrance" in hint for hint in goal.hints)
    assert not any("viridian_mart_front_door" in hint for hint in goal.hints)


def test_five_poke_balls_in_mart_hands_off_to_capsule_a() -> None:
    snapshot = {
        "mode": "menu",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "x": 2, "y": 5},
        "party": [{"species_name": "Squirtle", "level": 8}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 15}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5b_route_22_spearow"
    assert any("target=route_22_grass" in hint for hint in goal.hints)


def test_spearow_in_party_hands_off_to_capsule_a_proper() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x21, "x": 33, "y": 11},
        "party": [
            {"species_name": "Squirtle", "level": 8},
            {"species_name": "Spearow", "level": 3},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 12}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_6_capsule_a"
    assert "catch Pikachu specifically" in goal.objective
    assert any("target=forest_grass" in hint for hint in goal.hints)


def test_route_22_spearow_battle_requests_catch() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x21, "x": 31, "y": 11},
        "party": [{"species_name": "Squirtle", "level": 8}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 12}],
        "enemy": {"species_name": "Spearow", "level": 3, "hp": 15, "max_hp": 15},
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5b_route_22_spearow_catch"
    assert any("use attempt_catch" in hint.lower() for hint in goal.hints)


def test_route_22_spearow_battle_stays_targeted_after_spending_a_ball() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x21, "x": 32, "y": 11},
        "party": [{"species_name": "Squirtle", "level": 7}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 4}],
        "enemy": {"species_name": "Spearow", "level": 5, "hp": 14, "max_hp": 19},
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5b_route_22_spearow_catch"
    assert any("use attempt_catch" in hint.lower() for hint in goal.hints)


def test_route_22_non_spearow_battle_does_not_blanket_run() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x21, "x": 31, "y": 11},
        "party": [{"species_name": "Squirtle", "level": 8}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 12}],
        "enemy": {"species_name": "Rattata", "level": 3, "hp": 12, "max_hp": 12},
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_5b_route_22_spearow_catch"
    assert any("safe XP" in hint for hint in goal.hints)
    assert not any("use run_from_wild_battle when available" in hint for hint in goal.hints)


def test_capsule_a_requires_pikachu_not_generic_party_growth() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x33, "x": 28, "y": 43},
        "party": [{"species_name": "Squirtle", "level": 6}, {"species_name": "Weedle", "level": 3}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 4}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id != "chapter_6_capsule_a_complete"
    assert goal.success is False


def test_spearow_plus_additional_non_pikachu_does_not_complete_capsule_a() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x0D, "x": 7, "y": 48},
        "party": [
            {"species_name": "Squirtle", "level": 6},
            {"species_name": "Spearow", "level": 5},
            {"species_name": "Weedle", "level": 3},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 1}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id != "chapter_6_capsule_a_complete"
    assert goal.success is False


def test_pikachu_in_forest_still_requires_north_exit() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x33, "x": 28, "y": 43},
        "party": [{"species_name": "Squirtle", "level": 7}, {"species_name": "Pikachu", "level": 4}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 3}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_6_capsule_a_exit_forest"
    assert goal.success is False
    assert any("target=forest_north_exit" in hint for hint in goal.hints)


def test_pikachu_in_viridian_mart_keeps_exit_forest_goal_even_low_on_balls() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "x": 2, "y": 5},
        "party": [
            {"species_name": "Squirtle", "level": 6},
            {"species_name": "Spearow", "level": 5},
            {"species_name": "Pikachu", "level": 3},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 3}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_6_capsule_a_exit_forest"
    assert "Pikachu is secured" in goal.objective
    assert any("Do not buy more Poke Balls" in hint for hint in goal.hints)


def test_pikachu_on_route_one_after_blackout_returns_to_forest_goal() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x0C, "x": 10, "y": 31},
        "party": [
            {"species_name": "Squirtle", "level": 6},
            {"species_name": "Pikachu", "level": 3},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 0}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_6_capsule_a_exit_forest"
    assert any("target=viridian_city_south_entrance" in hint for hint in goal.hints)


def test_forest_trainer_battle_after_pikachu_is_not_rival_battle() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 2,
        "position": {"map_id": 0x33, "x": 26, "y": 33},
        "party": [
            {"species_name": "Squirtle", "level": 6, "hp": 0},
            {"species_name": "Pikachu", "level": 3, "hp": 12},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 3}],
        "enemy": {"species_name": "Weedle", "level": 6, "hp": 12, "max_hp": 21},
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_6_capsule_a_exit_forest"
    assert goal.title == "Exit Viridian Forest"
    assert "rival" not in goal.objective.lower()


def test_pikachu_at_forest_north_exit_hands_off_to_pewter_chapter() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2F, "x": 4, "y": 7},
        "party": [
            {
                "species_name": "Squirtle",
                "level": 8,
                "moves": [{"move_name": "Tackle"}, {"move_name": "Tail Whip"}, {"move_name": "Bubble"}],
            },
            {"species_name": "Pikachu", "level": 4},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 3}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_reach_pewter_city"
    assert goal.success is False
    assert "pikachu_caught=true" in goal.evidence
    assert any("navigate_within_pewter_region" in hint for hint in goal.hints)


def test_pikachu_at_forest_north_exit_without_bubble_levels_before_brock() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2F, "x": 4, "y": 7},
        "party": [
            {
                "species_name": "Squirtle",
                "level": 5,
                "moves": [{"move_name": "Tackle"}, {"move_name": "Tail Whip"}],
            },
            {"species_name": "Pikachu", "level": 4},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 3}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_level_for_brock"
    assert "brock_ready=false" in goal.evidence
    assert any("pewter_route2_grass" in hint for hint in goal.hints)


def test_level_for_brock_at_forest_top_finishes_forest_exit_first() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x33, "x": 1, "y": 0},
        "party": [
            {
                "species_name": "Squirtle",
                "level": 5,
                "hp": 0,
                "max_hp": 20,
                "moves": [{"move_name": "Tackle"}, {"move_name": "Tail Whip"}],
            },
            {"species_name": "Pikachu", "level": 4, "hp": 17, "max_hp": 17},
        ],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 3}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_level_for_brock"
    assert any("navigate_within_viridian_forest_region target=north_gate_north" in hint for hint in goal.hints)
    assert not any(hint.startswith("Use navigate_within_pewter_region target=pewter_pokecenter_counter") for hint in goal.hints)


def test_pewter_city_without_badge_targets_brock() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x02, "x": 20, "y": 26},
        "party": [
            {
                "species_name": "Squirtle",
                "level": 14,
                "hp": 41,
                "max_hp": 41,
                "status": 0,
                "moves": [{"move_name": "Tackle"}, {"move_name": "Bubble"}],
            },
            {"species_name": "Pikachu", "level": 9, "hp": 26, "max_hp": 26, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_prepare_for_brock"
    assert goal.success is False
    assert any("pewter_gym_brock_pre_battle" in hint for hint in goal.hints)


def test_damaged_party_in_pewter_targets_pokecenter_before_brock() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x02, "x": 20, "y": 26},
        "party": [
            {"species_name": "Squirtle", "level": 5, "hp": 0, "max_hp": 20, "status": 0},
            {"species_name": "Pikachu", "level": 6, "hp": 9, "max_hp": 20, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_level_for_brock"
    assert any("pewter_pokecenter_counter" in hint for hint in goal.hints)
    assert any("heal_at_pokecenter" in hint for hint in goal.hints)
    assert not any(hint == "Use navigate_within_pewter_region target=pewter_gym_brock_pre_battle." for hint in goal.hints)


def test_damaged_party_inside_pewter_gym_is_sent_to_heal() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x36, "x": 4, "y": 6},
        "party": [
            {"species_name": "Squirtle", "level": 5, "hp": 0, "max_hp": 20, "status": 0},
            {"species_name": "Pikachu", "level": 6, "hp": 9, "max_hp": 20, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_level_for_brock"
    assert goal.title == "Level Before Brock"
    assert "party_needs_healing=true" in goal.evidence
    assert any("pewter_pokecenter_counter" in hint for hint in goal.hints)


def test_brock_trainer_battle_uses_chapter_7_battle_goal() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 2,
        "position": {"map_id": 0x36, "x": 4, "y": 7},
        "party": [
            {
                "species_name": "Squirtle",
                "level": 14,
                "hp": 41,
                "max_hp": 41,
                "status": 0,
                "moves": [{"move_name": "Tackle"}, {"move_name": "Bubble"}],
            },
            {"species_name": "Pikachu", "level": 9, "hp": 26, "max_hp": 26, "status": 0},
        ],
        "enemy": {"species_name": "Geodude", "level": 10, "hp": 21, "max_hp": 21},
        "inventory": [],
        "badge_names": [],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_defeat_brock_battle"
    assert any("Water" in hint or "water" in hint for hint in goal.hints)


def test_boulder_badge_completes_chapter_7() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x36, "x": 5, "y": 1},
        "party": [{"species_name": "Wartortle", "level": 16, "hp": 35, "max_hp": 50, "status": 0}],
        "inventory": [],
        "badge_names": ["Boulder Badge"],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_boulder_badge_complete"
    assert goal.success is True
    assert "boulder_badge=true" in goal.evidence


def test_defeated_brock_claims_badge_before_damaged_party_can_leave_to_heal() -> None:
    snapshot = {
        "mode": "dialogue",
        "battle_type_raw": 0,
        "position": {"map_id": 0x36, "x": 5, "y": 1},
        "party": [
            {
                "species_name": "Squirtle",
                "level": 14,
                "hp": 7,
                "max_hp": 41,
                "status": 0,
                "moves": [{"move_name": "Bubble"}],
            },
            {"species_name": "Pikachu", "level": 9, "hp": 26, "max_hp": 26, "status": 0},
        ],
        "inventory": [],
        "badge_names": [],
        "story_events": {"beat_brock": True},
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_7_claim_boulder_badge"
    assert goal.success is False
    assert "brock_defeated=true" in goal.evidence
    assert "boulder_badge=false" in goal.evidence
    assert not any("pokecenter" in hint.lower() for hint in goal.hints)


def test_forest_pikachu_battle_requests_catch() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x33, "x": 28, "y": 43},
        "party": [{"species_name": "Squirtle", "level": 7}, {"species_name": "Spearow", "level": 3}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 4}],
        "enemy": {"species_name": "Pikachu", "level": 3, "hp": 12, "max_hp": 12},
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_6_capsule_a_pikachu_catch"
    assert any("wild enemy is Pikachu" in hint for hint in goal.hints)


def test_inside_forest_without_pikachu_never_returns_to_route_22() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x33, "x": 17, "y": 47},
        "party": [{"species_name": "Squirtle", "level": 7}, {"species_name": "Spearow", "level": 3}],
        "inventory": [{"item_id": 0x04, "item_name": "Poke Ball", "quantity": 4}],
    }

    goal = current_chapter_goal(snapshot)

    assert goal.chapter_id == "chapter_6_capsule_a"
    assert "Pikachu" in goal.objective
    assert "Route 22 is out of scope after entering Viridian Forest." in goal.hints
    assert not any("route_22" in hint.lower() for hint in goal.hints)


def test_oak_lab_exit_story_progress_accepts_rival_intercept_menu() -> None:
    before = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 7, "y": 4},
        "party": [{"species_name": "Squirtle", "level": 5}],
        "inventory": [],
    }
    after = {
        "mode": "menu",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 5, "y": 6},
        "party": [{"species_name": "Squirtle", "level": 5}],
        "inventory": [],
    }

    assert oak_lab_exit_story_progress(before, after, target="oaks_lab_exit") is True


def test_oak_lab_post_rival_exit_route_allows_initial_non_moving_down_inputs() -> None:
    plan = plan_oak_lab_post_rival_exit_route(
        current_position=Position(0x28, 5, 6),
        remaining_inputs=10,
    )

    assert plan is not None
    assert plan["buttons"] == ["down", "down", "down", "down", "down", "down", "down"]


def test_oak_lab_exit_completed_accepts_pallet_transition() -> None:
    before = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 5, "y": 6},
    }
    after = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x00, "x": 12, "y": 12},
    }

    assert oak_lab_exit_completed(before, after, target="oaks_lab_exit") is True


def test_viridian_mart_counter_route_handles_entry_settle_dialogue() -> None:
    plan = plan_viridian_mart_counter_route(
        current_position=Position(0x2A, 3, 7),
        remaining_inputs=4,
    )

    assert plan is not None
    assert plan["buttons"] == ["up", "up", "left"]
