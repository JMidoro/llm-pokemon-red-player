from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pokemon_player.capsule_a_navigation import Landmark, Position, at_landmark, normalize_target


MAP_PALLET_TOWN = 0x00
MAP_VIRIDIAN_CITY = 0x01
MAP_ROUTE_1 = 0x0C
MAP_REDS_HOUSE_1F = 0x25
MAP_REDS_HOUSE_2F = 0x26
MAP_RIVALS_HOUSE = 0x27
MAP_OAKS_LAB = 0x28
MAP_VIRIDIAN_MART = 0x2A

PALLET_MAP_IDS = frozenset(
    {
        MAP_PALLET_TOWN,
        MAP_VIRIDIAN_CITY,
        MAP_ROUTE_1,
        MAP_REDS_HOUSE_1F,
        MAP_REDS_HOUSE_2F,
        MAP_RIVALS_HOUSE,
        MAP_OAKS_LAB,
        MAP_VIRIDIAN_MART,
    }
)


@dataclass(frozen=True)
class PalletTransition:
    source: Position
    button: str
    destination_map: int
    destination_hint: Position


LANDMARKS: dict[str, Landmark] = {
    "pallet_bedroom_entrance": Landmark(
        "pallet_bedroom_entrance",
        "Pallet bedroom stair landing",
        Position(MAP_REDS_HOUSE_2F, 6, 1),
        source="local_prologue_probe",
    ),
    "pallet_bedroom_exit": Landmark(
        "pallet_bedroom_exit",
        "Pallet bedroom stairs down",
        Position(MAP_REDS_HOUSE_2F, 6, 1),
        source="local_prologue_probe",
    ),
    "pallet_home_1f_entrance": Landmark(
        "pallet_home_1f_entrance",
        "Player house 1F inside door",
        Position(MAP_REDS_HOUSE_1F, 2, 7),
        source="story_probe",
    ),
    "pallet_home_1f_exit": Landmark(
        "pallet_home_1f_exit",
        "Player house exterior after exiting",
        Position(MAP_PALLET_TOWN, 5, 6),
        source="story_probe",
    ),
    "pallet_home_front_door": Landmark(
        "pallet_home_front_door",
        "Player house exterior door",
        Position(MAP_PALLET_TOWN, 5, 6),
        source="golden_state",
    ),
    "pallet_grass_entrance": Landmark(
        "pallet_grass_entrance",
        "Pallet north grass entrance approach",
        Position(MAP_PALLET_TOWN, 10, 2),
        source="story_probe",
    ),
    "pallet_oak_trigger": Landmark(
        "pallet_oak_trigger",
        "Pallet north grass tile where Oak intercept begins",
        Position(MAP_PALLET_TOWN, 10, 1),
        source="story_probe_stale_text_state",
    ),
    "oaks_lab_entrance": Landmark(
        "oaks_lab_entrance",
        "Oak's Lab inside entrance",
        Position(MAP_OAKS_LAB, 5, 11),
        source="story_probe",
    ),
    "oaks_lab_exit": Landmark(
        "oaks_lab_exit",
        "Pallet Town outside Oak's Lab after exiting",
        Position(MAP_PALLET_TOWN, 12, 12),
        source="story_probe",
    ),
    "oaks_lab_starter_table": Landmark(
        "oaks_lab_starter_table",
        "Oak's Lab starter table",
        Position(MAP_OAKS_LAB, 5, 3),
        source="story_probe",
    ),
    "oaks_lab_rival_trigger": Landmark(
        "oaks_lab_rival_trigger",
        "Oak's Lab rival battle trigger",
        Position(MAP_OAKS_LAB, 5, 6),
        source="local_gemma_post_starter_probe",
    ),
    "rivals_home_entrance": Landmark(
        "rivals_home_entrance",
        "Rival's house inside entrance",
        Position(MAP_RIVALS_HOUSE, 2, 7),
        source="unverified_standard_map_seed",
    ),
    "rivals_home_exit": Landmark(
        "rivals_home_exit",
        "Rival's house exterior after exiting",
        Position(MAP_PALLET_TOWN, 13, 6),
        source="unverified_standard_map_seed",
    ),
    "rivals_home_town_map": Landmark(
        "rivals_home_town_map",
        "Rival's house Town Map area",
        Position(MAP_RIVALS_HOUSE, 2, 4),
        source="golden_state",
    ),
    "rivals_home_front_door": Landmark(
        "rivals_home_front_door",
        "Rival's house exterior door",
        Position(MAP_PALLET_TOWN, 13, 6),
        source="golden_state",
    ),
    "route_1_entrance": Landmark(
        "route_1_entrance",
        "Route 1 entrance from Pallet Town",
        Position(MAP_ROUTE_1, 10, 35),
        source="unverified_standard_map_seed",
    ),
    "route_1_south": Landmark(
        "route_1_south",
        "Route 1 south path",
        Position(MAP_ROUTE_1, 10, 31),
        source="golden_state",
    ),
    "route_1_north_exit": Landmark(
        "route_1_north_exit",
        "Route 1 north exit to Viridian City",
        Position(MAP_ROUTE_1, 11, 0),
        source="emulator_route_probe",
    ),
    "viridian_city_south_entrance": Landmark(
        "viridian_city_south_entrance",
        "Viridian City south entrance from Route 1",
        Position(MAP_VIRIDIAN_CITY, 21, 35),
        source="emulator_route_probe",
    ),
    "viridian_mart_front_door": Landmark(
        "viridian_mart_front_door",
        "Viridian Mart front door",
        Position(MAP_VIRIDIAN_CITY, 29, 20),
        source="golden_state",
    ),
    "viridian_mart_entrance": Landmark(
        "viridian_mart_entrance",
        "Viridian Mart inside entrance",
        Position(MAP_VIRIDIAN_MART, 3, 7),
        source="golden_state",
    ),
    "viridian_mart_exit": Landmark(
        "viridian_mart_exit",
        "Viridian City outside Viridian Mart after exiting",
        Position(MAP_VIRIDIAN_CITY, 29, 20),
        source="golden_state",
    ),
    "viridian_mart_counter": Landmark(
        "viridian_mart_counter",
        "Viridian Mart counter",
        Position(MAP_VIRIDIAN_MART, 2, 5),
        source="local_probe",
    ),
    "pallet_route_1_threshold": Landmark(
        "pallet_route_1_threshold",
        "Pallet north route threshold",
        Position(MAP_PALLET_TOWN, 10, 0),
        source="story_probe",
    ),
}

LANDMARK_ALIASES = {
    "bedroom": "pallet_bedroom_entrance",
    "bedroom_entrance": "pallet_bedroom_entrance",
    "bedroom_exit": "pallet_bedroom_exit",
    "home_1f": "pallet_home_1f_entrance",
    "home_1f_entrance": "pallet_home_1f_entrance",
    "home_1f_exit": "pallet_home_1f_exit",
    "home": "pallet_home_front_door",
    "player_home": "pallet_home_front_door",
    "grass": "pallet_grass_entrance",
    "oak_trigger": "pallet_grass_entrance",
    "trigger_oak": "pallet_oak_trigger",
    "oak_intercept": "pallet_oak_trigger",
    "pallet_grass": "pallet_grass_entrance",
    "lab": "oaks_lab_entrance",
    "oaks_lab": "oaks_lab_entrance",
    "oak_lab": "oaks_lab_entrance",
    "lab_entrance": "oaks_lab_entrance",
    "lab_exit": "oaks_lab_exit",
    "starter_table": "oaks_lab_starter_table",
    "rival_trigger": "oaks_lab_rival_trigger",
    "lab_rival_trigger": "oaks_lab_rival_trigger",
    "oak_lab_rival_trigger": "oaks_lab_rival_trigger",
    "rival_battle_trigger": "oaks_lab_rival_trigger",
    "rival_home": "rivals_home_entrance",
    "rivals_home": "rivals_home_entrance",
    "rival_house": "rivals_home_entrance",
    "rivals_house": "rivals_home_entrance",
    "rival_home_entrance": "rivals_home_entrance",
    "rival_home_exit": "rivals_home_exit",
    "town_map": "rivals_home_town_map",
    "route_1": "route_1_entrance",
    "route1": "route_1_entrance",
    "route_1_entrance": "route_1_entrance",
    "route_1_south": "route_1_south",
    "route_1_north": "route_1_north_exit",
    "route_1_north_exit": "route_1_north_exit",
    "viridian": "viridian_city_south_entrance",
    "viridian_city": "viridian_city_south_entrance",
    "viridian_city_south": "viridian_city_south_entrance",
    "viridian_city_south_entrance": "viridian_city_south_entrance",
    "viridian_mart": "viridian_mart_front_door",
    "viridian_mart_front_door": "viridian_mart_front_door",
    "mart": "viridian_mart_front_door",
    "mart_door": "viridian_mart_front_door",
    "viridian_mart_entrance": "viridian_mart_entrance",
    "viridian_mart_exit": "viridian_mart_exit",
    "mart_exit": "viridian_mart_exit",
    "viridian_mart_counter": "viridian_mart_counter",
    "mart_counter": "viridian_mart_counter",
}

TRANSITIONS = (
    PalletTransition(
        Position(MAP_PALLET_TOWN, 5, 6),
        "up",
        MAP_REDS_HOUSE_1F,
        Position(MAP_REDS_HOUSE_1F, 2, 7),
    ),
    PalletTransition(
        Position(MAP_REDS_HOUSE_1F, 2, 7),
        "down",
        MAP_PALLET_TOWN,
        Position(MAP_PALLET_TOWN, 5, 6),
    ),
    PalletTransition(
        Position(MAP_REDS_HOUSE_1F, 7, 1),
        "up",
        MAP_REDS_HOUSE_2F,
        Position(MAP_REDS_HOUSE_2F, 6, 1),
    ),
    PalletTransition(
        Position(MAP_REDS_HOUSE_2F, 6, 1),
        "right",
        MAP_REDS_HOUSE_1F,
        Position(MAP_REDS_HOUSE_1F, 7, 1),
    ),
    PalletTransition(
        Position(MAP_PALLET_TOWN, 13, 6),
        "up",
        MAP_RIVALS_HOUSE,
        Position(MAP_RIVALS_HOUSE, 2, 7),
    ),
    PalletTransition(
        Position(MAP_RIVALS_HOUSE, 2, 7),
        "down",
        MAP_PALLET_TOWN,
        Position(MAP_PALLET_TOWN, 13, 6),
    ),
    PalletTransition(
        Position(MAP_PALLET_TOWN, 12, 12),
        "up",
        MAP_OAKS_LAB,
        Position(MAP_OAKS_LAB, 5, 11),
    ),
    PalletTransition(
        Position(MAP_OAKS_LAB, 5, 11),
        "down",
        MAP_PALLET_TOWN,
        Position(MAP_PALLET_TOWN, 12, 12),
    ),
    PalletTransition(
        Position(MAP_PALLET_TOWN, 10, 0),
        "up",
        MAP_ROUTE_1,
        Position(MAP_ROUTE_1, 10, 35),
    ),
    PalletTransition(
        Position(MAP_ROUTE_1, 10, 35),
        "down",
        MAP_PALLET_TOWN,
        Position(MAP_PALLET_TOWN, 10, 0),
    ),
    PalletTransition(
        Position(MAP_ROUTE_1, 10, 0),
        "up",
        MAP_VIRIDIAN_CITY,
        Position(MAP_VIRIDIAN_CITY, 20, 35),
    ),
    PalletTransition(
        Position(MAP_ROUTE_1, 11, 0),
        "up",
        MAP_VIRIDIAN_CITY,
        Position(MAP_VIRIDIAN_CITY, 21, 35),
    ),
    PalletTransition(
        Position(MAP_VIRIDIAN_CITY, 20, 35),
        "down",
        MAP_ROUTE_1,
        Position(MAP_ROUTE_1, 10, 0),
    ),
    PalletTransition(
        Position(MAP_VIRIDIAN_CITY, 21, 35),
        "down",
        MAP_ROUTE_1,
        Position(MAP_ROUTE_1, 11, 0),
    ),
    PalletTransition(
        Position(MAP_VIRIDIAN_CITY, 29, 20),
        "up",
        MAP_VIRIDIAN_MART,
        Position(MAP_VIRIDIAN_MART, 3, 7),
    ),
    PalletTransition(
        Position(MAP_VIRIDIAN_MART, 3, 7),
        "down",
        MAP_VIRIDIAN_CITY,
        Position(MAP_VIRIDIAN_CITY, 29, 20),
    ),
)


def resolve_landmark(target: str | None) -> Landmark | None:
    if target is None:
        return LANDMARKS["pallet_grass_entrance"]
    normalized = normalize_target(target)
    canonical = LANDMARK_ALIASES.get(normalized, normalized)
    return LANDMARKS.get(canonical)


def snapshot_position(snapshot: Mapping[str, Any]) -> Position | None:
    position = snapshot.get("position")
    if not isinstance(position, Mapping):
        return None
    map_id = position.get("map_id")
    x = position.get("x")
    y = position.get("y")
    if not all(isinstance(value, int) for value in (map_id, x, y)):
        return None
    return Position(int(map_id), int(x), int(y))


def is_allowed_position(position: Position | None) -> bool:
    return position is not None and position.map_id in PALLET_MAP_IDS


def landmarks_for_current_map(snapshot: Mapping[str, Any]) -> list[Landmark]:
    position = snapshot_position(snapshot)
    if position is None:
        return []
    return [landmark for landmark in LANDMARKS.values() if landmark.position.map_id == position.map_id]


def target_options_for_current_map(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    options = []
    for landmark in landmarks_for_current_map(snapshot):
        options.append(
            {
                "id": landmark.id,
                "label": landmark.label,
                "position": landmark.position.format(),
                "source": landmark.source,
            }
        )
    return options


def at_pallet_landmark(position: Position | None, landmark: Landmark) -> bool:
    return at_landmark(position, landmark)


def default_navigation_target(snapshot: Mapping[str, Any]) -> str:
    position = snapshot_position(snapshot)
    party = snapshot.get("party") if isinstance(snapshot.get("party"), list) else []
    inventory = snapshot.get("inventory") if isinstance(snapshot.get("inventory"), list) else []
    if position is None:
        return "pallet_grass_entrance"
    if _has_oaks_parcel(inventory):
        if position.map_id == MAP_OAKS_LAB:
            return "oaks_lab_starter_table"
        return "oaks_lab_entrance"
    if position.map_id == MAP_OAKS_LAB:
        if not party:
            return "oaks_lab_starter_table"
        if at_pallet_landmark(position, LANDMARKS["oaks_lab_exit"]):
            return "route_1_entrance"
        return "oaks_lab_exit"
    if position.map_id == MAP_PALLET_TOWN:
        return "route_1_entrance" if party else "pallet_oak_trigger"
    if position.map_id == MAP_ROUTE_1:
        return "viridian_city_south_entrance"
    if position.map_id == MAP_VIRIDIAN_CITY:
        if at_pallet_landmark(position, LANDMARKS["viridian_mart_front_door"]):
            return "viridian_mart_entrance"
        return "viridian_mart_front_door"
    if position.map_id == MAP_VIRIDIAN_MART:
        return "viridian_mart_counter"
    return "pallet_grass_entrance"


def _has_oaks_parcel(inventory: list[Any]) -> bool:
    for item in inventory:
        if not isinstance(item, Mapping):
            continue
        if item.get("item_id") == 0x46:
            return True
        item_name = str(item.get("item_name") or item.get("name") or "")
        if "parcel" in item_name.lower():
            return True
    return False
