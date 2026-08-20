from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.detect_party_changed import detect_party_changed


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT_CATCH_STATES = ROOT / "research" / "skill-states" / "attempt_catch"


def load_record(name: str) -> dict:
    return json.loads((ATTEMPT_CATCH_STATES / f"{name}.skill.json").read_text(encoding="utf-8"))


def test_detect_party_changed_succeeds_when_catch_adds_party_member() -> None:
    before = load_record("success_before")
    after = load_record("success_after")

    result = detect_party_changed(
        after["snapshot"],
        before_snapshot=before["snapshot"],
        target_species="Weedle",
    )

    assert result.status == "succeeded"
    assert "Party roster gained target species Weedle." == result.summary
    assert "target_species=Weedle" in result.evidence


def test_detect_party_changed_fails_when_breakout_keeps_party_unchanged() -> None:
    before = load_record("success_before")
    after = load_record("failed_after_breakout")

    result = detect_party_changed(after["snapshot"], before_snapshot=before["snapshot"])

    assert result.status == "failed"
    assert "unchanged" in result.summary


def test_detect_party_changed_requires_before_snapshot() -> None:
    after = load_record("success_after")

    result = detect_party_changed(after["snapshot"])

    assert result.status == "blocked"
    assert "before snapshot" in result.summary


def test_detect_party_changed_ignores_hp_only_changes() -> None:
    before = {
        "party": [
            {
                "slot": 1,
                "species_id": 84,
                "species_name": "Pikachu",
                "nickname": "PIKACHU",
                "hp": 20,
            }
        ],
        "warnings": [],
    }
    after = {
        "party": [
            {
                "slot": 1,
                "species_id": 84,
                "species_name": "Pikachu",
                "nickname": "PIKACHU",
                "hp": 1,
            }
        ],
        "warnings": [],
    }

    result = detect_party_changed(after, before_snapshot=before)

    assert result.status == "failed"
