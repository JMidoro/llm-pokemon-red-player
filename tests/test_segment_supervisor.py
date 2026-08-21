from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pytest

from pokemon_player.durable_io import atomic_write_json, read_json
from pokemon_player.segment_supervisor import (
    SUPERVISOR_STATES,
    DurableSegmentSupervisor,
    LeaseBusyError,
    LineageLease,
    SegmentExecution,
    SegmentRequest,
    SubprocessSegmentRunner,
    SupervisorConfig,
    SupervisorPaths,
)


def test_subprocess_runner_offsets_seed_by_accepted_actions_and_fresh_starts_once(
    tmp_path: Path,
) -> None:
    runner = SubprocessSegmentRunner(
        project_root=tmp_path,
        provider="lmstudio-chat",
        max_actions=100,
        temperature=0.1,
        first_inference_seed=5301,
        fresh_start_first_segment=True,
    )

    first = SegmentRequest(
        lineage_id="trial",
        segment_id="segment-000001-a1",
        sequence=1,
        attempt=1,
        input_state=tmp_path / "seed.state",
        segment_dir=tmp_path / "segments" / "segment-000001-a1",
    )
    second = SegmentRequest(
        lineage_id="trial",
        segment_id="segment-000002-a1",
        sequence=2,
        attempt=1,
        input_state=tmp_path / "continued.state",
        segment_dir=tmp_path / "segments" / "segment-000002-a1",
        inference_action_offset=37,
    )

    first_command = runner._command(first)
    second_command = runner._command(second)

    assert "--fresh-start" in first_command
    assert "--fresh-start" not in second_command
    assert first_command[first_command.index("--seed") + 1] == "5301"
    assert second_command[second_command.index("--seed") + 1] == "5338"
    assert first_command[first_command.index("--temperature") + 1] == "0.1"


class FakeRunner:
    def __init__(self, outcomes: list[str], *, healthy: bool = True) -> None:
        self.outcomes = list(outcomes)
        self.healthy = healthy
        self.requests: list[SegmentRequest] = []
        self.health_checks = 0

    def run(
        self,
        request: SegmentRequest,
        *,
        on_started: Callable[[int | None], None],
        on_poll: Callable[[], None],
    ) -> SegmentExecution:
        del on_poll
        self.requests.append(request)
        on_started(10000 + len(self.requests))
        outcome = self.outcomes.pop(0)
        if outcome == "missing_report":
            return SegmentExecution(request.report_path, return_code=7, child_pid=None)
        state = request.segment_dir / "final.state"
        screenshot = request.segment_dir / "final.png"
        state.write_bytes(f"state-{request.segment_id}".encode())
        screenshot.write_bytes(b"png")
        report = fake_report(outcome, state=state, screenshot=screenshot)
        request.report_path.write_text(json.dumps(report), encoding="utf-8")
        return SegmentExecution(request.report_path, return_code=1 if outcome == "model_error" else 0)

    def health_check(self) -> dict[str, Any]:
        self.health_checks += 1
        return {
            "schema": "provider_health_v1",
            "provider": "fake",
            "healthy": self.healthy,
            "checkedUtc": "2026-08-20T00:00:00+00:00",
        }


def fake_report(outcome: str, *, state: Path, screenshot: Path) -> dict[str, Any]:
    finish: dict[str, Any] = {
        "status": "checkpoint",
        "success": False,
        "summary": "Bounded fixture checkpoint.",
        "failureCategory": None,
        "stopReason": "action_budget",
    }
    history = [
        {
            "action": 1,
            "skillId": "advance_dialogue",
            "result": {"status": "succeeded", "summary": "Progressed.", "warnings": []},
        }
    ]
    snapshot = {
        "mode": "overworld",
        "position": {"map_id": 1, "map_name": "Fixture", "x": 2, "y": 3},
        "party": [{"species_id": 7, "level": 6, "hp": 20, "max_hp": 20}],
        "inventory": [{"item_id": 4, "quantity": 5}],
        "money": 3000,
    }
    observations = [
        {
            "action": 1,
            "stateHash": "state-1",
            "chapterId": "fixture_chapter",
            "position": snapshot["position"],
            "party": snapshot["party"],
            "inventory": snapshot["inventory"],
            "money": snapshot["money"],
        }
    ]
    if outcome == "model_error":
        finish.update(
            status="stopped",
            summary="Provider connection failed before an action started.",
            failureCategory="connection",
            stopReason=None,
        )
    elif outcome == "unsafe":
        snapshot = {"mode": "unknown", "position": {}}
    elif outcome == "stalled":
        history = [
            {
                "action": index,
                "skillId": "advance_dialogue",
                "result": {
                    "status": "blocked",
                    "summary": "No prompt visible.",
                    "warnings": ["no_progress"],
                },
            }
            for index in range(1, 6)
        ]
        observations = [
            {
                "action": index,
                "stateHash": "same-state",
                "chapterId": "fixture_chapter",
                "position": snapshot["position"],
                "party": snapshot["party"],
                "inventory": snapshot["inventory"],
                "money": snapshot["money"],
            }
            for index in range(1, 6)
        ]
    elif outcome == "state_gap":
        history = [
            {
                "action": index,
                "skillId": "advance_dialogue",
                "result": {
                    "status": "blocked",
                    "summary": "Unknown screen.",
                    "warnings": ["unclassified_visual_state"],
                },
            }
            for index in range(1, 4)
        ]
    elif outcome == "provisional":
        history = [
            {
                "action": index,
                "skillId": "literal_button_press",
                "result": {"status": "succeeded", "summary": "Pressed A.", "warnings": []},
            }
            for index in range(1, 5)
        ]
    elif outcome == "success":
        finish.update(
            status="completed",
            success=True,
            summary="Chapter success reached.",
            stopReason=None,
        )
    return {
        "schema": "director_segment_run_v1",
        "finish": finish,
        "history": history,
        "chapterTimeline": [
            {
                "action": len(history),
                "chapterId": "fixture_chapter",
                "title": "Fixture Chapter",
                "success": outcome == "success",
            }
        ],
        "progressObservations": observations,
        "finalState": str(state),
        "finalScreenshot": str(screenshot),
        "finalSnapshot": snapshot,
    }


def make_supervisor(
    tmp_path: Path,
    runner: FakeRunner,
    *,
    max_segments: int | None = 1,
    allow_provisional: bool = True,
) -> tuple[DurableSegmentSupervisor, SupervisorPaths, Path]:
    seed = tmp_path / "seed.state"
    seed.write_bytes(b"seed")
    paths = SupervisorPaths(tmp_path / "supervisor", "test-lineage")
    supervisor = DurableSegmentSupervisor(
        SupervisorConfig(
            paths=paths,
            initial_state=seed,
            allow_provisional_continue=allow_provisional,
            heartbeat_seconds=0.01,
            lease_ttl_seconds=1,
            min_free_bytes=0,
            max_segments=max_segments,
        ),
        runner,
    )
    return supervisor, paths, seed


def test_declared_state_machine_matches_milestone_contract() -> None:
    assert SUPERVISOR_STATES == {
        "idle",
        "starting",
        "running",
        "checkpointing",
        "waiting_review",
        "paused",
        "blocked",
        "completed",
        "failed",
    }


def test_healthy_segments_chain_from_hashed_final_state(tmp_path: Path) -> None:
    runner = FakeRunner(["healthy", "healthy"])
    supervisor, paths, _ = make_supervisor(tmp_path, runner, max_segments=2)

    result = supervisor.run()

    assert result["state"]["state"] == "completed"
    assert result["checkpoint"]["machineReason"] == "segment_limit_reached"
    assert runner.requests[1].input_state == runner.requests[0].segment_dir / "final.state"
    assert [request.inference_action_offset for request in runner.requests] == [0, 1]
    assert len(result["manifest"]["segments"]) == 2
    for item in result["manifest"]["segments"]:
        assert item["directorActionCount"] == 1
        segment = read_json(paths.lineage_root / str(item["manifestPath"]))
        assert segment and segment["artifacts"]["complete"] is True
        assert segment["artifacts"]["finalState"]["sha256"]


def test_model_error_retries_once_after_healthy_provider_check(tmp_path: Path) -> None:
    runner = FakeRunner(["model_error", "healthy"])
    supervisor, _, seed = make_supervisor(tmp_path, runner, max_segments=2)

    result = supervisor.run()

    assert runner.health_checks == 1
    assert [request.attempt for request in runner.requests] == [1, 2]
    assert [request.inference_action_offset for request in runner.requests] == [0, 0]
    assert [request.input_state for request in runner.requests] == [seed.resolve(), seed.resolve()]
    assert result["state"]["state"] == "completed"


def test_repeated_model_error_is_quarantined_without_losing_safe_state(tmp_path: Path) -> None:
    runner = FakeRunner(["model_error", "model_error"])
    supervisor, paths, seed = make_supervisor(tmp_path, runner, max_segments=None)

    result = supervisor.run()

    assert result["state"]["state"] == "blocked"
    assert result["manifest"]["lastSafeState"]["path"] == str(seed.resolve())
    failures = list(paths.failures.glob("*.json"))
    assert len(failures) == 1
    assert read_json(failures[0])["checkpoint"]["verdict"] == "model_error"


def test_unsafe_state_rolls_back_and_preserves_evidence(tmp_path: Path) -> None:
    runner = FakeRunner(["unsafe"])
    supervisor, paths, seed = make_supervisor(tmp_path, runner, max_segments=None)

    result = supervisor.run()

    assert result["state"]["state"] == "blocked"
    assert result["checkpoint"]["machineReason"] == "unsafe_state"
    assert result["manifest"]["lastSafeState"]["path"] == str(seed.resolve())
    assert list(paths.failures.glob("*.json"))


def test_provisional_checkpoint_queues_review_and_continues_when_allowed(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(["provisional"])
    supervisor, paths, _ = make_supervisor(tmp_path, runner, max_segments=1)

    result = supervisor.run()

    assert result["state"]["state"] == "completed"
    reviews = list(paths.reviews.glob("*.json"))
    assert reviews
    assert read_json(reviews[0])["status"] == "queued"


def test_pause_before_launch_is_durable_until_resume(tmp_path: Path) -> None:
    runner = FakeRunner([])
    supervisor, paths, _ = make_supervisor(tmp_path, runner, max_segments=0)
    paths.operator_stop.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(paths.operator_stop, {"action": "pause"})
    results: list[dict[str, Any]] = []
    worker = threading.Thread(target=lambda: results.append(supervisor.run()))

    worker.start()
    deadline = time.time() + 2
    while time.time() < deadline:
        state = read_json(paths.state) or {}
        if state.get("state") == "paused":
            break
        time.sleep(0.01)

    assert (read_json(paths.state) or {}).get("state") == "paused"
    assert worker.is_alive()
    atomic_write_json(paths.operator_stop, {"action": "resume"})
    worker.join(timeout=2)

    assert runner.requests == []
    assert results[0]["state"]["state"] == "completed"


def test_missing_report_fails_with_previous_safe_checkpoint(tmp_path: Path) -> None:
    runner = FakeRunner(["missing_report"])
    supervisor, _, seed = make_supervisor(tmp_path, runner, max_segments=None)

    result = supervisor.run()

    assert result["state"]["state"] == "failed"
    assert result["checkpoint"]["stable"] is True
    assert result["manifest"]["lastSafeState"]["path"] == str(seed.resolve())


def test_restart_finalizes_previously_completed_child_before_new_launch(tmp_path: Path) -> None:
    runner = FakeRunner([])
    supervisor, paths, seed = make_supervisor(tmp_path, runner, max_segments=1)
    segment_id = "segment-000001-a1"
    segment_dir = paths.segments / segment_id
    segment_dir.mkdir(parents=True)
    final_state = segment_dir / "final.state"
    screenshot = segment_dir / "final.png"
    final_state.write_bytes(b"recovered")
    screenshot.write_bytes(b"png")
    (segment_dir / "report.json").write_text(
        json.dumps(fake_report("healthy", state=final_state, screenshot=screenshot)),
        encoding="utf-8",
    )
    atomic_write_json(
        paths.manifest,
        {
            "schema": "segment_lineage_manifest_v1",
            "lineageId": paths.lineage_id,
            "createdUtc": "2026-08-20T00:00:00+00:00",
            "updatedUtc": "2026-08-20T00:00:00+00:00",
            "nextSequence": 1,
            "lastSafeState": {"path": str(seed.resolve()), "segmentId": None},
            "segments": [],
        },
    )
    atomic_write_json(
        segment_dir / "manifest.json",
        {
            "schema": "segment_artifact_manifest_v1",
            "lineageId": paths.lineage_id,
            "segmentId": segment_id,
            "sequence": 1,
            "attempt": 1,
            "inputState": str(seed.resolve()),
            "status": "running",
            "childPid": None,
        },
    )
    atomic_write_json(
        paths.state,
        {
            "schema": "segment_supervisor_state_v1",
            "lineageId": paths.lineage_id,
            "state": "checkpointing",
            "currentSegment": segment_id,
            "childPid": None,
        },
    )

    result = supervisor.run()

    assert runner.requests == []
    assert result["state"]["state"] == "completed"
    assert result["manifest"]["lastSafeState"]["segmentId"] == segment_id


def test_restart_quarantines_unreported_launch_without_reusing_segment_id(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(["healthy"])
    supervisor, paths, seed = make_supervisor(tmp_path, runner, max_segments=2)
    segment_id = "segment-000001-a1"
    segment_dir = paths.segments / segment_id
    segment_dir.mkdir(parents=True)
    atomic_write_json(
        paths.manifest,
        {
            "schema": "segment_lineage_manifest_v1",
            "lineageId": paths.lineage_id,
            "createdUtc": "2026-08-20T00:00:00+00:00",
            "updatedUtc": "2026-08-20T00:00:00+00:00",
            "nextSequence": 1,
            "lastSafeState": {"path": str(seed.resolve()), "segmentId": None},
            "segments": [],
        },
    )
    atomic_write_json(
        segment_dir / "manifest.json",
        {
            "schema": "segment_artifact_manifest_v1",
            "lineageId": paths.lineage_id,
            "segmentId": segment_id,
            "sequence": 1,
            "attempt": 1,
            "inputState": str(seed.resolve()),
            "status": "registered",
            "childPid": None,
        },
    )
    atomic_write_json(
        paths.state,
        {
            "schema": "segment_supervisor_state_v1",
            "lineageId": paths.lineage_id,
            "state": "starting",
            "currentSegment": segment_id,
            "childPid": None,
        },
    )

    result = supervisor.run()

    assert runner.requests[0].sequence == 2
    assert runner.requests[0].segment_id == "segment-000002-a1"
    ids = [item["segmentId"] for item in result["manifest"]["segments"]]
    assert ids == ["segment-000001-a1", "segment-000002-a1"]


def test_lineage_lease_rejects_concurrent_supervisor(tmp_path: Path) -> None:
    paths = SupervisorPaths(tmp_path / "supervisor", "one-lineage")
    first = LineageLease(paths, "first", ttl_seconds=1)
    second = LineageLease(paths, "second", ttl_seconds=1)
    first.acquire()
    try:
        with pytest.raises(LeaseBusyError):
            second.acquire()
    finally:
        first.release()
