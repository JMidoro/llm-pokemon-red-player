from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pokemon_player.capsule_a_navigation import Landmark, Position, at_landmark, normalize_target


MAP_PEWTER_CITY = 0x02
MAP_ROUTE_2 = 0x0D
MAP_VIRIDIAN_FOREST_NORTH_GATE = 0x2F
MAP_PEWTER_GYM = 0x36
MAP_PEWTER_MART = 0x38
MAP_PEWTER_POKECENTER = 0x3A

PEWTER_MAP_IDS = frozenset(
    {
        MAP_PEWTER_CITY,
        MAP_ROUTE_2,
        MAP_VIRIDIAN_FOREST_NORTH_GATE,
        MAP_PEWTER_GYM,
        MAP_PEWTER_MART,
        MAP_PEWTER_POKECENTER,
    }
)


@dataclass(frozen=True)
class PewterTransition:
    source: Position
    button: str
    destination_map: int
    destination_hint: Position


LANDMARKS: dict[str, Landmark] = {
    "viridian_forest_north_gate_exit": Landmark(
        "viridian_forest_north_gate_exit",
        "Viridian Forest north gate exit",
        Position(MAP_VIRIDIAN_FOREST_NORTH_GATE, 5, 1),
        source="golden_state",
    ),
    "pewter_city_viridian_forest_exit": Landmark(
        "pewter_city_viridian_forest_exit",
        "Route 2 north of Viridian Forest",
        Position(MAP_ROUTE_2, 3, 11),
        source="golden_state",
    ),
    "pewter_route2_grass": Landmark(
        "pewter_route2_grass",
        "Route 2 Pewter-side grass",
        Position(MAP_ROUTE_2, 7, 7),
        source="golden_state",
    ),
    "pewter_city_south_entrance": Landmark(
        "pewter_city_south_entrance",
        "Pewter City south entrance from Route 2",
        Position(MAP_PEWTER_CITY, 18, 35),
        source="emulator_transition_probe",
    ),
    "pewter_city_center": Landmark(
        "pewter_city_center",
        "Pewter City center",
        Position(MAP_PEWTER_CITY, 20, 26),
        source="golden_state",
    ),
    "pewter_pokecenter_entrance": Landmark(
        "pewter_pokecenter_entrance",
        "Pewter PokeCenter exterior door",
        Position(MAP_PEWTER_CITY, 13, 26),
        source="golden_state",
    ),
    "pewter_pokecenter_inside": Landmark(
        "pewter_pokecenter_inside",
        "Pewter PokeCenter interior entrance",
        Position(MAP_PEWTER_POKECENTER, 3, 7),
        source="emulator_transition_probe",
    ),
    "pewter_pokecenter_counter": Landmark(
        "pewter_pokecenter_counter",
        "Pewter PokeCenter counter",
        Position(MAP_PEWTER_POKECENTER, 3, 3),
        source="golden_state",
    ),
    "pewter_mart_entrance": Landmark(
        "pewter_mart_entrance",
        "Pewter Mart exterior door",
        Position(MAP_PEWTER_CITY, 23, 18),
        source="golden_state",
    ),
    "pewter_mart_inside": Landmark(
        "pewter_mart_inside",
        "Pewter Mart interior entrance",
        Position(MAP_PEWTER_MART, 3, 7),
        source="emulator_transition_probe",
    ),
    "pewter_mart_counter": Landmark(
        "pewter_mart_counter",
        "Pewter Mart counter",
        Position(MAP_PEWTER_MART, 2, 5),
        source="golden_state",
    ),
    "pewter_gym_entrance": Landmark(
        "pewter_gym_entrance",
        "Pewter Gym exterior door",
        Position(MAP_PEWTER_CITY, 16, 18),
        source="golden_state",
    ),
    "pewter_gym_inside": Landmark(
        "pewter_gym_inside",
        "Pewter Gym interior entrance",
        Position(MAP_PEWTER_GYM, 4, 13),
        source="golden_state",
    ),
    "pewter_gym_trainer_pre_battle": Landmark(
        "pewter_gym_trainer_pre_battle",
        "Pewter Gym trainer approach",
        Position(MAP_PEWTER_GYM, 4, 7),
        source="golden_state",
    ),
    "pewter_gym_brock_pre_battle": Landmark(
        "pewter_gym_brock_pre_battle",
        "Brock pre-battle position",
        Position(MAP_PEWTER_GYM, 5, 1),
        source="golden_state",
    ),
    "pewter_city_route3_exit": Landmark(
        "pewter_city_route3_exit",
        "Pewter City Route 3 exit",
        Position(MAP_PEWTER_CITY, 34, 18),
        source="golden_state",
    ),
    "pewter_museum_entrance": Landmark(
        "pewter_museum_entrance",
        "Pewter Museum exterior door",
        Position(MAP_PEWTER_CITY, 14, 8),
        source="golden_state",
    ),
    "pewter_museum_bush": Landmark(
        "pewter_museum_bush",
        "Pewter Museum side-quest Cut bush",
        Position(MAP_PEWTER_CITY, 27, 4),
        source="golden_state",
    ),
    "pewter_cut_bush": Landmark(
        "pewter_cut_bush",
        "Route 2 Cut bush near Pewter",
        Position(MAP_ROUTE_2, 5, 9),
        source="golden_state",
    ),
}

LANDMARK_ALIASES = {
    "forest_north_gate": "viridian_forest_north_gate_exit",
    "north_gate_exit": "viridian_forest_north_gate_exit",
    "route_2_forest_exit": "pewter_city_viridian_forest_exit",
    "route2_forest_exit": "pewter_city_viridian_forest_exit",
    "route_2": "pewter_city_viridian_forest_exit",
    "route2": "pewter_city_viridian_forest_exit",
    "route_2_grass": "pewter_route2_grass",
    "route2_grass": "pewter_route2_grass",
    "pewter_grass": "pewter_route2_grass",
    "pewter": "pewter_city_center",
    "pewter_city": "pewter_city_center",
    "city": "pewter_city_center",
    "pewter_south": "pewter_city_south_entrance",
    "pokecenter": "pewter_pokecenter_inside",
    "poke_center": "pewter_pokecenter_inside",
    "pokemon_center": "pewter_pokecenter_inside",
    "pewter_pokecenter": "pewter_pokecenter_inside",
    "heal": "pewter_pokecenter_counter",
    "pokecenter_counter": "pewter_pokecenter_counter",
    "mart": "pewter_mart_inside",
    "pewter_mart": "pewter_mart_inside",
    "mart_counter": "pewter_mart_counter",
    "gym": "pewter_gym_inside",
    "pewter_gym": "pewter_gym_inside",
    "gym_trainer": "pewter_gym_trainer_pre_battle",
    "trainer": "pewter_gym_trainer_pre_battle",
    "brock": "pewter_gym_brock_pre_battle",
    "brock_pre_battle": "pewter_gym_brock_pre_battle",
    "route_3": "pewter_city_route3_exit",
    "route3": "pewter_city_route3_exit",
    "route_3_exit": "pewter_city_route3_exit",
    "museum": "pewter_museum_entrance",
    "museum_bush": "pewter_museum_bush",
    "cut_bush": "pewter_cut_bush",
}

TRANSITIONS = (
    PewterTransition(
        Position(MAP_VIRIDIAN_FOREST_NORTH_GATE, 5, 1),
        "up",
        MAP_ROUTE_2,
        Position(MAP_ROUTE_2, 3, 11),
    ),
    PewterTransition(
        Position(MAP_ROUTE_2, 3, 11),
        "down",
        MAP_VIRIDIAN_FOREST_NORTH_GATE,
        Position(MAP_VIRIDIAN_FOREST_NORTH_GATE, 5, 1),
    ),
    PewterTransition(
        Position(MAP_ROUTE_2, 8, 0),
        "up",
        MAP_PEWTER_CITY,
        Position(MAP_PEWTER_CITY, 18, 35),
    ),
    PewterTransition(
        Position(MAP_PEWTER_CITY, 18, 35),
        "down",
        MAP_ROUTE_2,
        Position(MAP_ROUTE_2, 8, 0),
    ),
    PewterTransition(
        Position(MAP_PEWTER_CITY, 13, 26),
        "up",
        MAP_PEWTER_POKECENTER,
        Position(MAP_PEWTER_POKECENTER, 3, 7),
    ),
    PewterTransition(
        Position(MAP_PEWTER_POKECENTER, 3, 7),
        "down",
        MAP_PEWTER_CITY,
        Position(MAP_PEWTER_CITY, 13, 26),
    ),
    PewterTransition(
        Position(MAP_PEWTER_CITY, 23, 18),
        "up",
        MAP_PEWTER_MART,
        Position(MAP_PEWTER_MART, 3, 7),
    ),
    PewterTransition(
        Position(MAP_PEWTER_MART, 3, 7),
        "down",
        MAP_PEWTER_CITY,
        Position(MAP_PEWTER_CITY, 23, 18),
    ),
    PewterTransition(
        Position(MAP_PEWTER_CITY, 16, 18),
        "up",
        MAP_PEWTER_GYM,
        Position(MAP_PEWTER_GYM, 4, 13),
    ),
    PewterTransition(
        Position(MAP_PEWTER_GYM, 4, 13),
        "down",
        MAP_PEWTER_CITY,
        Position(MAP_PEWTER_CITY, 16, 18),
    ),
)


def resolve_landmark(target: str | None) -> Landmark | None:
    if target is None:
        return LANDMARKS["pewter_gym_brock_pre_battle"]
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
    return position is not None and position.map_id in PEWTER_MAP_IDS


def landmarks_for_current_map(snapshot: Mapping[str, Any]) -> list[Landmark]:
    position = snapshot_position(snapshot)
    if position is None:
        return []
    return [landmark for landmark in LANDMARKS.values() if landmark.position.map_id == position.map_id]


def target_options_for_current_map(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": landmark.id,
            "label": landmark.label,
            "position": landmark.position.format(),
            "source": landmark.source,
        }
        for landmark in landmarks_for_current_map(snapshot)
    ]


def at_pewter_landmark(position: Position | None, landmark: Landmark) -> bool:
    return at_landmark(position, landmark)


def default_navigation_target(snapshot: Mapping[str, Any]) -> str:
    position = snapshot_position(snapshot)
    if position is None:
        return "pewter_gym_brock_pre_battle"
    if position.map_id in {MAP_VIRIDIAN_FOREST_NORTH_GATE, MAP_ROUTE_2}:
        return "pewter_city_center"
    if position.map_id == MAP_PEWTER_CITY:
        return "pewter_gym_brock_pre_battle"
    if position.map_id == MAP_PEWTER_GYM:
        return "pewter_gym_brock_pre_battle"
    if position.map_id == MAP_PEWTER_POKECENTER:
        return "pewter_pokecenter_counter"
    if position.map_id == MAP_PEWTER_MART:
        return "pewter_mart_counter"
    return "pewter_gym_brock_pre_battle"
