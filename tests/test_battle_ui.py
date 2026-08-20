from __future__ import annotations

from pathlib import Path

from pokemon_player.battle_ui import (
    forced_party_selection_prompt_visible,
    inspect_battle_ui_screenshot,
    party_menu_cursor_slot,
)


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT_SCREENSHOTS = ROOT / "research" / "skill-states" / "local" / "attempt_catch"


def test_battle_ui_detects_action_menu_and_cursor() -> None:
    ui = inspect_battle_ui_screenshot(ATTEMPT_SCREENSHOTS / "success_before.png")

    assert ui.kind == "action_menu"
    assert ui.cursor == "fight"


def test_battle_ui_detects_throw_dialogue() -> None:
    ui = inspect_battle_ui_screenshot(ATTEMPT_SCREENSHOTS / "uncertain_throw_dialogue.png")

    assert ui.kind == "dialogue"


def test_battle_ui_detects_intro_dialogue_not_move_menu() -> None:
    ui = inspect_battle_ui_screenshot(
        ROOT
        / "research"
        / "promotions"
        / "evidence"
        / "local"
        / "battle_dialogue_advancement_contract"
        / "step_01_battle_intro_dialogue_before.png"
    )

    assert ui.kind == "dialogue"
    assert ui.cursor == "unknown"


def test_battle_ui_detects_short_move_result_dialogue() -> None:
    ui = inspect_battle_ui_screenshot(
        ROOT
        / "research"
        / "promotions"
        / "evidence"
        / "local"
        / "battle_dialogue_advancement_contract"
        / "step_01_move_dialogue_before.png"
    )

    assert ui.kind == "dialogue"
    assert ui.cursor == "unknown"


def test_battle_ui_detects_resolved_dialogue_action_menu() -> None:
    ui = inspect_battle_ui_screenshot(
        ROOT
        / "research"
        / "promotions"
        / "evidence"
        / "local"
        / "battle_dialogue_advancement_contract"
        / "step_01_move_dialogue_after.png"
    )

    assert ui.kind == "action_menu"
    assert ui.cursor == "fight"


def test_policy_move_submenu_detects_move_cursor() -> None:
    ui = inspect_battle_ui_screenshot(
        ROOT
        / "research"
        / "policy-states"
        / "local"
        / "battle_menu_throw"
        / "pikachu_fullhealth_moves_leer.png"
    )

    assert ui.kind == "move_menu"
    assert ui.cursor == "move_1"


def test_policy_move_submenu_detects_second_move_cursor() -> None:
    ui = inspect_battle_ui_screenshot(
        ROOT
        / "research"
        / "policy-states"
        / "local"
        / "battle_menu_throw"
        / "pikachu_fullhealth_moves_tackle.png"
    )

    assert ui.kind == "move_menu"
    assert ui.cursor == "move_2"


def test_policy_party_menu_is_not_action_menu() -> None:
    ui = inspect_battle_ui_screenshot(
        ROOT
        / "research"
        / "policy-states"
        / "local"
        / "battle_menu_throw"
        / "pikachu_fullhealth_pokemon.png"
    )

    assert ui.kind == "party_menu"
    assert ui.cursor == "unknown"


def test_promotion_party_selection_prompt_detects_party_menu() -> None:
    ui = inspect_battle_ui_screenshot(
        ROOT
        / "research"
        / "promotions"
        / "evidence"
        / "local"
        / "battle_menu_and_cursor_detection"
        / "step_01_party_menu_nidoran.png"
    )

    assert ui.kind == "party_menu"
    assert ui.cursor == "unknown"


def test_forced_party_prompt_from_local_gemma_run_detects_party_menu() -> None:
    screenshot = (
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T061115146309Z"
        / "final.png"
    )
    ui = inspect_battle_ui_screenshot(screenshot)

    assert ui.kind == "party_menu"
    assert ui.cursor == "unknown"
    assert party_menu_cursor_slot(screenshot) == 1
    assert forced_party_selection_prompt_visible(screenshot) is True


def test_normal_battle_party_menu_cursor_is_detected_without_forced_prompt() -> None:
    screenshot = ROOT / "research" / "policy-states" / "local" / "battle_menu_throw" / "pikachu_fullhealth_pokemon.png"

    assert inspect_battle_ui_screenshot(screenshot).kind == "party_menu"
    assert party_menu_cursor_slot(screenshot) == 2
    assert forced_party_selection_prompt_visible(screenshot) is False
