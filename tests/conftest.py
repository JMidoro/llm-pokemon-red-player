from __future__ import annotations

import pytest


# These tests intentionally exercise ignored host captures or historical run bundles.
# Keeping the boundary as exact node ids lets pure tests in the same modules stay in CI.
LOCAL_ARTIFACT_TESTS = frozenset(
    {
        "tests/test_advance_battle_dialogue_skill.py::test_advance_battle_dialogue_detects_waiting_battle_text",
        "tests/test_advance_battle_dialogue_skill.py::test_advance_battle_dialogue_blocks_when_action_menu_is_available",
        "tests/test_advance_battle_dialogue_skill.py::test_advance_battle_dialogue_marks_return_to_action_menu_as_success",
        "tests/test_advance_dialogue_skill.py::test_advance_dialogue_matches_human_captured_skill_states",
        "tests/test_advance_dialogue_skill.py::test_advance_dialogue_visual_state_distinguishes_prompt_from_start_menu",
        "tests/test_attempt_catch_skill.py::test_attempt_catch_matches_human_captured_skill_states",
        "tests/test_attempt_catch_skill.py::test_attempt_catch_screenshot_dialogue_detector_separates_transient_text",
        "tests/test_battle_ui.py::test_battle_ui_detects_action_menu_and_cursor",
        "tests/test_battle_ui.py::test_battle_ui_detects_throw_dialogue",
        "tests/test_battle_ui.py::test_policy_move_submenu_detects_move_cursor",
        "tests/test_battle_ui.py::test_policy_move_submenu_detects_second_move_cursor",
        "tests/test_battle_ui.py::test_policy_party_menu_is_not_action_menu",
        "tests/test_battle_ui.py::test_forced_party_prompt_from_local_gemma_run_detects_party_menu",
        "tests/test_battle_ui.py::test_normal_battle_party_menu_cursor_is_detected_without_forced_prompt",
        "tests/test_director_player.py::test_director_availability_enables_pokecenter_healing_inside_center",
        "tests/test_director_player.py::test_oaks_lab_dialogue_advances_before_navigation",
        "tests/test_director_player.py::test_oaks_lab_menu_flagged_dialogue_still_advances_before_navigation",
        "tests/test_director_player.py::test_director_availability_enables_battle_dialogue_recovery_during_battle_text",
        "tests/test_director_player.py::test_director_availability_enables_battle_outcome_bundle_on_aftermath_text",
        "tests/test_director_player.py::test_director_availability_enables_switch_for_fainted_active_replacement",
        "tests/test_director_player.py::test_director_availability_enables_switch_on_forced_party_prompt_with_stale_active_slot",
        "tests/test_director_player.py::test_director_availability_enables_nickname_prompt_handler",
        "tests/test_director_player.py::test_director_availability_declares_nickname_text_args",
        "tests/test_director_player.py::test_director_availability_routes_pokedex_page_to_outcome_bundle",
        "tests/test_director_player.py::test_director_availability_routes_pre_pokedex_post_catch_dialogue_to_outcome_bundle",
        "tests/test_director_player.py::test_director_availability_suppresses_battle_advance_on_nickname_intro",
        "tests/test_director_player.py::test_director_availability_routes_generated_nickname_intro_through_handler",
        "tests/test_director_player.py::test_director_promoted_signals_mark_battle_dialogue_ready",
        "tests/test_enter_nickname_text_skill.py::test_nickname_keyboard_trace_matches_recent_abk_capture_path",
        "tests/test_enter_nickname_text_skill.py::test_enter_nickname_text_available_on_naming_screen",
        "tests/test_enter_nickname_text_skill.py::test_enter_nickname_text_handles_z_before_hidden_space",
        "tests/test_handle_nickname_prompt_skill.py::test_detects_nickname_yes_no_prompt_from_recent_capture",
        "tests/test_handle_nickname_prompt_skill.py::test_detects_pre_choice_nickname_intro_from_interpretation_capture",
        "tests/test_handle_nickname_prompt_skill.py::test_detects_naming_screen_from_recent_capture",
        "tests/test_handle_nickname_prompt_skill.py::test_prompt_skill_is_available_on_prompt_and_intro",
        "tests/test_heal_at_pokecenter_skill.py::test_heal_at_pokecenter_available_when_party_needs_healing_inside_center",
        "tests/test_heal_at_pokecenter_skill.py::test_heal_at_pokecenter_verifies_party_restored_after_nurse_dialogue",
        "tests/test_golden_states.py::test_all_golden_states_are_human_verified",
        "tests/test_golden_states.py::test_all_golden_states_reload_to_expected_snapshot_hash",
        "tests/test_golden_states.py::test_golden_states_cover_phase_1_modes_and_progression",
        "tests/test_navigate_within_viridian_forest_region_skill.py::test_navigation_start_blocks_when_stale_text_is_visible",
        "tests/test_promotion_evidence.py::test_mode_ui_visual_assertions_pass_against_existing_golden_screenshot",
        "tests/test_purchase_pokemart_item_skill.py::test_purchase_pokemart_item_enables_for_visible_buy_menu",
        "tests/test_purchase_pokemart_item_skill.py::test_purchase_pokemart_item_blocks_when_money_too_low",
        "tests/test_pyboy_smoke.py::test_pyboy_can_snapshot_save_and_reload",
        "tests/test_recover_to_overworld_skill.py::test_recover_to_overworld_screenshot_detector_finds_dialogue_or_menu_overlay",
        "tests/test_resolve_battle_outcome_dialogue_bundle_skill.py::test_resolve_bundle_enables_on_captured_outcome_dialogue_states",
        "tests/test_resolve_battle_outcome_dialogue_bundle_skill.py::test_resolve_bundle_reports_one_prompt_progress_as_success",
        "tests/test_resolve_battle_outcome_dialogue_bundle_skill.py::test_resolve_bundle_handles_pre_pokedex_post_catch_dialogue",
        "tests/test_use_move_skill.py::test_use_move_blocks_on_unclassified_battle_dialogue_box",
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    local_artifacts = pytest.mark.local_artifacts
    for item in items:
        base_nodeid = item.nodeid.split("[", 1)[0].replace("\\", "/")
        if base_nodeid in LOCAL_ARTIFACT_TESTS:
            item.add_marker(local_artifacts)
