from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.close_menu_or_cancel import close_menu_or_cancel


ROOT = Path(__file__).resolve().parents[1]
SKILL_STATES = ROOT / "research" / "skill-states" / "close_menu_or_cancel"


def load_record(name: str) -> dict:
    return json.loads((SKILL_STATES / f"{name}.skill.json").read_text(encoding="utf-8"))


def test_close_menu_or_cancel_matches_human_captured_skill_states() -> None:
    before = load_record("menu_success_before")
    cases = {
        "menu_success_before": ("succeeded", None),
        "menu_success_after": ("succeeded", before["snapshot"]),
        "blocked_no_menu": ("blocked", None),
        "blocked_battle_menu": ("blocked", None),
    }

    for capture_id, (expected_status, before_snapshot) in cases.items():
        record = load_record(capture_id)
        result = close_menu_or_cancel(
            record["snapshot"],
            before_snapshot=before_snapshot,
            screenshot_path=record["screenshot_file"],
        )
        assert result.status == expected_status
        assert result.evidence


def test_close_menu_or_cancel_blocks_clean_overworld() -> None:
    record = load_record("blocked_no_menu")

    result = close_menu_or_cancel(record["snapshot"], screenshot_path=record["screenshot_file"])

    assert result.status == "blocked"
    assert "no menu" in result.summary


def test_close_menu_or_cancel_allows_battle_item_menu(monkeypatch) -> None:
    class BattleUI:
        kind = "item_menu"

    class Visual:
        bottom_text_box = False
        upper_menu = False

    monkeypatch.setattr("pokemon_player.skills.close_menu_or_cancel.inspect_ui_visual_state", lambda _path: Visual())
    monkeypatch.setattr("pokemon_player.skills.close_menu_or_cancel.inspect_battle_ui_screenshot", lambda _path: BattleUI())

    result = close_menu_or_cancel(
        {"mode": "battle", "battle_type_raw": 1, "warnings": []},
        screenshot_path=Path(__file__),
    )

    assert result.status == "succeeded"
    assert "battle item menu" in result.summary


def test_close_menu_or_cancel_allows_normal_battle_party_menu(monkeypatch) -> None:
    class BattleUI:
        kind = "party_menu"

    class Visual:
        bottom_text_box = False
        upper_menu = False

    monkeypatch.setattr("pokemon_player.skills.close_menu_or_cancel.inspect_ui_visual_state", lambda _path: Visual())
    monkeypatch.setattr("pokemon_player.skills.close_menu_or_cancel.inspect_battle_ui_screenshot", lambda _path: BattleUI())
    monkeypatch.setattr("pokemon_player.skills.close_menu_or_cancel.forced_party_selection_prompt_visible", lambda _path: False)

    result = close_menu_or_cancel(
        {"mode": "battle", "battle_type_raw": 1, "warnings": []},
        screenshot_path=Path(__file__),
    )

    assert result.status == "succeeded"
    assert "battle party menu" in result.summary


def test_close_menu_or_cancel_blocks_forced_battle_party_menu(monkeypatch) -> None:
    class BattleUI:
        kind = "party_menu"

    class Visual:
        bottom_text_box = False
        upper_menu = False

    monkeypatch.setattr("pokemon_player.skills.close_menu_or_cancel.inspect_ui_visual_state", lambda _path: Visual())
    monkeypatch.setattr("pokemon_player.skills.close_menu_or_cancel.inspect_battle_ui_screenshot", lambda _path: BattleUI())
    monkeypatch.setattr("pokemon_player.skills.close_menu_or_cancel.forced_party_selection_prompt_visible", lambda _path: True)

    result = close_menu_or_cancel(
        {"mode": "battle", "battle_type_raw": 1, "warnings": []},
        screenshot_path=Path(__file__),
    )

    assert result.status == "blocked"
    assert "Forced party selection" in result.summary
