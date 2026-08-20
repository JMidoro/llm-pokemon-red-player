from __future__ import annotations

import json
from pathlib import Path

import _path  # noqa: F401

from pokemon_player.capsule_io import load_capsule_specs
from pokemon_player.capsule_model import assign_split, validate_capsule_spec


ROOT = Path(__file__).resolve().parents[1]


def test_phase4_capsule_specs_are_valid() -> None:
    specs = load_capsule_specs(ROOT / "research" / "capsules")

    assert {spec["id"] for spec in specs} == {"cerulean_misty", "viridian_forest_catching"}
    for spec in specs:
        assert validate_capsule_spec(spec) == []
        assert spec["budgets"]["max_button_actions"] > 0
        assert spec["success_conditions"]
        assert spec["failure_conditions"]
        assert spec["abort_conditions"]


def test_phase4_capsules_defer_rocket_hideout() -> None:
    specs = load_capsule_specs(ROOT / "research" / "capsules")

    assert all("rocket" not in json.dumps(spec).lower() for spec in specs)


def test_capsule_split_is_deterministic_and_has_holdout_for_multiple_states() -> None:
    state_ids = [f"golden:state_{index}" for index in range(10)]

    first = assign_split(
        capsule_id="example",
        state_ids=state_ids,
        seed="phase4-v0",
        holdout_ratio=0.2,
    )
    second = assign_split(
        capsule_id="example",
        state_ids=list(reversed(state_ids)),
        seed="phase4-v0",
        holdout_ratio=0.2,
    )

    assert first == second
    assert list(first.values()).count("holdout") == 2
    assert list(first.values()).count("tuning") == 8
