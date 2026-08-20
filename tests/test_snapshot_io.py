import _path  # noqa: F401

from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict
from pokemon_player.state_model import (
    BattleEnemy,
    GameMode,
    GameSnapshot,
    InventoryItem,
    MapPosition,
    PartyMember,
    StoryEvent,
)


def test_snapshot_to_dict_is_director_friendly() -> None:
    snapshot = GameSnapshot(
        mode=GameMode.OVERWORLD,
        position=MapPosition(map_id=0x33, x=2, y=3),
        party=(),
        inventory=(InventoryItem(item_id=0x04, quantity=3),),
        money=500,
        badges=0,
    )

    raw = snapshot_to_dict(snapshot)

    assert raw["mode"] == "overworld"
    assert raw["position"]["map_name"] == "Viridian Forest"
    assert raw["inventory"][0]["item_name"] == "Poke Ball"
    assert "plaintext_summary" in raw


def test_snapshot_hash_is_stable() -> None:
    snapshot = GameSnapshot(
        mode=GameMode.OVERWORLD,
        position=MapPosition(map_id=0x33, x=2, y=3),
        party=(),
        inventory=(),
        money=500,
        badges=0,
    )

    assert snapshot_hash(snapshot) == snapshot_hash(snapshot)


def test_snapshot_to_dict_includes_battle_enemy_when_present() -> None:
    snapshot = GameSnapshot(
        mode=GameMode.BATTLE,
        position=MapPosition(map_id=0x33, x=2, y=3),
        party=(),
        inventory=(),
        money=500,
        badges=0,
        battle_type_raw=1,
        enemy=BattleEnemy(species_id=0x70, level=3, hp=6, max_hp=13, status=0, catch_rate=255),
    )

    raw = snapshot_to_dict(snapshot)

    assert raw["enemy"]["species_name"] == "Weedle"
    assert raw["enemy"]["hp"] == 6
    assert raw["enemy"]["max_hp"] == 13


def test_snapshot_to_dict_includes_active_party_member_when_present() -> None:
    snapshot = GameSnapshot(
        mode=GameMode.BATTLE,
        position=MapPosition(map_id=0x33, x=2, y=3),
        party=(
            PartyMember(slot=1, species_id=0x05, level=3, hp=15, max_hp=15, status=0, moves=()),
            PartyMember(slot=2, species_id=0xB1, level=8, hp=29, max_hp=29, status=0, moves=()),
        ),
        inventory=(),
        money=500,
        badges=0,
        battle_type_raw=1,
        active_party_slot=2,
    )

    raw = snapshot_to_dict(snapshot)

    assert raw["active_party_slot"] == 2
    assert raw["active_party_member"]["species_name"] == "Squirtle"


def test_snapshot_to_dict_includes_story_event_flags_and_address_details() -> None:
    snapshot = GameSnapshot(
        mode=GameMode.OVERWORLD,
        position=MapPosition(map_id=0x2A, x=2, y=5),
        party=(),
        inventory=(),
        money=500,
        badges=0,
        story_events=(
            StoryEvent(
                key="oak_got_parcel",
                pret_name="EVENT_OAK_GOT_PARCEL",
                label="Oak received parcel",
                address=0xD74E,
                bit=0,
                mask=0x01,
                value=True,
                source="test",
            ),
        ),
    )

    raw = snapshot_to_dict(snapshot)

    assert raw["story_events"] == {"oak_got_parcel": True}
    assert raw["story_event_details"][0]["address_hex"] == "0xD74E"
    assert raw["story_event_details"][0]["bit"] == 0
