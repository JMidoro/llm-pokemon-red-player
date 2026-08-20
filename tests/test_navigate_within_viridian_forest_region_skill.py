from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from pokemon_player import skill_execution
from pokemon_player.capsule_a_navigation import (
    MAP_ROUTE_2,
    MAP_ROUTE_22,
    MAP_VIRIDIAN_CITY,
    MAP_VIRIDIAN_FOREST,
    MAP_VIRIDIAN_POKECENTER,
    Position,
    resolve_landmark,
)
from pokemon_player.skill_execution import (
    next_navigation_segment,
    next_same_map_navigation_waypoint,
)
from pokemon_player.skills.navigate_within_viridian_forest_region import (
    STALE_TEXT_MENU_OVERWORLD_WARNING,
    navigate_within_viridian_forest_region,
    trainer_alert_pending_dialogue,
)


ROOT = Path(__file__).resolve().parents[1]
PROMOTION_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "capsule_a_region_and_landmarks"


def load_record(name: str) -> dict:
    return json.loads((PROMOTION_EVIDENCE / f"{name}.promotion-evidence.json").read_text(encoding="utf-8"))


def test_navigation_allows_capsule_a_start_region() -> None:
    record = load_record("step_01_viridian_city_ready_point")

    result = navigate_within_viridian_forest_region(
        record["snapshot"],
        target="forest_grass",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "Navigation can start" in result.summary


def test_navigation_succeeds_when_already_at_target() -> None:
    record = load_record("step_01_viridian_forest_grass_1")

    result = navigate_within_viridian_forest_region(
        record["snapshot"],
        target="forest_grass",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "south grass patch" in result.summary


def test_navigation_blocks_outside_capsule_a_region() -> None:
    record = load_record("step_01_route_22_grass")

    result = navigate_within_viridian_forest_region(
        record["snapshot"],
        target="route_22_grass",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "Route 22 approved grass patch" in result.summary


def test_navigation_after_run_fails_if_target_not_reached() -> None:
    before = load_record("step_01_viridian_city_ready_point")
    after = load_record("step_01_route_2_corridor")

    result = navigate_within_viridian_forest_region(
        after["snapshot"],
        before_snapshot=before["snapshot"],
        target="forest_grass",
        screenshot_path=after["screenshot_file"],
    )

    assert result.status == "failed"
    assert "before reaching" in result.summary


def test_navigation_after_run_succeeds_when_trainer_battle_starts() -> None:
    before = load_record("step_01_viridian_forest_grass_1")
    after = deepcopy(before["snapshot"])
    after["mode"] = "battle"
    after["battle_type_raw"] = 2

    result = navigate_within_viridian_forest_region(
        after,
        before_snapshot=before["snapshot"],
        target="north_gate",
        screenshot_path=before["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "trainer battle route waypoint" in result.summary
    assert "trainer_battle_waypoint=true" in result.evidence


def test_navigation_after_run_succeeds_when_forced_trainer_dialogue_starts() -> None:
    before = load_record("step_01_viridian_forest_grass_1")
    after = deepcopy(before["snapshot"])
    after["mode"] = "dialogue"
    after["battle_type_raw"] = 0

    result = navigate_within_viridian_forest_region(
        after,
        before_snapshot=before["snapshot"],
        target="north_gate",
        screenshot_path=before["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "forced trainer engagement dialogue waypoint" in result.summary
    assert "trainer_engagement_waypoint=true" in result.evidence


def test_navigation_after_run_does_not_accept_stale_warning_as_trainer_alert() -> None:
    before = load_record("step_01_viridian_forest_grass_1")
    after = deepcopy(before["snapshot"])
    after["mode"] = "overworld"
    after["battle_type_raw"] = 0
    after["warnings"] = [STALE_TEXT_MENU_OVERWORLD_WARNING]

    result = navigate_within_viridian_forest_region(
        after,
        before_snapshot=before["snapshot"],
        target="north_gate",
        screenshot_path=before["screenshot_file"],
    )

    assert result.status == "failed"
    assert "trainer alert waypoint" not in result.summary
    assert "trainer_alert_waypoint=true" not in result.evidence


def test_same_map_planner_accepts_trainer_battle_as_terminal_route(monkeypatch) -> None:
    start = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 17, "y": 47},
    }
    trainer_battle = {
        "mode": "battle",
        "battle_type_raw": 2,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 18, "y": 47},
    }

    class FakePyBoy:
        current = start

    fake_pyboy = FakePyBoy()

    monkeypatch.setattr(skill_execution, "snapshot", lambda pyboy: pyboy.current)
    monkeypatch.setattr(skill_execution, "snapshot_to_dict", lambda value: value)
    monkeypatch.setattr(skill_execution, "pyboy_state_bytes", lambda pyboy: b"state")
    monkeypatch.setattr(skill_execution, "load_pyboy_state_bytes", lambda pyboy, state: None)
    monkeypatch.setattr(
        skill_execution,
        "wait_for_navigation_trainer_engagement",
        lambda pyboy, *, render, max_frames: None,
    )

    def fake_run_navigation_button(pyboy, button: str, *, render: bool) -> dict:
        assert button == "right"
        pyboy.current = trainer_battle
        return trainer_battle

    monkeypatch.setattr(skill_execution, "run_navigation_button", fake_run_navigation_button)

    result = skill_execution.find_same_map_navigation_path(
        fake_pyboy,
        target=Position(MAP_VIRIDIAN_FOREST, 19, 47),
        max_expansions=10,
        max_steps=10,
        render=False,
    )

    assert result["status"] == "planned_trainer_battle"
    assert result["buttons"] == ["right"]
    assert result["position"] == "map=0x33,x=18,y=47"


def test_same_map_planner_accepts_wild_battle_as_terminal_route(monkeypatch) -> None:
    start = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 17, "y": 47},
    }
    wild_battle = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 18, "y": 47},
    }
    target_reached = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 19, "y": 47},
    }

    class FakePyBoy:
        current = start

    fake_pyboy = FakePyBoy()

    monkeypatch.setattr(skill_execution, "snapshot", lambda pyboy: pyboy.current)
    monkeypatch.setattr(skill_execution, "snapshot_to_dict", lambda value: value)
    monkeypatch.setattr(skill_execution, "pyboy_state_bytes", lambda pyboy: b"state")
    monkeypatch.setattr(skill_execution, "load_pyboy_state_bytes", lambda pyboy, state: None)
    monkeypatch.setattr(
        skill_execution,
        "wait_for_navigation_trainer_engagement",
        lambda pyboy, *, render, max_frames: None,
    )

    def fake_run_navigation_button(pyboy, button: str, *, render: bool) -> dict:
        if button == "right":
            pyboy.current = wild_battle
            return wild_battle
        pyboy.current = target_reached
        return target_reached

    monkeypatch.setattr(skill_execution, "run_navigation_button", fake_run_navigation_button)

    result = skill_execution.find_same_map_navigation_path(
        fake_pyboy,
        target=Position(MAP_VIRIDIAN_FOREST, 19, 47),
        max_expansions=10,
        max_steps=10,
        render=False,
    )

    assert result["status"] == "planned_wild_battle"
    assert result["buttons"] == ["right"]
    assert result["position"] == "map=0x33,x=18,y=47"


def test_pallet_same_map_planner_does_not_prefer_wild_battle_over_landmark(monkeypatch) -> None:
    start = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x0C, "x": 10, "y": 35},
    }
    wild_battle = {
        "mode": "battle",
        "battle_type_raw": 1,
        "position": {"map_id": 0x0C, "x": 10, "y": 34},
    }
    target_reached = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x0C, "x": 10, "y": 33},
    }

    class FakePyBoy:
        current = start

    fake_pyboy = FakePyBoy()

    monkeypatch.setattr(skill_execution, "snapshot", lambda pyboy: pyboy.current)
    monkeypatch.setattr(skill_execution, "snapshot_to_dict", lambda value: value)
    monkeypatch.setattr(skill_execution, "pyboy_state_bytes", lambda pyboy: b"state")
    monkeypatch.setattr(skill_execution, "load_pyboy_state_bytes", lambda pyboy, state: None)

    def fake_run_navigation_button(pyboy, button: str, *, render: bool) -> dict:
        if button == "up":
            pyboy.current = wild_battle
            return wild_battle
        pyboy.current = target_reached
        return target_reached

    monkeypatch.setattr(skill_execution, "run_navigation_button", fake_run_navigation_button)

    result = skill_execution.find_pallet_same_map_navigation_path(
        fake_pyboy,
        target=Position(0x0C, 10, 33),
        max_expansions=10,
        max_steps=10,
        render=False,
    )

    assert result["status"] == "planned"
    assert result["buttons"] != ["up"]


def test_best_wild_battle_candidate_filters_to_target_map_for_capsule_navigation() -> None:
    candidate = skill_execution.best_wild_battle_candidate(
        [
            {
                "buttons": ["up"],
                "position": "map=0x0D,x=8,y=60",
                "map_id": MAP_ROUTE_2,
                "distance_to_target": 1,
            },
            {
                "buttons": ["left", "left", "up"],
                "position": "map=0x21,x=34,y=12",
                "map_id": MAP_ROUTE_22,
                "distance_to_target": 4,
            },
        ],
        target=Position(MAP_ROUTE_22, 33, 11),
    )

    assert candidate is not None
    assert candidate["map_id"] == MAP_ROUTE_22
    assert candidate["buttons"] == ["left", "left", "up"]


def test_same_map_planner_waits_for_pending_trainer_engagement(monkeypatch) -> None:
    start = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 17, "y": 47},
    }

    class FakePyBoy:
        current = start

    fake_pyboy = FakePyBoy()

    monkeypatch.setattr(skill_execution, "snapshot", lambda pyboy: pyboy.current)
    monkeypatch.setattr(skill_execution, "snapshot_to_dict", lambda value: value)
    monkeypatch.setattr(skill_execution, "pyboy_state_bytes", lambda pyboy: b"state")
    monkeypatch.setattr(skill_execution, "load_pyboy_state_bytes", lambda pyboy, state: None)
    monkeypatch.setattr(skill_execution, "run_navigation_button", lambda pyboy, button, *, render: start)
    monkeypatch.setattr(
        skill_execution,
        "wait_for_navigation_trainer_engagement",
        lambda pyboy, *, render, max_frames: {
            "plan_status": "planned_trainer_engagement",
            "reason": "trainer_engagement_dialogue",
            "summary": "Planned navigation to a forced trainer engagement dialogue waypoint.",
            "wait_frames": 96,
            "position": "map=0x33,x=17,y=47",
            "battle_type_raw": 0,
        },
    )

    result = skill_execution.find_same_map_navigation_path(
        fake_pyboy,
        target=Position(MAP_VIRIDIAN_FOREST, 19, 47),
        max_expansions=10,
        max_steps=10,
        render=False,
    )

    assert result["status"] == "planned_trainer_engagement"
    assert result["buttons"] == []
    assert result["wait_frames"] == 96


def test_same_map_planner_waits_after_successful_step_before_enqueuing(monkeypatch) -> None:
    start = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 17, "y": 47},
    }
    moved = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 18, "y": 47},
    }

    class FakePyBoy:
        current = start

    fake_pyboy = FakePyBoy()

    monkeypatch.setattr(skill_execution, "snapshot", lambda pyboy: pyboy.current)
    monkeypatch.setattr(skill_execution, "snapshot_to_dict", lambda value: value)
    monkeypatch.setattr(skill_execution, "pyboy_state_bytes", lambda pyboy: b"state")
    monkeypatch.setattr(skill_execution, "load_pyboy_state_bytes", lambda pyboy, state: None)

    def fake_run_navigation_button(pyboy, button: str, *, render: bool) -> dict:
        assert button == "right"
        pyboy.current = moved
        return moved

    monkeypatch.setattr(skill_execution, "run_navigation_button", fake_run_navigation_button)
    monkeypatch.setattr(
        skill_execution,
        "wait_for_navigation_trainer_engagement",
        lambda pyboy, *, render, max_frames: {
            "plan_status": "planned_trainer_engagement",
            "reason": "trainer_engagement_dialogue",
            "summary": "Planned navigation to a forced trainer engagement dialogue waypoint.",
            "wait_frames": 48,
            "position": "map=0x33,x=18,y=47",
            "battle_type_raw": 0,
        },
    )

    result = skill_execution.find_same_map_navigation_path(
        fake_pyboy,
        target=Position(MAP_VIRIDIAN_FOREST, 19, 47),
        max_expansions=10,
        max_steps=10,
        render=False,
    )

    assert result["status"] == "planned_trainer_engagement"
    assert result["buttons"] == ["right"]
    assert result["position"] == "map=0x33,x=18,y=47"


def test_same_map_planner_clears_blocking_item_ball(monkeypatch) -> None:
    start = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 25, "y": 12},
    }
    pickup_dialogue = {
        "mode": "menu",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 25, "y": 12},
    }
    target = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 25, "y": 11},
    }

    class FakePyBoy:
        current = deepcopy(start)
        facing = None
        item_cleared = False
        pickup_open = False

    fake_pyboy = FakePyBoy()

    def fake_state(pyboy):
        return (
            deepcopy(pyboy.current),
            pyboy.facing,
            pyboy.item_cleared,
            pyboy.pickup_open,
        )

    def fake_load_state(pyboy, state):
        pyboy.current = deepcopy(state[0])
        pyboy.facing = state[1]
        pyboy.item_cleared = state[2]
        pyboy.pickup_open = state[3]

    def fake_run_navigation_button(pyboy, button: str, *, render: bool) -> dict:
        if button == "up":
            pyboy.facing = "up"
            pyboy.current = deepcopy(target if pyboy.item_cleared else start)
            return pyboy.current
        if button == "a" and pyboy.facing == "up" and not pyboy.item_cleared:
            if pyboy.pickup_open:
                pyboy.pickup_open = False
                pyboy.item_cleared = True
                pyboy.current = deepcopy(start)
            else:
                pyboy.pickup_open = True
                pyboy.current = deepcopy(pickup_dialogue)
            return pyboy.current
        pyboy.current = deepcopy(start)
        return pyboy.current

    monkeypatch.setattr(skill_execution, "snapshot", lambda pyboy: pyboy.current)
    monkeypatch.setattr(skill_execution, "snapshot_to_dict", lambda value: value)
    monkeypatch.setattr(skill_execution, "pyboy_state_bytes", fake_state)
    monkeypatch.setattr(skill_execution, "load_pyboy_state_bytes", fake_load_state)
    monkeypatch.setattr(skill_execution, "run_navigation_button", fake_run_navigation_button)
    monkeypatch.setattr(
        skill_execution,
        "wait_for_navigation_trainer_engagement",
        lambda pyboy, *, render, max_frames: None,
    )

    result = skill_execution.find_same_map_navigation_path(
        fake_pyboy,
        target=Position(MAP_VIRIDIAN_FOREST, 25, 11),
        max_expansions=10,
        max_steps=10,
        render=False,
    )

    assert result["status"] == "planned"
    assert result["buttons"] == ["up", "a", "a", "up"]


def test_same_map_planner_does_not_treat_sign_dialogue_as_item_pickup(monkeypatch) -> None:
    start = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 4, "y": 23},
    }
    sign_dialogue = {
        "mode": "dialogue",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 4, "y": 23},
    }

    class FakePyBoy:
        current = deepcopy(start)
        facing = None
        sign_open = False

    fake_pyboy = FakePyBoy()

    def fake_state(pyboy):
        return (deepcopy(pyboy.current), pyboy.facing, pyboy.sign_open)

    def fake_load_state(pyboy, state):
        pyboy.current = deepcopy(state[0])
        pyboy.facing = state[1]
        pyboy.sign_open = state[2]

    def fake_run_navigation_button(pyboy, button: str, *, render: bool) -> dict:
        if button == "up" and not pyboy.sign_open:
            pyboy.facing = "up"
            pyboy.current = deepcopy(start)
            return pyboy.current
        if button == "a" and pyboy.facing == "up":
            pyboy.sign_open = True
            pyboy.current = deepcopy(sign_dialogue)
            return pyboy.current
        if pyboy.sign_open:
            pyboy.current = deepcopy(sign_dialogue)
            return pyboy.current
        pyboy.current = deepcopy(start)
        return pyboy.current

    monkeypatch.setattr(skill_execution, "snapshot", lambda pyboy: pyboy.current)
    monkeypatch.setattr(skill_execution, "snapshot_to_dict", lambda value: value)
    monkeypatch.setattr(skill_execution, "pyboy_state_bytes", fake_state)
    monkeypatch.setattr(skill_execution, "load_pyboy_state_bytes", fake_load_state)
    monkeypatch.setattr(skill_execution, "run_navigation_button", fake_run_navigation_button)
    monkeypatch.setattr(
        skill_execution,
        "wait_for_navigation_trainer_engagement",
        lambda pyboy, *, render, max_frames: None,
    )

    result = skill_execution.find_same_map_navigation_path(
        fake_pyboy,
        target=Position(MAP_VIRIDIAN_FOREST, 4, 22),
        max_expansions=5,
        max_steps=5,
        render=False,
    )

    assert result["status"] == "not_found"
    assert result["buttons"] == []


def test_stale_overworld_warning_is_not_a_trainer_waypoint_by_itself() -> None:
    before = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 24, "y": 42},
    }
    after = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 23, "y": 42},
    }
    after["warnings"] = [STALE_TEXT_MENU_OVERWORLD_WARNING]

    result = navigate_within_viridian_forest_region(after, target="mid_north", before_snapshot=before)

    assert result.status == "failed"
    assert "trainer alert" not in result.summary.lower()


def test_navigation_start_blocks_when_stale_text_is_visible() -> None:
    screenshot = (
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T100138512982Z"
        / "final.png"
    )
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 4, "y": 23},
        "warnings": [STALE_TEXT_MENU_OVERWORLD_WARNING],
    }

    result = navigate_within_viridian_forest_region(
        snapshot,
        target="forest_north_exit",
        screenshot_path=screenshot,
    )

    assert result.status == "blocked"
    assert "clearing stale text" in result.summary


def test_navigation_start_allows_clean_overworld_despite_stale_wram_warning() -> None:
    screenshot = (
        ROOT
        / "research"
        / "artifacts"
        / "local-gemma-chapter-runs"
        / "20260629T220710421584Z"
        / "skill-runs"
        / "navigate_within_viridian_forest_region"
        / "20260629T221058Z"
        / "before.png"
    )
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": MAP_VIRIDIAN_FOREST, "x": 28, "y": 43},
        "warnings": [STALE_TEXT_MENU_OVERWORLD_WARNING],
    }

    result = navigate_within_viridian_forest_region(
        snapshot,
        target="forest_north_exit",
        screenshot_path=screenshot,
    )

    assert result.status == "succeeded"
    assert "can start" in result.summary


def test_trainer_alert_pending_dialogue_uses_stale_overworld_warning() -> None:
    assert trainer_alert_pending_dialogue(
        {
            "mode": "overworld",
            "battle_type_raw": 0,
            "warnings": [STALE_TEXT_MENU_OVERWORLD_WARNING],
        }
    )


def test_north_gate_aliases_distinguish_gate_sides() -> None:
    assert resolve_landmark("north_gate").id == "viridian_forest_north_gate_from_south"
    assert resolve_landmark("north_gate_south").id == "viridian_forest_north_gate_from_south"
    assert resolve_landmark("north_gate_north").id == "viridian_forest_north_gate_from_north"
    assert resolve_landmark("forest_north_exit").id == "viridian_forest_north_exit"
    assert resolve_landmark("mid_north").id == "viridian_forest_mid_north_corridor"


def test_viridian_pokecenter_aliases_resolve_to_interior() -> None:
    assert resolve_landmark("viridian_pokecenter").id == "viridian_pokecenter_inside"
    assert resolve_landmark("pokecenter").position == Position(MAP_VIRIDIAN_POKECENTER, 3, 7)


def test_viridian_city_routes_to_pokecenter_door() -> None:
    segment_target, transition_button = next_navigation_segment(
        Position(MAP_VIRIDIAN_CITY, 19, 27),
        Position(MAP_VIRIDIAN_POKECENTER, 3, 7),
    )

    assert segment_target == Position(MAP_VIRIDIAN_CITY, 23, 26)
    assert transition_button == "up"


def test_pokecenter_routes_back_to_city() -> None:
    segment_target, transition_button = next_navigation_segment(
        Position(MAP_VIRIDIAN_POKECENTER, 3, 7),
        Position(MAP_VIRIDIAN_CITY, 19, 27),
    )

    assert segment_target == Position(MAP_VIRIDIAN_POKECENTER, 3, 7)
    assert transition_button == "down"


def test_north_exit_routes_through_mid_north_corridor_waypoint() -> None:
    start = Position(MAP_VIRIDIAN_FOREST, 26, 33)
    north_exit = Position(MAP_VIRIDIAN_FOREST, 1, 0)

    waypoint = next_same_map_navigation_waypoint(start, north_exit)

    assert waypoint == Position(MAP_VIRIDIAN_FOREST, 17, 9)


def test_north_gate_cross_map_route_uses_mid_north_corridor_waypoint() -> None:
    start = Position(MAP_VIRIDIAN_FOREST, 26, 33)
    north_gate_south = resolve_landmark("north_gate").position

    segment_target, transition_button = next_navigation_segment(start, north_gate_south)

    assert segment_target == Position(MAP_VIRIDIAN_FOREST, 17, 9)
    assert transition_button is None


def test_mid_north_to_north_exit_uses_local_planner_segment() -> None:
    segment_target, transition_button = next_navigation_segment(
        Position(MAP_VIRIDIAN_FOREST, 17, 9),
        Position(MAP_VIRIDIAN_FOREST, 1, 0),
    )

    assert segment_target == Position(MAP_VIRIDIAN_FOREST, 1, 0)
    assert transition_button is None


def test_route_2_south_side_enters_south_gate_for_forest_north_exit() -> None:
    segment_target, transition_button = next_navigation_segment(
        Position(MAP_ROUTE_2, 8, 71),
        Position(MAP_VIRIDIAN_FOREST, 1, 0),
    )

    assert segment_target == Position(MAP_ROUTE_2, 3, 44)
    assert transition_button == "up"


def test_forest_to_route_22_routes_back_out_south_gate() -> None:
    start = Position(MAP_VIRIDIAN_FOREST, 32, 43)
    route_22 = resolve_landmark("route_22_grass").position

    segment_target, transition_button = next_navigation_segment(start, route_22)

    assert segment_target == Position(MAP_VIRIDIAN_FOREST, 17, 47)
    assert transition_button == "down"
