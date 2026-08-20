from __future__ import annotations

from pathlib import Path

from pokemon_player.skills.handle_nickname_prompt import (
    handle_nickname_prompt,
    screenshot_has_naming_screen,
    screenshot_has_nickname_intro_dialogue,
    screenshot_has_nickname_prompt,
)


ROOT = Path(__file__).resolve().parents[1]
MANUAL_INPUT = ROOT / "research" / "artifacts" / "director-player-runs" / "manual_input"
INTERPRETATION_CAPTURES = ROOT / "research" / "artifacts" / "director-player-runs" / "interpretation_captures"


def test_detects_nickname_yes_no_prompt_from_recent_capture() -> None:
    path = MANUAL_INPUT / "a-20260624T222337148845Z0000" / "before.png"

    assert screenshot_has_nickname_prompt(path) is True
    assert screenshot_has_naming_screen(path) is False
    assert screenshot_has_nickname_intro_dialogue(path) is False


def test_detects_pre_choice_nickname_intro_from_interpretation_capture() -> None:
    paths = [
        INTERPRETATION_CAPTURES / "advance_battle_dialogue-20260625T003035943533Z0000" / "screenshot.png",
        INTERPRETATION_CAPTURES / "advance_battle_dialogue-20260625T005556627749Z0000" / "screenshot.png",
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T061115146309Z"
        / "action_017_before.png",
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T061115146309Z"
        / "action_018_before.png",
    ]

    for path in paths:
        assert screenshot_has_nickname_intro_dialogue(path) is True
        assert screenshot_has_nickname_prompt(path) is False


def test_detects_naming_screen_from_recent_capture() -> None:
    path = MANUAL_INPUT / "a-20260624T222352075861Z0000" / "after.png"

    assert screenshot_has_naming_screen(path) is True
    assert screenshot_has_nickname_prompt(path) is False


def test_black_transition_frame_is_not_naming_screen() -> None:
    path = (
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T094738534917Z"
        / "action_002_before.png"
    )

    assert screenshot_has_naming_screen(path) is False


def test_stable_viridian_mart_counter_is_not_naming_screen() -> None:
    path = (
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T173906047314Z"
        / "final.png"
    )

    assert screenshot_has_naming_screen(path) is False


def test_wild_battle_intro_is_not_nickname_prompt() -> None:
    path = (
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260630T173331365843Z"
        / "action_001_before.png"
    )

    assert screenshot_has_nickname_prompt(path) is False


def test_prompt_skill_is_available_on_prompt_and_intro() -> None:
    snapshot = {"mode": "battle", "battle_type_raw": 1, "enemy": {"hp": 1}}
    prompt = MANUAL_INPUT / "a-20260624T222337148845Z0000" / "before.png"
    intro = (
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T061115146309Z"
        / "action_017_before.png"
    )
    naming = MANUAL_INPUT / "a-20260624T222352075861Z0000" / "after.png"

    assert handle_nickname_prompt(snapshot, screenshot_path=prompt).status == "succeeded"
    assert handle_nickname_prompt(snapshot, screenshot_path=intro).status == "succeeded"
    assert handle_nickname_prompt(snapshot, screenshot_path=naming).status == "blocked"
