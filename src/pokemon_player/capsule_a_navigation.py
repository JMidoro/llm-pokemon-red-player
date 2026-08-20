from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class Position:
    map_id: int
    x: int
    y: int

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.map_id, self.x, self.y)

    def format(self) -> str:
        return f"map=0x{self.map_id:02X},x={self.x},y={self.y}"


@dataclass(frozen=True)
class Landmark:
    id: str
    label: str
    position: Position
    source: str = "promotion_evidence"


@dataclass(frozen=True)
class GrassPatch:
    id: str
    label: str
    map_id: int
    x_min: int
    x_max: int
    y_min: int
    y_max: int
    near_distance: int = 2

    def contains(self, position: Position | None) -> bool:
        if position is None or position.map_id != self.map_id:
            return False
        return self.x_min <= position.x <= self.x_max and self.y_min <= position.y <= self.y_max

    def is_near(self, position: Position | None) -> bool:
        if position is None or position.map_id != self.map_id:
            return False
        clamped_x = min(max(position.x, self.x_min), self.x_max)
        clamped_y = min(max(position.y, self.y_min), self.y_max)
        return abs(position.x - clamped_x) + abs(position.y - clamped_y) <= self.near_distance

    def nearest_position(self, position: Position) -> Position:
        return Position(
            self.map_id,
            min(max(position.x, self.x_min), self.x_max),
            min(max(position.y, self.y_min), self.y_max),
        )

    def format_bounds(self) -> str:
        return (
            f"map=0x{self.map_id:02X},"
            f"x={self.x_min}..{self.x_max},"
            f"y={self.y_min}..{self.y_max}"
        )


MAP_VIRIDIAN_CITY = 0x01
MAP_ROUTE_2 = 0x0D
MAP_ROUTE_22 = 0x21
MAP_VIRIDIAN_POKECENTER = 0x29
MAP_VIRIDIAN_MART = 0x2A
MAP_VIRIDIAN_FOREST_NORTH_GATE = 0x2F
MAP_VIRIDIAN_FOREST_SOUTH_GATE = 0x32
MAP_VIRIDIAN_FOREST = 0x33

ALLOWED_MAP_IDS = frozenset(
    {
        MAP_VIRIDIAN_CITY,
        MAP_ROUTE_2,
        MAP_ROUTE_22,
        MAP_VIRIDIAN_POKECENTER,
        MAP_VIRIDIAN_MART,
        MAP_VIRIDIAN_FOREST_NORTH_GATE,
        MAP_VIRIDIAN_FOREST_SOUTH_GATE,
        MAP_VIRIDIAN_FOREST,
    }
)

BOUNDARY_MAP_IDS = frozenset(
    {
        0x02,  # Pewter City
    }
)

LANDMARKS: dict[str, Landmark] = {
    "viridian_city_ready_point": Landmark(
        "viridian_city_ready_point",
        "Viridian City ready point",
        Position(MAP_VIRIDIAN_CITY, 19, 27),
    ),
    "viridian_city_north_corridor": Landmark(
        "viridian_city_north_corridor",
        "Viridian City north corridor",
        Position(MAP_VIRIDIAN_CITY, 18, 11),
    ),
    "viridian_city_north_exit": Landmark(
        "viridian_city_north_exit",
        "Viridian City north exit",
        Position(MAP_VIRIDIAN_CITY, 18, 0),
        source="derived_route_point",
    ),
    "viridian_pokecenter_door": Landmark(
        "viridian_pokecenter_door",
        "Viridian PokeCenter door",
        Position(MAP_VIRIDIAN_CITY, 23, 26),
        source="director_probe",
    ),
    "viridian_pokecenter_inside": Landmark(
        "viridian_pokecenter_inside",
        "Viridian PokeCenter interior",
        Position(MAP_VIRIDIAN_POKECENTER, 3, 7),
        source="golden_state",
    ),
    "route_22_grass": Landmark(
        "route_22_grass",
        "Route 22 approved grass patch",
        Position(MAP_ROUTE_22, 33, 11),
        source="promotion_evidence",
    ),
    "route_2_south_entry": Landmark(
        "route_2_south_entry",
        "Route 2 south entry from Viridian City",
        Position(MAP_ROUTE_2, 8, 71),
        source="derived_route_point",
    ),
    "route_2_south_gate_threshold": Landmark(
        "route_2_south_gate_threshold",
        "Route 2 south forest gate threshold",
        Position(MAP_ROUTE_2, 3, 44),
    ),
    "route_2_north": Landmark(
        "route_2_north",
        "Route 2 north forest gate threshold",
        Position(MAP_ROUTE_2, 3, 11),
    ),
    "viridian_forest_south_gate_from_south": Landmark(
        "viridian_forest_south_gate_from_south",
        "Viridian Forest south gate, south side",
        Position(MAP_VIRIDIAN_FOREST_SOUTH_GATE, 4, 7),
    ),
    "viridian_forest_south_gate_from_north": Landmark(
        "viridian_forest_south_gate_from_north",
        "Viridian Forest south gate, north side",
        Position(MAP_VIRIDIAN_FOREST_SOUTH_GATE, 5, 1),
    ),
    "viridian_forest_south_entrance": Landmark(
        "viridian_forest_south_entrance",
        "Viridian Forest south entrance",
        Position(MAP_VIRIDIAN_FOREST, 17, 47),
        source="derived_route_point",
    ),
    "viridian_forest_grass_1": Landmark(
        "viridian_forest_grass_1",
        "Viridian Forest south grass patch",
        Position(MAP_VIRIDIAN_FOREST, 28, 43),
    ),
    "viridian_forest_grass_2": Landmark(
        "viridian_forest_grass_2",
        "Viridian Forest interior grass patch",
        Position(MAP_VIRIDIAN_FOREST, 25, 25),
    ),
    "viridian_forest_mid_north_corridor": Landmark(
        "viridian_forest_mid_north_corridor",
        "Viridian Forest mid-north corridor",
        Position(MAP_VIRIDIAN_FOREST, 17, 9),
        source="director_manual_waypoint",
    ),
    "viridian_forest_north_exit": Landmark(
        "viridian_forest_north_exit",
        "Viridian Forest north exit",
        Position(MAP_VIRIDIAN_FOREST, 1, 0),
    ),
    "viridian_forest_north_gate_from_south": Landmark(
        "viridian_forest_north_gate_from_south",
        "Viridian Forest north gate, south side",
        Position(MAP_VIRIDIAN_FOREST_NORTH_GATE, 4, 7),
    ),
    "viridian_forest_north_gate_from_north": Landmark(
        "viridian_forest_north_gate_from_north",
        "Viridian Forest north gate, north side",
        Position(MAP_VIRIDIAN_FOREST_NORTH_GATE, 5, 1),
    ),
}

LANDMARK_ALIASES = {
    "forest_grass": "viridian_forest_grass_1",
    "grass": "viridian_forest_grass_1",
    "south_grass": "viridian_forest_grass_1",
    "viridian_forest_grass": "viridian_forest_grass_1",
    "interior_grass": "viridian_forest_grass_2",
    "grass_2": "viridian_forest_grass_2",
    "mid_north": "viridian_forest_mid_north_corridor",
    "north_corridor": "viridian_forest_mid_north_corridor",
    "forest_mid_north": "viridian_forest_mid_north_corridor",
    "forest_entrance": "viridian_forest_south_entrance",
    "viridian_forest_entrance": "viridian_forest_south_entrance",
    "south_gate": "viridian_forest_south_gate_from_south",
    "north_gate": "viridian_forest_north_gate_from_south",
    "north_gate_south": "viridian_forest_north_gate_from_south",
    "north_gate_north": "viridian_forest_north_gate_from_north",
    "forest_north_exit": "viridian_forest_north_exit",
    "route_2": "route_2_south_gate_threshold",
    "route2": "route_2_south_gate_threshold",
    "route_2_north": "route_2_north",
    "viridian_city": "viridian_city_ready_point",
    "ready_point": "viridian_city_ready_point",
    "resupply": "viridian_city_ready_point",
    "viridian_pokecenter": "viridian_pokecenter_inside",
    "pokecenter": "viridian_pokecenter_inside",
    "pokemon_center": "viridian_pokecenter_inside",
    "heal": "viridian_pokecenter_inside",
    "route_22_grass": "route_22_grass",
    "route22_grass": "route_22_grass",
    "route_22": "route_22_grass",
    "route22": "route_22_grass",
}

APPROVED_GRASS_PATCHES: dict[str, GrassPatch] = {
    "viridian_forest_south_grass": GrassPatch(
        "viridian_forest_south_grass",
        "Viridian Forest south grass patch",
        MAP_VIRIDIAN_FOREST,
        x_min=28,
        x_max=32,
        y_min=41,
        y_max=43,
    ),
    "route_22_grass": GrassPatch(
        "route_22_grass",
        "Route 22 approved grass patch",
        MAP_ROUTE_22,
        x_min=31,
        x_max=34,
        y_min=9,
        y_max=12,
    ),
    "pewter_route2_grass": GrassPatch(
        "pewter_route2_grass",
        "Route 2 Pewter-side grass patch",
        MAP_ROUTE_2,
        x_min=6,
        x_max=8,
        y_min=6,
        y_max=8,
    )
}

GRASS_PATCH_ALIASES = {
    "forest_grass": "viridian_forest_south_grass",
    "grass": "viridian_forest_south_grass",
    "south_grass": "viridian_forest_south_grass",
    "viridian_forest_grass": "viridian_forest_south_grass",
    "viridian_forest_south_grass": "viridian_forest_south_grass",
    "current_map": "current_map",
    "current": "current_map",
    "auto": "current_map",
    "route_22_grass": "route_22_grass",
    "route22_grass": "route_22_grass",
    "route_22": "route_22_grass",
    "route22": "route_22_grass",
    "pewter_route2_grass": "pewter_route2_grass",
    "pewter_grass": "pewter_route2_grass",
    "route_2_grass": "pewter_route2_grass",
    "route2_grass": "pewter_route2_grass",
}


def resolve_landmark(target: str | None) -> Landmark | None:
    if target is None:
        return LANDMARKS["viridian_forest_grass_1"]
    normalized = normalize_target(target)
    canonical = LANDMARK_ALIASES.get(normalized, normalized)
    return LANDMARKS.get(canonical)


def resolve_grass_patch(target: str | None) -> GrassPatch | None:
    if target is None:
        return APPROVED_GRASS_PATCHES["viridian_forest_south_grass"]
    normalized = normalize_target(target)
    canonical = GRASS_PATCH_ALIASES.get(normalized, normalized)
    if canonical == "current_map":
        return None
    return APPROVED_GRASS_PATCHES.get(canonical)


def approved_grass_patch_for_map(map_id: int | None) -> GrassPatch | None:
    if map_id is None:
        return None
    for patch in APPROVED_GRASS_PATCHES.values():
        if patch.map_id == map_id:
            return patch
    return None


def normalize_target(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", "_").split())


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
    return position is not None and position.map_id in ALLOWED_MAP_IDS


def is_boundary_position(position: Position | None) -> bool:
    return position is not None and position.map_id in BOUNDARY_MAP_IDS


def at_landmark(position: Position | None, landmark: Landmark) -> bool:
    return position == landmark.position


def approved_grass_patch_for_position(position: Position | None) -> GrassPatch | None:
    for patch in APPROVED_GRASS_PATCHES.values():
        if patch.contains(position) or patch.is_near(position):
            return patch
    return None
