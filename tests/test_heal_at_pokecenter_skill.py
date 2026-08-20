from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.heal_at_pokecenter import heal_at_pokecenter, party_fully_healed, party_needs_healing


ROOT = Path(__file__).resolve().parents[1]
MANUAL_INPUT = ROOT / "research" / "artifacts" / "director-player-runs" / "manual_input"
GOLDEN = ROOT / "research" / "golden-states"


def load_manual_report(name: str) -> dict:
    return json.loads((MANUAL_INPUT / name / "report.json").read_text(encoding="utf-8"))


def test_heal_at_pokecenter_available_when_party_needs_healing_inside_center() -> None:
    report = load_manual_report("up-20260625T003351869669Z0000")

    result = heal_at_pokecenter(report["before"], screenshot_path=report["beforeScreenshotPath"])

    assert result.status == "succeeded"
    assert party_needs_healing(report["before"]) is True
    assert party_fully_healed(report["before"]) is False


def test_heal_at_pokecenter_verifies_party_restored_after_nurse_dialogue() -> None:
    before = load_manual_report("a-20260625T003357497970Z0000")
    after = load_manual_report("a-20260625T003414357490Z0000")

    result = heal_at_pokecenter(
        after["before"],
        before_snapshot=before["before"],
        screenshot_path=after["beforeScreenshotPath"],
    )

    assert result.status == "succeeded"
    assert party_fully_healed(after["before"]) is True


def test_heal_at_pokecenter_supports_pewter_center() -> None:
    record = json.loads((GOLDEN / "pewter_pokecenter_counter.expected.json").read_text(encoding="utf-8"))

    result = heal_at_pokecenter(record["snapshot"], screenshot_path=record["screenshot_file"])

    assert result.status == "succeeded"
    assert "PokeCenter" in result.summary


def test_heal_at_pokecenter_blocks_outside_center_or_battle() -> None:
    assert heal_at_pokecenter({"mode": "battle", "battle_type_raw": 1}).status == "blocked"
    assert heal_at_pokecenter(
        {"mode": "overworld", "battle_type_raw": 0, "position": {"map_id": 0x33, "x": 1, "y": 1}}
    ).status == "blocked"
