import _path  # noqa: F401

from pokemon_player.invariants import check_snapshot_invariants
from pokemon_player.state_model import GameMode, GameSnapshot, InventoryItem, MapPosition, PartyMember


def test_invariants_reject_empty_party() -> None:
    result = check_snapshot_invariants(
        GameSnapshot(
            mode=GameMode.OVERWORLD,
            position=MapPosition(map_id=0x33, x=1, y=1),
            party=(),
            inventory=(),
            money=0,
            badges=0,
        )
    )

    assert not result.ok
    assert "Party must not be empty." in result.errors


def test_invariants_reject_hp_above_max() -> None:
    result = check_snapshot_invariants(
        GameSnapshot(
            mode=GameMode.OVERWORLD,
            position=MapPosition(map_id=0x33, x=1, y=1),
            party=(
                PartyMember(
                    slot=1,
                    species_id=0x54,
                    level=5,
                    hp=20,
                    max_hp=10,
                    status=0,
                    moves=(),
                    nickname="PIKACHU",
                ),
            ),
            inventory=(InventoryItem(item_id=0x04, quantity=5),),
            money=0,
            badges=0,
        )
    )

    assert not result.ok
    assert any("HP above max HP" in error for error in result.errors)
