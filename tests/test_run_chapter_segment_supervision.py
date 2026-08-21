from __future__ import annotations

from scripts.run_chapter_segment import build_parser, operator_finish, progress_observation


def test_canonical_runner_accepts_supervisor_registration_and_operations_paths() -> None:
    args = build_parser().parse_args(
        [
            "--provider",
            "replay",
            "--run-id",
            "segment-000001-a1",
            "--run-root",
            "supervisor/segments",
            "--operations-dir",
            "operations",
            "--no-operations-control",
        ]
    )

    assert args.run_id == "segment-000001-a1"
    assert args.run_root == "supervisor/segments"
    assert args.operations_dir == "operations"
    assert args.no_operations_control is True


def test_operator_stop_maps_to_safe_machine_reason() -> None:
    finish = operator_finish("stop_after_action")

    assert finish["status"] == "checkpoint"
    assert finish["stopReason"] == "operator_stop_after_action"
    assert finish["failureCategory"] is None


def test_progress_observation_records_state_and_resource_signals() -> None:
    observation = progress_observation(
        action=3,
        state_hash="abc123",
        chapter={"chapterId": "chapter_2", "success": False},
        snapshot_dict={
            "mode": "overworld",
            "position": {"map_id": 1, "x": 2, "y": 3},
            "money": 3000,
            "badge_names": [],
            "party": [{"species_id": 7, "level": 6, "hp": 20, "status": 0}],
            "inventory": [{"item_id": 4, "quantity": 5}],
        },
    )

    assert observation["stateHash"] == "abc123"
    assert observation["position"]["x"] == 2
    assert observation["party"][0]["level"] == 6
    assert observation["inventory"] == [{"itemId": 4, "quantity": 5}]
