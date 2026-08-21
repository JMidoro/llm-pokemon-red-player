from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from pokemon_player.memory_map import move_name
from pokemon_player.state_model import (
    BattleEnemy,
    GameSnapshot,
    InventoryItem,
    MapPosition,
    MoveSlot,
    PartyMember,
    StoryEvent,
)


def move_to_dict(move: MoveSlot) -> dict[str, int | str | None]:
    return {
        "move_id": move.move_id,
        "move_name": move_name(move.move_id),
        "pp": move.pp,
    }


def party_member_to_dict(member: PartyMember) -> dict[str, Any]:
    return {
        "slot": member.slot,
        "species_id": member.species_id,
        "species_name": member.species_name,
        "level": member.level,
        "hp": member.hp,
        "max_hp": member.max_hp,
        "status": member.status,
        "moves": [move_to_dict(move) for move in member.moves],
        "nickname": member.nickname,
    }


def inventory_item_to_dict(item: InventoryItem) -> dict[str, int | str]:
    return {
        "item_id": item.item_id,
        "item_name": item.item_name,
        "quantity": item.quantity,
    }


def enemy_to_dict(enemy: BattleEnemy) -> dict[str, int | str | None]:
    return {
        "species_id": enemy.species_id,
        "species_name": enemy.species_name,
        "level": enemy.level,
        "hp": enemy.hp,
        "max_hp": enemy.max_hp,
        "status": enemy.status,
        "catch_rate": enemy.catch_rate,
    }


def story_event_to_dict(event: StoryEvent) -> dict[str, int | str | bool]:
    return {
        "key": event.key,
        "pret_name": event.pret_name,
        "label": event.label,
        "address": event.address,
        "address_hex": f"0x{event.address:04X}",
        "bit": event.bit,
        "mask": event.mask,
        "mask_hex": f"0x{event.mask:02X}",
        "value": event.value,
        "source": event.source,
    }


def position_to_dict(position: MapPosition | None) -> dict[str, int | str] | None:
    if position is None:
        return None
    return {
        "map_id": position.map_id,
        "map_name": position.map_name,
        "x": position.x,
        "y": position.y,
    }


def snapshot_to_dict(snapshot: GameSnapshot) -> dict[str, Any]:
    active_member = (
        next(
            (member for member in snapshot.party if member.slot == snapshot.active_party_slot),
            None,
        )
        if snapshot.active_party_slot is not None
        else None
    )
    raw = {
        "mode": snapshot.mode.value,
        "position": position_to_dict(snapshot.position),
        "party": [party_member_to_dict(member) for member in snapshot.party],
        "inventory": [inventory_item_to_dict(item) for item in snapshot.inventory],
        "money": snapshot.money,
        "badges": snapshot.badges,
        "badge_names": list(snapshot.badge_names()),
        "options_raw": snapshot.options_raw,
        "battle_style": snapshot.battle_style,
        "battle_type_raw": snapshot.battle_type_raw,
        "story_events": {event.key: event.value for event in snapshot.story_events},
        "story_event_details": [story_event_to_dict(event) for event in snapshot.story_events],
        "pokedex_owned_dex_numbers": list(snapshot.pokedex_owned_dex_numbers),
        "pokedex_seen_dex_numbers": list(snapshot.pokedex_seen_dex_numbers),
        "facts": list(snapshot.facts()),
        "warnings": list(snapshot.warnings),
        "plaintext_summary": snapshot.plaintext_summary(),
    }
    if snapshot.active_party_slot is not None:
        raw["active_party_slot"] = snapshot.active_party_slot
        raw["active_party_member"] = party_member_to_dict(active_member) if active_member else None
    if snapshot.enemy:
        raw["enemy"] = enemy_to_dict(snapshot.enemy)
    return raw


def stable_snapshot_json(snapshot: GameSnapshot) -> str:
    return json.dumps(snapshot_to_dict(snapshot), indent=2, sort_keys=True)


def snapshot_hash(snapshot: GameSnapshot) -> str:
    return sha256(stable_snapshot_json(snapshot).encode("utf-8")).hexdigest().upper()
