from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.recover_to_overworld import (
    recover_to_overworld,
    screenshot_has_overworld_ui_overlay,
)


ROOT = Path(__file__).resolve().parents[1]
SKILL_STATES = ROOT / "research" / "skill-states" / "recover_to_overworld"
SCREENSHOTS = ROOT / "research" / "skill-states" / "local" / "recover_to_overworld"


def load_record(name: str) -> dict:
    return json.loads((SKILL_STATES / f"{name}.skill.json").read_text(encoding="utf-8"))


def test_recover_to_overworld_matches_human_captured_skill_states() -> None:
    before_menu = load_record("menu_success_before")
    before_dialogue = load_record("dialogue_success_before")
    cases = {
        "menu_success_before": ("succeeded", None),
        "menu_success_after": ("succeeded", before_menu["snapshot"]),
        "dialogue_success_before": ("succeeded", None),
        "dialogue_success_after": ("succeeded", before_dialogue["snapshot"]),
        "noop_overworld": ("succeeded", None),
        "blocked_battle": ("blocked", None),
    }

    for capture_id, (expected_status, before_snapshot) in cases.items():
        record = load_record(capture_id)
        result = recover_to_overworld(
            record["snapshot"],
            before_snapshot=before_snapshot,
            screenshot_path=record["screenshot_file"],
        )
        assert result.status == expected_status
        assert result.evidence


def test_recover_to_overworld_keeps_stale_overworld_warning_successful() -> None:
    record = load_record("noop_overworld")

    result = recover_to_overworld(record["snapshot"], screenshot_path=record["screenshot_file"])

    assert result.status == "succeeded"
    assert result.warnings


def test_recover_to_overworld_unknown_mode_is_uncertain() -> None:
    result = recover_to_overworld({"mode": "unknown", "battle_type_raw": 0, "warnings": []})

    assert result.status == "uncertain"


def test_recover_to_overworld_screenshot_detector_finds_dialogue_or_menu_overlay() -> None:
    assert screenshot_has_overworld_ui_overlay(SCREENSHOTS / "dialogue_success_before.png")
    assert screenshot_has_overworld_ui_overlay(SCREENSHOTS / "menu_success_before.png")
