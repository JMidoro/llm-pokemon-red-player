from __future__ import annotations

from pathlib import Path

from pokemon_player.skills.switch_party_member import switch_party_member


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


def battle_snapshot(*, active_slot: int = 1, squirtle_hp: int = 29) -> dict:
    party = [
        {"slot": 1, "species_name": "Spearow", "nickname": "SPEAROW", "hp": 15},
        {"slot": 2, "species_name": "Squirtle", "nickname": "SQUIRTLE", "hp": squirtle_hp},
        {"slot": 3, "species_name": "Nidoran M", "nickname": "NIDORAN", "hp": 24},
    ]
    active = next(member for member in party if member["slot"] == active_slot)
    return {
        "mode": "battle",
        "battle_type_raw": 1,
        "active_party_slot": active_slot,
        "active_party_member": active,
        "party": party,
        "warnings": [],
    }


def test_switch_party_member_preconditions_succeed_for_viable_target() -> None:
    result = switch_party_member(battle_snapshot(), target="Squirtle")

    assert result.status == "succeeded"
    assert "can be switched in" in result.summary


def test_switch_party_member_blocks_current_active_target() -> None:
    result = switch_party_member(battle_snapshot(), target="Spearow")

    assert result.status == "blocked"
    assert "already the active battler" in result.summary


def test_switch_party_member_blocks_fainted_target() -> None:
    result = switch_party_member(battle_snapshot(squirtle_hp=0), target="Squirtle")

    assert result.status == "blocked"
    assert "fainted" in result.summary


def test_switch_party_member_blocks_when_battle_dialogue_is_waiting() -> None:
    result = switch_party_member(
        battle_snapshot(),
        target="Squirtle",
        screenshot_path=BATTLE_DIALOGUE_SCREENSHOT,
    )

    assert result.status == "blocked"
    assert "Battle dialogue is waiting" in result.summary


def test_switch_party_member_result_succeeds_on_active_slot_change() -> None:
    before = battle_snapshot(active_slot=1)
    after = battle_snapshot(active_slot=2)

    result = switch_party_member(after, before_snapshot=before, target="Squirtle")

    assert result.status == "succeeded"
    assert "Active battler changed to Squirtle" in result.summary
