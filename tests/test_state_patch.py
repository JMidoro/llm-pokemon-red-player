from __future__ import annotations

import pytest

import _path  # noqa: F401

from pokemon_player import memory_map as mm
from pokemon_player.patch_io import patch_from_dict
from pokemon_player.patch_model import (
    RawMemoryWrite,
    RemovePartyMember,
    SetItemQuantity,
    SetBadges,
    SetMapLocation,
    SetMoney,
    SetPartyMoves,
    SetPartySpecies,
    SetPartyStats,
    StatePatch,
)
from pokemon_player.state_inspector import StateInspector
from pokemon_player.state_patch import (
    PatchValidationError,
    StatePatchApplier,
    decode_party_nickname,
    encode_gen1_text,
)


def make_memory() -> list[int]:
    memory = [0] * 0x10000
    memory[mm.PARTY_COUNT] = 2
    memory[mm.PARTY_SPECIES_LIST] = 0xB1
    memory[mm.PARTY_SPECIES_LIST + 1] = 0x24
    memory[mm.PARTY_SPECIES_LIST + 2] = 0xFF

    squirtle = mm.PARTY_STRUCT_START
    memory[squirtle + mm.PARTY_SLOT.species] = 0xB1
    memory[squirtle + mm.PARTY_SLOT.level] = 9
    memory[squirtle + mm.PARTY_SLOT.level_alias] = 9
    memory[squirtle + mm.PARTY_SLOT.hp + 1] = 29
    memory[squirtle + mm.PARTY_SLOT.max_hp + 1] = 29
    memory[squirtle + mm.PARTY_SLOT.move_1] = 0x21
    memory[squirtle + mm.PARTY_SLOT.pp_1] = 35

    pidgey = mm.PARTY_STRUCT_START + mm.PARTY_STRUCT_SIZE
    memory[pidgey + mm.PARTY_SLOT.species] = 0x24
    memory[pidgey + mm.PARTY_SLOT.level] = 3
    memory[pidgey + mm.PARTY_SLOT.level_alias] = 3
    memory[pidgey + mm.PARTY_SLOT.hp + 1] = 12
    memory[pidgey + mm.PARTY_SLOT.max_hp + 1] = 12

    memory[mm.PARTY_NICKNAME_START : mm.PARTY_NICKNAME_START + mm.PARTY_NICKNAME_SIZE] = (
        encode_gen1_text("SQUIRTLE", mm.PARTY_NICKNAME_SIZE)
    )
    second_name = mm.PARTY_NICKNAME_START + mm.PARTY_NICKNAME_SIZE
    memory[second_name : second_name + mm.PARTY_NICKNAME_SIZE] = encode_gen1_text(
        "PIDGEY", mm.PARTY_NICKNAME_SIZE
    )

    memory[mm.ITEM_COUNT] = 1
    memory[mm.ITEM_LIST_START] = 0x04
    memory[mm.ITEM_LIST_START + 1] = 5
    memory[mm.ITEM_LIST_START + 2] = 0xFF
    memory[mm.MONEY_START : mm.MONEY_START + 3] = [0x00, 0x08, 0x75]
    memory[mm.CURRENT_MAP] = 0x33
    memory[mm.PLAYER_X] = 3
    memory[mm.PLAYER_Y] = 41
    return memory


def apply(memory: list[int], *operations) -> None:
    StatePatchApplier(memory).apply(StatePatch(description="test", operations=tuple(operations)))


def test_swap_party_species_updates_species_list_struct_and_nickname() -> None:
    memory = make_memory()

    apply(memory, SetPartySpecies(slot=1, species="Charmander"))

    snapshot = StateInspector(memory).inspect()
    assert snapshot.party[0].species_name == "Charmander"
    assert memory[mm.PARTY_SPECIES_LIST] == 0xB0
    assert decode_party_nickname(memory, 1) == "CHARMANDER"


def test_remove_party_member_compacts_party() -> None:
    memory = make_memory()

    apply(memory, RemovePartyMember(species="Pidgey"))

    snapshot = StateInspector(memory).inspect()
    assert len(snapshot.party) == 1
    assert snapshot.party[0].species_name == "Squirtle"
    assert memory[mm.PARTY_SPECIES_LIST + 1] == 0xFF


def test_set_party_stats_rejects_hp_above_max_hp() -> None:
    memory = make_memory()

    with pytest.raises(PatchValidationError, match="current_hp cannot exceed max_hp"):
        apply(memory, SetPartyStats(slot=1, current_hp=30))


def test_set_party_stats_and_moves() -> None:
    memory = make_memory()

    apply(
        memory,
        SetPartyStats(slot=1, level=8, current_hp=3, max_hp=26, status="poison"),
        SetPartyMoves(slot=1, moves=("ThunderShock", "Growl"), pp=(30, 40)),
    )

    snapshot = StateInspector(memory).inspect()
    assert snapshot.party[0].level == 8
    assert snapshot.party[0].hp == 3
    assert snapshot.party[0].max_hp == 26
    assert snapshot.party[0].status == 0x08
    assert snapshot.party[0].moves[0].move_id == 0x54
    assert snapshot.party[0].moves[1].pp == 40


def test_item_money_and_same_map_location_patch() -> None:
    memory = make_memory()
    memory[mm.CURRENT_MAP] = 0x2A

    apply(
        memory,
        SetItemQuantity(item="Poke Ball", quantity=0),
        SetItemQuantity(item="Potion", quantity=2),
        SetMoney(amount=3000),
        SetMapLocation(map_id="Viridian Mart", x=2, y=3),
    )

    snapshot = StateInspector(memory).inspect()
    assert not snapshot.has_item(0x04)
    assert snapshot.has_item(0x14)
    assert snapshot.money == 3000
    assert snapshot.position is not None
    assert snapshot.position.map_name == "Viridian Mart"


def test_cross_map_location_patch_requires_explicit_unverified_escape_hatch() -> None:
    memory = make_memory()

    with pytest.raises(PatchValidationError, match="Cross-map runtime edits"):
        apply(memory, SetMapLocation(map_id="Viridian Mart", x=2, y=3))


def test_cross_map_location_patch_warns_when_explicitly_allowed() -> None:
    memory = make_memory()

    report = StatePatchApplier(memory).apply(
        StatePatch(
            description="cross map",
            operations=(SetMapLocation(map_id="Viridian Mart", x=2, y=3, allow_cross_map=True),),
        )
    )

    assert report.loud_warnings()


def test_set_badges_by_name() -> None:
    memory = make_memory()

    apply(memory, SetBadges(badge_names=("Boulder Badge", "Cascade Badge")))

    snapshot = StateInspector(memory).inspect()
    assert snapshot.badge_names() == ("Boulder Badge", "Cascade Badge")


def test_raw_memory_write_warns_loudly() -> None:
    memory = make_memory()

    report = StatePatchApplier(memory).apply(
        StatePatch(
            description="danger",
            operations=(RawMemoryWrite(address=0xD000, value=0x12, reason="test unverified path"),),
        )
    )

    assert memory[0xD000] == 0x12
    assert report.loud_warnings()


def test_patch_from_dict() -> None:
    patch = patch_from_dict(
        {
            "description": "remove balls",
            "goal": "force purchase flow",
            "operations": [
                {"type": "set_item_quantity", "item": "Poke Ball", "quantity": 0},
                {"type": "set_money", "amount": 3000},
            ],
        }
    )

    assert patch.description == "remove balls"
    assert len(patch.operations) == 2
