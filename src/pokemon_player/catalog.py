from __future__ import annotations

import re

from pokemon_player import memory_map as mm


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


SPECIES_BY_NAME = {normalize_name(name): species_id for species_id, name in mm.SPECIES_NAMES.items()}
ITEM_BY_NAME = {normalize_name(name): item_id for item_id, name in mm.ITEM_NAMES.items()}
MOVE_BY_NAME = {normalize_name(name): move_id for move_id, name in mm.MOVE_NAMES.items()}
MAP_BY_NAME = {normalize_name(name): map_id for map_id, name in mm.MAP_NAMES.items()}


def resolve_species(value: int | str) -> int:
    if isinstance(value, int):
        return value
    key = normalize_name(value)
    if key not in SPECIES_BY_NAME:
        raise ValueError(f"Unknown species {value!r}. Promote it to the catalog before use.")
    return SPECIES_BY_NAME[key]


def resolve_item(value: int | str) -> int:
    if isinstance(value, int):
        return value
    key = normalize_name(value)
    if key not in ITEM_BY_NAME:
        raise ValueError(f"Unknown item {value!r}. Promote it to the catalog before use.")
    return ITEM_BY_NAME[key]


def resolve_move(value: int | str) -> int:
    if isinstance(value, int):
        return value
    key = normalize_name(value)
    if key not in MOVE_BY_NAME:
        raise ValueError(f"Unknown move {value!r}. Promote it to the catalog before use.")
    return MOVE_BY_NAME[key]


def resolve_map(value: int | str) -> int:
    if isinstance(value, int):
        return value
    key = normalize_name(value)
    if key not in MAP_BY_NAME:
        raise ValueError(f"Unknown map/location {value!r}. Promote it to the catalog before use.")
    return MAP_BY_NAME[key]
