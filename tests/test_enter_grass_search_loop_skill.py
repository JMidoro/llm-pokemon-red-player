from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.enter_grass_search_loop import enter_grass_search_loop


ROOT = Path(__file__).resolve().parents[1]
PROMOTION_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "grass_patch_and_encounter_search"
CAPSULE_REGION_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "capsule_a_region_and_landmarks"


def load_record(name: str) -> dict:
    return json.loads((PROMOTION_EVIDENCE / f"{name}.promotion-evidence.json").read_text(encoding="utf-8"))


def load_capsule_record(name: str) -> dict:
    return json.loads((CAPSULE_REGION_EVIDENCE / f"{name}.promotion-evidence.json").read_text(encoding="utf-8"))


def test_grass_search_can_start_near_approved_patch() -> None:
    record = load_record("step_01_near_viridian_approved_grass")

    result = enter_grass_search_loop(
        record["snapshot"],
        patch="forest_grass",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "near the approved grass patch" in result.summary


def test_grass_search_can_start_inside_approved_patch() -> None:
    record = load_record("step_01_standing_in_viridian_approved_grass")

    result = enter_grass_search_loop(
        record["snapshot"],
        patch="forest_grass",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "inside the approved grass patch" in result.summary


def test_grass_search_can_use_current_map_route_22_patch() -> None:
    record = load_capsule_record("step_01_route_22_grass")

    result = enter_grass_search_loop(
        record["snapshot"],
        patch="current_map",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "approved grass patch" in result.summary
    assert "target_patch_id=route_22_grass" in result.evidence


def test_grass_search_succeeds_when_wild_battle_started_in_patch() -> None:
    record = load_record("step_01_wild_battle_in_approved_grass")

    result = enter_grass_search_loop(
        record["snapshot"],
        patch="forest_grass",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "succeeded"
    assert "Wild battle started" in result.summary


def test_grass_search_blocks_when_not_near_approved_patch() -> None:
    record = load_record("step_01_blocked_not_near_grass")

    result = enter_grass_search_loop(
        record["snapshot"],
        patch="forest_grass",
        screenshot_path=record["screenshot_file"],
    )

    assert result.status == "blocked"
    assert "not in or near" in result.summary


def test_grass_search_reports_budget_failure_after_attempt() -> None:
    before = load_record("step_01_standing_in_viridian_approved_grass")
    after = load_record("step_01_standing_in_viridian_approved_grass")

    result = enter_grass_search_loop(
        after["snapshot"],
        before_snapshot=before["snapshot"],
        patch="forest_grass",
        screenshot_path=after["screenshot_file"],
    )

    assert result.status == "failed"
    assert "budget ended" in result.summary
