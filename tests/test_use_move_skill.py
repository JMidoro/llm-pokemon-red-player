from __future__ import annotations

from pathlib import Path

from pokemon_player.skill_execution import path_to_battle_move_slot
from pokemon_player.skills.use_move import use_move


ROOT = Path(__file__).resolve().parents[1]
BATTLE_DIALOGUE_SCREENSHOT = (
    ROOT
    / "research"
    / "promotions"
    / "evidence"
    / "local"
    / "battle_dialogue_advancement_contract"
    / "step_01_move_dialogue_before.png"
)


def battle_snapshot(*, water_gun_pp: int = 25, enemy_hp: int = 30) -> dict:
    return {
        "mode": "battle",
        "battle_type_raw": 1,
        "active_party_slot": 1,
        "active_party_member": {
            "slot": 1,
            "species_name": "Wartortle",
            "moves": [
                {"move_id": 33, "move_name": "Tackle", "pp": 35},
                {"move_id": 39, "move_name": "Tail Whip", "pp": 30},
                {"move_id": 145, "move_name": "Bubble", "pp": 30},
                {"move_id": 55, "move_name": "Water Gun", "pp": water_gun_pp},
            ],
        },
        "party": [
            {
                "slot": 1,
                "species_name": "Wartortle",
                "moves": [
                    {"move_id": 33, "move_name": "Tackle", "pp": 35},
                    {"move_id": 39, "move_name": "Tail Whip", "pp": 30},
                    {"move_id": 145, "move_name": "Bubble", "pp": 30},
                    {"move_id": 55, "move_name": "Water Gun", "pp": water_gun_pp},
                ],
            }
        ],
        "enemy": {"hp": enemy_hp, "max_hp": 30},
        "warnings": [],
    }


def test_use_move_preconditions_succeed_for_known_move_with_pp() -> None:
    result = use_move(battle_snapshot(), requested_move="Water Gun")

    assert result.status == "succeeded"
    assert "active move slot 4" in result.summary


def test_use_move_blocks_missing_requested_move() -> None:
    result = use_move(battle_snapshot(), requested_move="Hyper Beam")

    assert result.status == "blocked"
    assert "does not know Hyper Beam" in result.summary


def test_use_move_blocks_zero_pp() -> None:
    result = use_move(battle_snapshot(water_gun_pp=0), requested_move="Water Gun")

    assert result.status == "blocked"
    assert "0 PP" in result.summary


def test_use_move_blocks_when_battle_dialogue_is_waiting() -> None:
    result = use_move(battle_snapshot(), requested_move="Water Gun", screenshot_path=BATTLE_DIALOGUE_SCREENSHOT)

    assert result.status == "blocked"
    assert "Battle dialogue is waiting" in result.summary


def test_use_move_blocks_on_unclassified_battle_dialogue_box() -> None:
    screenshot = (
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T214713690246Z"
        / "action_063_before.png"
    )

    result = use_move(
        {
            "mode": "battle",
            "battle_type_raw": 2,
            "active_party_slot": 3,
            "party": [
                {
                    "slot": 3,
                    "species_name": "Pikachu",
                    "moves": [{"move_id": 84, "move_name": "ThunderShock", "pp": 29}],
                }
            ],
        },
        requested_move="ThunderShock",
        screenshot_path=screenshot,
    )

    assert result.status == "blocked"
    assert "wait for the action or move menu" in result.summary


def test_use_move_can_start_from_battle_item_menu(monkeypatch) -> None:
    class UI:
        kind = "item_menu"

    monkeypatch.setattr("pokemon_player.skills.use_move.inspect_battle_ui_screenshot", lambda _path: UI())

    result = use_move(battle_snapshot(), requested_move="Water Gun", screenshot_path=Path("screen.png"))

    assert result.status == "succeeded"
    assert "active move slot 4" in result.summary


def test_use_move_can_recover_from_non_forced_battle_party_menu(monkeypatch) -> None:
    class UI:
        kind = "party_menu"

    monkeypatch.setattr("pokemon_player.skills.use_move.inspect_battle_ui_screenshot", lambda _path: UI())
    monkeypatch.setattr("pokemon_player.skills.use_move.forced_party_selection_prompt_visible", lambda _path: False)

    result = use_move(battle_snapshot(), requested_move="Water Gun", screenshot_path=Path("screen.png"))

    assert result.status == "succeeded"


def test_use_move_blocks_forced_party_selection(monkeypatch) -> None:
    class UI:
        kind = "party_menu"

    monkeypatch.setattr("pokemon_player.skills.use_move.inspect_battle_ui_screenshot", lambda _path: UI())
    monkeypatch.setattr("pokemon_player.skills.use_move.forced_party_selection_prompt_visible", lambda _path: True)

    result = use_move(battle_snapshot(), requested_move="Water Gun", screenshot_path=Path("screen.png"))

    assert result.status == "blocked"
    assert "Forced party selection" in result.summary


def test_use_move_result_succeeds_on_requested_pp_delta() -> None:
    before = battle_snapshot(water_gun_pp=25)
    after = battle_snapshot(water_gun_pp=24, enemy_hp=10)

    result = use_move(after, before_snapshot=before, requested_move="Water Gun")

    assert result.status == "succeeded"
    assert "PP decreased" in result.summary
    assert "pp_delta=-1" in result.evidence


def test_use_move_routing_can_start_from_move_menu_cursor() -> None:
    assert path_to_battle_move_slot("move_1", 3) == ("down", "down")
    assert path_to_battle_move_slot("move_3", 1) == ("up", "up")
    assert path_to_battle_move_slot("move_2", 2) == ()
