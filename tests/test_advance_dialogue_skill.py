from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.advance_dialogue import advance_dialogue
from pokemon_player.skills.visual_state import inspect_ui_visual_state


ROOT = Path(__file__).resolve().parents[1]
SKILL_STATES = ROOT / "research" / "skill-states" / "advance_dialogue"
SCREENSHOTS = ROOT / "research" / "skill-states" / "local" / "advance_dialogue"


def load_record(name: str) -> dict:
    return json.loads((SKILL_STATES / f"{name}.skill.json").read_text(encoding="utf-8"))


def test_advance_dialogue_matches_human_captured_skill_states() -> None:
    before = load_record("dialogue_success_before")
    cases = {
        "dialogue_success_before": ("succeeded", None),
        "dialogue_success_after": ("succeeded", before["snapshot"]),
        "blocked_no_dialogue": ("blocked", None),
        "uncertain_repeating_dialogue": ("uncertain", None),
    }

    for capture_id, (expected_status, before_snapshot) in cases.items():
        record = load_record(capture_id)
        result = advance_dialogue(
            record["snapshot"],
            before_snapshot=before_snapshot,
            screenshot_path=record["screenshot_file"],
        )
        assert result.status == expected_status
        assert result.evidence


def test_advance_dialogue_visual_state_distinguishes_prompt_from_start_menu() -> None:
    prompt = inspect_ui_visual_state(SCREENSHOTS / "dialogue_success_before.png")
    start_menu = inspect_ui_visual_state(SCREENSHOTS / "blocked_no_dialogue.png")
    mixed_prompt = inspect_ui_visual_state(SCREENSHOTS / "uncertain_repeating_dialogue.png")

    assert prompt.bottom_text_box
    assert not prompt.upper_menu
    assert not start_menu.bottom_text_box
    assert mixed_prompt.bottom_text_box
    assert mixed_prompt.upper_menu
