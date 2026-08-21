from __future__ import annotations

from typing import Any

from pokemon_player import memory_map as mm


# Families are expressed in National Pokedex numbers so that evolution and nickname changes do
# not change encounter provenance. Single-stage Pokemon intentionally have one-member families.
GEN1_EVOLUTION_FAMILIES: tuple[tuple[int, ...], ...] = (
    (1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12), (13, 14, 15), (16, 17, 18),
    (19, 20), (21, 22), (23, 24), (25, 26), (27, 28), (29, 30, 31), (32, 33, 34),
    (35, 36), (37, 38), (39, 40), (41, 42), (43, 44, 45), (46, 47), (48, 49),
    (50, 51), (52, 53), (54, 55), (56, 57), (58, 59), (60, 61, 62), (63, 64, 65),
    (66, 67, 68), (69, 70, 71), (72, 73), (74, 75, 76), (77, 78), (79, 80),
    (81, 82), (83,), (84, 85), (86, 87), (88, 89), (90, 91), (92, 93, 94), (95,),
    (96, 97), (98, 99), (100, 101), (102, 103), (104, 105), (106,), (107,), (108,),
    (109, 110), (111, 112), (113,), (114,), (115,), (116, 117), (118, 119),
    (120, 121), (122,), (123,), (124,), (125,), (126,), (127,), (128,), (129, 130),
    (131,), (132,), (133, 134, 135, 136), (137,), (138, 139), (140, 141), (142,),
    (143,), (144,), (145,), (146,), (147, 148, 149), (150,), (151,),
)

DEX_TO_FAMILY = {
    dex_number: family
    for family in GEN1_EVOLUTION_FAMILIES
    for dex_number in family
}


def evolution_family(dex_number: int | None) -> tuple[int, ...] | None:
    if dex_number is None:
        return None
    return DEX_TO_FAMILY.get(int(dex_number), (int(dex_number),))


def family_id(dex_number: int | None) -> str | None:
    family = evolution_family(dex_number)
    return f"dex-family-{family[0]:03d}" if family else None


def species_dex_number(species_id: int | None) -> int | None:
    if species_id is None:
        return None
    return mm.SPECIES_DEX_NUMBERS.get(int(species_id))


def canonical_area(
    position: dict[str, Any] | None,
    area_aliases: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(position, dict):
        return None
    raw_map_id = position.get("map_id")
    try:
        map_id = int(raw_map_id)
    except (TypeError, ValueError):
        return None
    aliases = area_aliases or {}
    keys = (str(map_id), f"0x{map_id:02X}", f"{map_id:02X}")
    area_id = next((aliases[key] for key in keys if key in aliases), None)
    if not area_id:
        area_id = f"map-{map_id:02x}"
    return {
        "id": str(area_id),
        "mapId": map_id,
        "mapName": str(position.get("map_name") or mm.map_name(map_id)),
        "x": position.get("x"),
        "y": position.get("y"),
    }
