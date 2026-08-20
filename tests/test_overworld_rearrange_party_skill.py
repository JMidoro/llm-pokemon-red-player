from __future__ import annotations

from pokemon_player.skill_execution import cyclic_menu_path, path_between_vertical_slots
from pokemon_player.skills.overworld_rearrange_party import overworld_rearrange_party


def overworld_snapshot(*, party: list[dict] | None = None) -> dict:
    return {
        "mode": "overworld",
        "battle_type_raw": 0,
        "party": party
        or [
            {"slot": 1, "species_id": 21, "species_name": "Spearow", "nickname": "SPEAROW", "level": 8},
            {"slot": 2, "species_id": 7, "species_name": "Squirtle", "nickname": "SQUIRTLE", "level": 10},
            {"slot": 3, "species_id": 16, "species_name": "Pidgey", "nickname": "PIDGEY", "level": 5},
        ],
        "warnings": [],
    }


def battle_snapshot() -> dict:
    snapshot = overworld_snapshot()
    snapshot["mode"] = "battle"
    snapshot["battle_type_raw"] = 1
    return snapshot


def test_overworld_rearrange_party_preconditions_succeed_for_valid_move() -> None:
    result = overworld_rearrange_party(overworld_snapshot(), target="Squirtle", destination_slot=1)

    assert result.status == "succeeded"
    assert "can be moved" in result.summary


def test_overworld_rearrange_party_succeeds_when_already_in_slot() -> None:
    result = overworld_rearrange_party(overworld_snapshot(), target="Spearow", destination_slot=1)

    assert result.status == "succeeded"
    assert "already in party slot 1" in result.summary
    assert "noop=true" in result.evidence


def test_overworld_rearrange_party_blocks_wrong_mode() -> None:
    result = overworld_rearrange_party(battle_snapshot(), target="Squirtle", destination_slot=1)

    assert result.status == "blocked"
    assert "stable overworld" in result.summary


def test_overworld_rearrange_party_blocks_invalid_destination() -> None:
    result = overworld_rearrange_party(overworld_snapshot(), target="Squirtle", destination_slot=6)

    assert result.status == "blocked"
    assert "outside the current party size" in result.summary


def test_overworld_rearrange_party_result_succeeds_on_requested_order() -> None:
    before = overworld_snapshot()
    after = overworld_snapshot(
        party=[
            {"slot": 1, "species_id": 7, "species_name": "Squirtle", "nickname": "SQUIRTLE", "level": 10},
            {"slot": 2, "species_id": 21, "species_name": "Spearow", "nickname": "SPEAROW", "level": 8},
            {"slot": 3, "species_id": 16, "species_name": "Pidgey", "nickname": "PIDGEY", "level": 5},
        ]
    )

    result = overworld_rearrange_party(after, before_snapshot=before, target="Squirtle", destination_slot=1)

    assert result.status == "succeeded"
    assert "moved from party slot 2 to slot 1" in result.summary


def test_overworld_rearrange_party_result_fails_when_order_does_not_change() -> None:
    before = overworld_snapshot()
    after = overworld_snapshot()

    result = overworld_rearrange_party(after, before_snapshot=before, target="Squirtle", destination_slot=1)

    assert result.status == "failed"
    assert "stayed in party slot 2" in result.summary


def test_overworld_rearrange_party_result_uncertain_when_roster_changes() -> None:
    before = overworld_snapshot()
    after = overworld_snapshot(
        party=[
            {"slot": 1, "species_id": 7, "species_name": "Squirtle", "nickname": "SQUIRTLE", "level": 10},
            {"slot": 2, "species_id": 21, "species_name": "Spearow", "nickname": "SPEAROW", "level": 8},
        ]
    )

    result = overworld_rearrange_party(after, before_snapshot=before, target="Squirtle", destination_slot=1)

    assert result.status == "uncertain"
    assert "Party roster changed" in result.summary


def test_cyclic_menu_path_handles_remembered_start_menu_cursor() -> None:
    assert cyclic_menu_path(1, 1, 7) == ()
    assert cyclic_menu_path(2, 1, 7) == ("up",)
    assert cyclic_menu_path(6, 1, 7) == ("down", "down")


def test_party_slot_cursor_path_uses_linear_zero_based_movement_to_avoid_cancel_row() -> None:
    assert path_between_vertical_slots(3, 0) == ("up", "up", "up")
    assert path_between_vertical_slots(0, 3) == ("down", "down", "down")
