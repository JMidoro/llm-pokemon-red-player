from __future__ import annotations

from pokemon_player.capsule_a_navigation import Position
from pokemon_player.pallet_navigation import LANDMARKS
from pokemon_player.skills.complete_prologue import complete_prologue


def fresh_boot_snapshot() -> dict:
    return {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x00, "x": 0, "y": 0},
        "party": [],
        "warnings": [],
    }


def test_complete_prologue_can_start_from_clean_boot_sentinel() -> None:
    result = complete_prologue(fresh_boot_snapshot(), player_name="RED", rival_name="BLUE")

    assert result.status == "succeeded"
    assert "clean boot" in result.summary


def test_complete_prologue_validates_name_length() -> None:
    result = complete_prologue(fresh_boot_snapshot(), player_name="TOOLONGG", rival_name="BLUE")

    assert result.status == "blocked"
    assert "Player name" in result.summary


def test_complete_prologue_succeeds_at_pallet_handoff() -> None:
    before = fresh_boot_snapshot()
    after = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x00, "x": 5, "y": 6},
        "party": [],
        "warnings": [],
    }

    result = complete_prologue(after, before_snapshot=before, handoff="pallet_outside")

    assert result.status == "succeeded"
    assert "Pallet Town outside Red's house" in result.summary


def test_red_bedroom_stair_landmark_matches_prologue_probe() -> None:
    assert LANDMARKS["pallet_bedroom_exit"].position == Position(0x26, 6, 1)
