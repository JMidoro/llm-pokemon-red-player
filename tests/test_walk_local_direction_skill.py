from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.walk_local_direction import walk_local_direction


ROOT = Path(__file__).resolve().parents[1]
SKILL_STATES = ROOT / "research" / "skill-states" / "walk_local_direction"


def load_record(name: str) -> dict:
    return json.loads((SKILL_STATES / f"{name}.skill.json").read_text(encoding="utf-8"))


def test_walk_local_direction_matches_human_captured_skill_states() -> None:
    before = load_record("step_success_before")
    cases = {
        "step_success_before": ("succeeded", None, None),
        "step_success_after": ("succeeded", before["snapshot"], "left"),
        "blocked_wall_or_npc": ("blocked", None, "left"),
        "blocked_wrong_mode": ("blocked", None, "left"),
    }

    for capture_id, (expected_status, before_snapshot, direction) in cases.items():
        record = load_record(capture_id)
        result = walk_local_direction(
            record["snapshot"],
            before_snapshot=before_snapshot,
            direction=direction,
            screenshot_path=record["screenshot_file"],
        )
        assert result.status == expected_status
        assert result.evidence


def test_walk_local_direction_blocks_when_attempt_does_not_move() -> None:
    before = load_record("step_success_before")

    result = walk_local_direction(
        before["snapshot"],
        before_snapshot=before["snapshot"],
        direction="left",
    )

    assert result.status == "blocked"
    assert "did not change coordinates" in result.summary
