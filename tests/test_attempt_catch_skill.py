from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.attempt_catch import attempt_catch, screenshot_has_throw_dialogue
from pokemon_player.skill_execution import bag_item_cursor_path, classify_attempt_catch_failure
from pokemon_player.skill_result import SkillResult


ROOT = Path(__file__).resolve().parents[1]
SKILL_STATES = ROOT / "research" / "skill-states" / "attempt_catch"
SCREENSHOTS = ROOT / "research" / "skill-states" / "local" / "attempt_catch"


def load_record(name: str) -> dict:
    return json.loads((SKILL_STATES / f"{name}.skill.json").read_text(encoding="utf-8"))


def test_attempt_catch_matches_human_captured_skill_states() -> None:
    before = load_record("success_before")
    cases = {
        "success_before": ("succeeded", None),
        "success_after": ("succeeded", before["snapshot"]),
        "failed_after_breakout": ("failed", before["snapshot"]),
        "blocked_no_balls": ("blocked", None),
        "uncertain_throw_dialogue": ("uncertain", None),
    }

    for capture_id, (expected_status, before_snapshot) in cases.items():
        record = load_record(capture_id)
        result = attempt_catch(
            record["snapshot"],
            before_snapshot=before_snapshot,
            screenshot_path=record["screenshot_file"],
        )
        assert result.status == expected_status
        assert result.evidence


def test_attempt_catch_screenshot_dialogue_detector_separates_transient_text() -> None:
    assert screenshot_has_throw_dialogue(SCREENSHOTS / "uncertain_throw_dialogue.png")
    assert not screenshot_has_throw_dialogue(SCREENSHOTS / "success_before.png")
    assert not screenshot_has_throw_dialogue(SCREENSHOTS / "failed_after_breakout.png")


def test_attempt_catch_with_no_observed_delta_is_uncertain() -> None:
    before = load_record("success_before")

    result = attempt_catch(before["snapshot"], before_snapshot=before["snapshot"])

    assert result.status == "uncertain"
    assert "No ball consumption" in result.summary


def test_attempt_catch_failure_classification_marks_throw_executor_failures() -> None:
    result = SkillResult(
        skill_id="attempt_catch",
        status="uncertain",
        summary="Could not initiate a ball throw from the current battle UI.",
    )

    classification = classify_attempt_catch_failure(
        result,
        execution={
            "throw_execution": {
                "executor": "battle-menu-controller",
                "status": "truncated",
                "throw_initiated": False,
                "summary": "Battle-menu option stopped before initiating a ball throw.",
            }
        },
    )

    assert classification["category"] == "throw_executor_failed"
    assert classification["owner_phase"] == "executor"


def test_attempt_catch_failure_classification_treats_breakout_as_resolved_outcome() -> None:
    result = SkillResult(
        skill_id="attempt_catch",
        status="failed",
        summary="A ball was consumed, but the wild battle continues and party is unchanged.",
    )

    classification = classify_attempt_catch_failure(result, execution={})

    assert classification["category"] == "resolved_skill_outcome"
    assert classification["owner_phase"] == "none"


def test_bag_item_cursor_path_uses_live_cyclic_menu_position() -> None:
    assert bag_item_cursor_path(current_index=0, target_index=1, inventory_slots=4) == ("down",)
    assert bag_item_cursor_path(current_index=2, target_index=1, inventory_slots=4) == ("up",)
    assert bag_item_cursor_path(current_index=4, target_index=1, inventory_slots=4) == ("down", "down")
