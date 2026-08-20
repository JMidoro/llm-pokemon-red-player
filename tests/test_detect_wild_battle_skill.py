from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.detect_wild_battle import detect_wild_battle


ROOT = Path(__file__).resolve().parents[1]
SKILL_STATES = ROOT / "research" / "skill-states" / "detect_wild_battle"
GOLDEN_STATES = ROOT / "research" / "golden-states"


def load_snapshot(path: Path) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    return record["snapshot"]


def test_detect_wild_battle_matches_human_captured_skill_states() -> None:
    cases = {
        "success_wild_battle.skill.json": "succeeded",
        "failed_overworld.skill.json": "failed",
        "uncertain_ui_or_unknown_battle.skill.json": "uncertain",
    }

    for filename, expected_status in cases.items():
        result = detect_wild_battle(load_snapshot(SKILL_STATES / filename))
        assert result.status == expected_status
        assert result.evidence


def test_detect_wild_battle_keeps_trainer_battle_uncertain() -> None:
    result = detect_wild_battle(load_snapshot(GOLDEN_STATES / "mid_misty_battle.expected.json"))

    assert result.status == "uncertain"
    assert "battle_type_raw=2" in result.evidence


def test_detect_wild_battle_accepts_other_wild_battle_maps() -> None:
    result = detect_wild_battle(load_snapshot(GOLDEN_STATES / "mt_moon_battle_paras.expected.json"))

    assert result.status == "succeeded"
    assert "outside the first Capsule A map" in result.summary
