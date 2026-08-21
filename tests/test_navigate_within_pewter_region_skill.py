from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.pewter_navigation import (
    MAP_PEWTER_CITY,
    MAP_PEWTER_GYM,
    MAP_ROUTE_2,
    Position,
    resolve_landmark,
)
from pokemon_player.skills.navigate_within_pewter_region import navigate_within_pewter_region


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "research" / "golden-states"


def load_record(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.expected.json").read_text(encoding="utf-8"))


def test_pewter_navigation_allows_route_2_north_strip() -> None:
    record = load_record("pewter_city_viridian_forest_exit")

    result = navigate_within_pewter_region(
        record["snapshot"],
        target="pewter_city_center",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert any("map=0x0D" in item for item in result.evidence)


def test_pewter_navigation_allows_city_to_brock_target() -> None:
    record = load_record("pewter_city_overworld")

    result = navigate_within_pewter_region(
        record["snapshot"],
        target="brock",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "target_id=pewter_gym_brock_pre_battle" in result.evidence


def test_pewter_navigation_recognizes_brock_landmark() -> None:
    record = load_record("pewter_gym_brock_pre_battle")

    result = navigate_within_pewter_region(
        record["snapshot"],
        target="pewter_gym_brock_pre_battle",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "blocked"
    assert "choose the next semantic action" in result.summary


def test_pewter_navigation_accepts_forced_dialogue_waypoint_after_run() -> None:
    before = load_record("pewter_city_overworld")
    after = load_record("pewter_gym_trainer_pre_battle")
    after_snapshot = dict(after["snapshot"])
    after_snapshot["mode"] = "dialogue"

    result = navigate_within_pewter_region(
        after_snapshot,
        target="pewter_gym_brock_pre_battle",
        before_snapshot=before["snapshot"],
        screenshot_path=after["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "dialogue_waypoint=true" in result.evidence


def test_pewter_navigation_blocks_unrelated_region() -> None:
    record = load_record("pallet_overworld_started")

    result = navigate_within_pewter_region(record["snapshot"], target="pewter_city_center")

    assert result.status == "blocked"
    assert "outside the Pewter navigation region" in result.summary


def test_pewter_landmark_aliases_resolve_to_captured_coordinates() -> None:
    assert resolve_landmark("route_2_grass").position == Position(MAP_ROUTE_2, 7, 7)
    assert resolve_landmark("pewter").position == Position(MAP_PEWTER_CITY, 20, 26)
    assert resolve_landmark("brock").position == Position(MAP_PEWTER_GYM, 5, 1)
