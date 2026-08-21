from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from pokemon_player.operations import OperationsPaths, OperationsRunControl, OperationsStore, report_summary, safe_text


def sample_report(tmp_path: Path, run_id: str = "20260820T120000000000Z") -> tuple[Path, dict]:
    run_dir = tmp_path / "reports" / run_id
    run_dir.mkdir(parents=True)
    screenshot = run_dir / "final.png"
    screenshot.write_bytes(b"png")
    report = {
        "createdUtc": "2026-08-20T12:00:00+00:00",
        "model": "local-test-model",
        "baseUrl": "http://127.0.0.1:1234/v1",
        "auth": {"tokenProvided": True, "token": "do-not-leak"},
        "stateIn": "F:\\secret\\seed.state",
        "goal": "Reach the next safe checkpoint.",
        "finish": {"status": "checkpoint", "summary": "Action budget checkpoint.", "failureCategory": None},
        "chapterTimeline": [
            {
                "action": 1,
                "chapterId": "chapter_7",
                "title": "Prepare for Brock",
                "objective": "Train safely.",
                "success": False,
            }
        ],
        "history": [
            {
                "action": 1,
                "skillId": "use_move",
                "args": {"move": "Tackle", "statePath": "F:\\secret\\before.state"},
                "plaintextReasoning": "Tackle is the safest useful move.",
                "result": {
                    "skill_id": "use_move",
                    "status": "succeeded",
                    "summary": "Tackle was used.",
                    "evidence": ["pp_delta=-1", "report_path=F:\\secret\\report.json"],
                    "warnings": [],
                    "run_dir": "F:\\secret\\skill-run",
                },
            }
        ],
        "requests": [{"response": {"secret": "raw-model-payload"}}],
        "finalScreenshot": str(screenshot),
        "finalState": str(run_dir / "final.state"),
        "finalSnapshot": {
            "mode": "battle",
            "position": {"map_name": "Route 2", "x": 6, "y": 7},
            "party": [{"slot": 1, "species_name": "Squirtle", "level": 7, "hp": 24, "max_hp": 24, "status": 0}],
            "inventory": [{"item_name": "Poke Ball", "quantity": 2}],
        },
        "checkpoint": {
            "verdict": "healthy_continue",
            "confidence": "high",
            "continueRecommended": True,
            "summary": "Safe to continue.",
            "reviewItems": [{"title": "Check battle", "detail": "Verify the final battle screen."}],
        },
    }
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return run_dir, report


def make_store(tmp_path: Path) -> OperationsStore:
    return OperationsStore(
        OperationsPaths(
            state_dir=tmp_path / "operations",
            report_root=tmp_path / "reports",
            dropbox_root=tmp_path / "Dropbox",
            director_report_root=tmp_path / "director-reports",
            director_status_dir=tmp_path / "director-status",
        ),
        director_url="http://127.0.0.1:1",
        active_stale_seconds=1,
    )


def test_report_summary_is_useful_and_excludes_sensitive_payloads(tmp_path: Path) -> None:
    _, report = sample_report(tmp_path)
    summary = report_summary(report, "20260820T120000000000Z", video_available=False)
    encoded = json.dumps(summary)

    assert summary["chapter"]["title"] == "Prepare for Brock"
    assert summary["party"][0]["species"] == "Squirtle"
    assert summary["lastDecision"]["args"] == {"move": "Tackle"}
    assert summary["lastSkillResult"]["evidence"] == ["pp_delta=-1"]
    assert summary["reviewItems"][0]["title"] == "Check battle"
    for forbidden in ("do-not-leak", "raw-model-payload", "F:\\\\secret", "baseUrl", "requests", "run_dir"):
        assert forbidden not in encoded


def test_legacy_action_budget_checkpoint_is_not_listed_as_a_failure(tmp_path: Path) -> None:
    _, report = sample_report(tmp_path)
    report["finish"]["failureCategory"] = "action_budget_exhausted"

    summary = report_summary(report, "legacy-budget-run", video_available=False)

    assert summary["checkpoint"]["verdict"] == "healthy_continue"
    assert summary["failure"] is None


def test_safe_text_redacts_embedded_host_paths_and_service_addresses() -> None:
    value = (
        "state=C:\\"
        + "Users\\operator\\Pokemon Player\\seed.state "
        + "or /"
        + "home/operator/run/report.json at http://127.0.0.1:1234/v1"
    )
    sanitized = safe_text(value)

    assert "C:\\" not in sanitized
    assert "/home/" not in sanitized
    assert "127.0.0.1" not in sanitized
    assert sanitized.count("hidden]") >= 1


def test_every_control_command_is_durable_and_audited(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    assert store.command("pause")["control"]["state"] == "paused"
    assert store.command("resume")["control"]["state"] == "running"
    assert store.command("stop_after_action")["control"]["stopAfterAction"] is True
    assert store.command("emergency_stop")["control"]["state"] == "emergency_stopped"

    events = [json.loads(line) for line in store.paths.audit.read_text(encoding="utf-8").splitlines()]
    assert [event["action"] for event in events] == ["pause", "resume", "stop_after_action", "emergency_stop"]
    assert len({event["commandId"] for event in events}) == 4


def test_paused_run_waits_without_a_remote_connection_and_resumes(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    control = OperationsRunControl(store, "test-run")
    store.command("pause")
    result: list[str] = []

    worker = threading.Thread(target=lambda: result.append(control.boundary(poll_seconds=0.01)))
    worker.start()
    time.sleep(0.06)

    assert worker.is_alive()
    assert json.loads(store.paths.active_run.read_text(encoding="utf-8"))["status"] == "paused"
    store.command("resume")
    worker.join(timeout=1)
    assert result == ["continue"]


def test_stop_after_action_only_triggers_at_after_action_boundary(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    control = OperationsRunControl(store, "test-run")
    store.command("stop_after_action")

    assert control.boundary(after_action=False) == "continue"
    assert control.boundary(after_action=True) == "stop_after_action"


def test_beginning_a_new_run_drops_terminal_fields_from_the_previous_run(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    previous = OperationsRunControl(store, "previous-run")
    previous.update(
        status="checkpoint",
        checkpoint={"verdict": "healthy_continue"},
        finish={"stopReason": "action_budget"},
        finishedUtc="2026-08-20T12:00:00+00:00",
    )

    current = OperationsRunControl(store, "current-run")
    current.begin(status="starting", actionCount=0)
    active = json.loads(store.paths.active_run.read_text(encoding="utf-8"))

    assert active["runId"] == "current-run"
    assert active["status"] == "starting"
    assert active["actionCount"] == 0
    assert "checkpoint" not in active
    assert "finish" not in active
    assert "finishedUtc" not in active

    try:
        previous.update(status="running")
    except RuntimeError as exc:
        assert "current-run" in str(exc)
    else:
        raise AssertionError("A stale run must not replace the current active-run record")


def test_snapshot_and_artifacts_never_expose_unrestricted_paths(tmp_path: Path) -> None:
    run_dir, _ = sample_report(tmp_path)
    store = make_store(tmp_path)
    snapshot = store.snapshot()
    encoded = json.dumps(snapshot)

    assert snapshot["currentRun"]["id"] == run_dir.name
    assert snapshot["capabilities"]["rawButtonsExposed"] is False
    assert "F:\\\\secret" not in encoded
    assert str(tmp_path) not in encoded
    assert store.artifact_path(run_dir.name, "screenshot")[0] == run_dir / "final.png"


def test_report_summaries_are_cached_until_report_changes(tmp_path: Path, monkeypatch) -> None:
    run_dir, _ = sample_report(tmp_path)
    store = make_store(tmp_path)
    first = store.report_summaries()

    monkeypatch.setattr("pokemon_player.operations.read_json", lambda path: (_ for _ in ()).throw(AssertionError(path)))
    second = store.report_summaries()

    assert first == second
    assert second[0]["id"] == run_dir.name


def test_browser_director_reports_are_sanitized_and_provider_neutral(tmp_path: Path) -> None:
    report_dir = tmp_path / "director-reports" / "20260820T130000000Z"
    report_dir.mkdir(parents=True)
    report = {
        "schema": "llm_director_run_v1",
        "status": "stopped",
        "model": "hosted-provider/model-large",
        "goal": "Catch Pikachu without wasting Poke Balls.",
        "assistantMessage": "I entered the approved grass and started a battle.",
        "steps": [
            {
                "name": "execute_skill",
                "args": {
                    "skillId": "enter_grass_search_loop",
                    "args": {"patch": "forest_grass"},
                    "plaintextReasoning": "I need a valid encounter.",
                },
                "status": "succeeded",
                "summary": "Battle started.",
                "plaintextReasoning": "I need a valid encounter.",
                "result": {
                    "skillId": "enter_grass_search_loop",
                    "status": "succeeded",
                    "summary": "Battle started.",
                    "lastResult": {
                        "status": "succeeded",
                        "summary": "Battle started.",
                        "reportPath": "C:\\private\\report.json",
                    },
                },
            }
        ],
        "playerStatus": {
            "snapshot": {
                "mode": "battle",
                "position": {"map_name": "Viridian Forest", "x": 32, "y": 43},
                "party": [{"slot": 1, "species_name": "Squirtle", "level": 9, "hp": 29, "max_hp": 29}],
                "inventory": [{"item_name": "Poke Ball", "quantity": 4}],
            }
        },
        "openaiRequest": {"input": "raw provider payload"},
        "reportPath": "C:\\private\\browser-report.json",
    }
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    store = make_store(tmp_path)

    summaries = store.director_report_summaries()
    payload = store.summary_payload("director-20260820T130000000Z")
    encoded = json.dumps(payload)

    assert summaries[0]["source"] == "browser_director"
    assert summaries[0]["model"] == "hosted-provider/model-large"
    assert summaries[0]["lastDecision"]["skillId"] == "enter_grass_search_loop"
    assert summaries[0]["party"][0]["species"] == "Squirtle"
    assert "raw provider payload" not in encoded
    assert "C:\\private" not in encoded
    assert "openaiRequest" not in encoded


def test_live_director_screenshot_is_confined_to_exact_status_directory(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    status_dir = tmp_path / "director-status"
    status_dir.mkdir()
    screenshot = status_dir / "current.png"
    screenshot.write_bytes(b"png")

    resolved, content_type, _ = store.artifact_path("live-director", "screenshot")

    assert resolved == screenshot
    assert content_type == "image/png"


def test_artifact_resolver_rejects_traversal_and_outside_screenshot(tmp_path: Path) -> None:
    run_dir, report = sample_report(tmp_path)
    store = make_store(tmp_path)
    report["finalScreenshot"] = str(tmp_path / "outside.png")
    (tmp_path / "outside.png").write_bytes(b"png")
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

    try:
        store.artifact_path("../outside", "screenshot")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Traversal run id must be rejected")

    try:
        store.artifact_path(run_dir.name, "screenshot")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Outside screenshot must be rejected")
