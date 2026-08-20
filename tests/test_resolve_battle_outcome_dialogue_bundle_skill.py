from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.resolve_battle_outcome_dialogue_bundle import (
    resolve_battle_outcome_dialogue_bundle,
    screenshot_has_pokedex_intro_dialogue,
)


ROOT = Path(__file__).resolve().parents[1]
SKILL_STATES = ROOT / "research" / "skill-states" / "resolve_battle_outcome_dialogue_bundle"
PARTY_SWITCH_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "party_switch_and_active_battler"
MANUAL_INPUT = ROOT / "research" / "artifacts" / "director-player-runs" / "manual_input"


def load_skill_record(name: str) -> dict:
    return json.loads((SKILL_STATES / f"{name}.skill.json").read_text(encoding="utf-8"))


def load_promotion_record(name: str) -> dict:
    return json.loads((PARTY_SWITCH_EVIDENCE / f"{name}.promotion-evidence.json").read_text(encoding="utf-8"))


def test_resolve_bundle_enables_on_captured_outcome_dialogue_states() -> None:
    for capture_id in [
        "post_catch_dialogue_before",
        "post_catch_dialogue_after",
        "victory_dialogue_before",
        "xp_or_level_up_dialogue",
        "level_up_text",
    ]:
        record = load_skill_record(capture_id)

        result = resolve_battle_outcome_dialogue_bundle(
            record["snapshot"],
            screenshot_path=record["screenshot_file"],
        )

        assert result.status == "succeeded", capture_id
        assert result.evidence


def test_resolve_bundle_blocks_neutral_action_menu() -> None:
    record = load_promotion_record("step_01_active_battler_baseline")

    result = resolve_battle_outcome_dialogue_bundle(
        record["snapshot"],
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "blocked"
    assert "action menu" in result.summary


def test_resolve_bundle_does_not_auto_advance_forced_party_selection() -> None:
    record = load_promotion_record("step_01_party_menu_forced_nidoran")

    result = resolve_battle_outcome_dialogue_bundle(
        record["snapshot"],
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "uncertain"
    assert "Party selection" in result.summary


def test_resolve_bundle_reports_one_prompt_progress_as_success() -> None:
    before = load_skill_record("victory_dialogue_before")
    after = load_skill_record("xp_or_level_up_dialogue")

    result = resolve_battle_outcome_dialogue_bundle(
        after["snapshot"],
        before_snapshot=before["snapshot"],
        screenshot_path=after["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "one battle outcome dialogue prompt" in result.summary


def test_resolve_bundle_handles_pre_pokedex_post_catch_dialogue() -> None:
    report = json.loads((MANUAL_INPUT / "a-20260624T232150151921Z0000" / "report.json").read_text(encoding="utf-8"))
    screenshot = MANUAL_INPUT / "a-20260624T232150151921Z0000" / "before.png"

    result = resolve_battle_outcome_dialogue_bundle(
        report["before"],
        screenshot_path=screenshot,
    )

    assert screenshot_has_pokedex_intro_dialogue(screenshot) is True
    assert result.status == "succeeded"
    assert "can be advanced" in result.summary
