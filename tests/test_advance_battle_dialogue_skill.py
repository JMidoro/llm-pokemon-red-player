from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.advance_battle_dialogue import advance_battle_dialogue


ROOT = Path(__file__).resolve().parents[1]
SKILL_STATES = ROOT / "research" / "skill-states" / "attempt_catch"


def load_record(name: str) -> dict:
    return json.loads((SKILL_STATES / f"{name}.skill.json").read_text(encoding="utf-8"))


def test_advance_battle_dialogue_detects_waiting_battle_text() -> None:
    record = load_record("uncertain_throw_dialogue")

    result = advance_battle_dialogue(record["snapshot"], screenshot_path=record["screenshot_file"])

    assert result.status == "succeeded"
    assert "dialogue" in " ".join(result.evidence)


def test_advance_battle_dialogue_blocks_when_action_menu_is_available() -> None:
    record = load_record("success_before")

    result = advance_battle_dialogue(record["snapshot"], screenshot_path=record["screenshot_file"])

    assert result.status == "blocked"
    assert "action menu" in result.summary


def test_advance_battle_dialogue_settles_unknown_active_battle_ui() -> None:
    snapshot = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x0D, "x": 6, "y": 4},
        "enemy": {"species_name": "Rattata", "hp": 15, "max_hp": 15},
    }

    result = advance_battle_dialogue(snapshot, screenshot_path=ROOT / "does-not-exist.png")

    assert result.status == "succeeded"
    assert "settling" in result.summary


def test_advance_battle_dialogue_marks_return_to_action_menu_as_success() -> None:
    before = load_record("uncertain_throw_dialogue")
    after = load_record("success_before")

    result = advance_battle_dialogue(
        after["snapshot"],
        before_snapshot=before["snapshot"],
        screenshot_path=after["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "action menu" in result.summary
