from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.durable_io import atomic_write_json, require_safe_component, utc_now  # noqa: E402
from pokemon_player.operations import OperationsPaths, OperationsRunControl, OperationsStore  # noqa: E402
from pokemon_player.run_interrogation import interrogate_run_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ROM-free durable supervisor segment fixture.")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-in", required=True)
    parser.add_argument("--operations-dir", required=True)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--action-seconds", type=float, default=0.25)
    parser.add_argument(
        "--outcome",
        choices=("healthy", "model_error", "unsafe", "stalled", "state_gap", "missing_report"),
        default="healthy",
    )
    return parser.parse_args()


def draw_fixture(path: Path, *, action: int, status: str) -> None:
    image = Image.new("RGB", (160, 144), "#e8f1df")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 159, 18), fill="#273d34")
    draw.text((7, 5), "SUPERVISOR SOAK", fill="#f4fff7")
    draw.rectangle((12, 32, 147, 107), fill="#b7d69c", outline="#557b4a", width=2)
    draw.text((23, 48), f"ACTION {action:04d}", fill="#20372b")
    draw.text((23, 68), status.upper().replace("_", " "), fill="#20372b")
    draw.text((23, 88), "SAFE BOUNDARY", fill="#557b4a")
    image.save(path)


def operator_finish(signal: str) -> dict[str, Any]:
    return {
        "status": "checkpoint",
        "success": False,
        "summary": f"Fixture stopped safely for operator signal {signal}.",
        "failureCategory": None,
        "stopReason": f"operator_{signal}",
    }


def main() -> int:
    args = parse_args()
    run_id = require_safe_component(args.run_id, label="run id")
    run_root = Path(args.run_root).resolve()
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_in = Path(args.state_in).resolve()
    if not state_in.is_file():
        raise FileNotFoundError(state_in)
    operations_dir = Path(args.operations_dir).resolve()
    store = OperationsStore(
        OperationsPaths(
            state_dir=operations_dir,
            report_root=run_root,
        )
    )
    control = OperationsRunControl(store, run_id)
    control.begin(
        status="starting",
        actionCount=0,
        provider="fixture",
        model="deterministic-supervisor-fixture",
        goal="Exercise durable segment supervision without a ROM or model.",
        chapter={
            "id": "durable_supervisor_soak",
            "title": "Durable Supervisor Soak",
            "objective": "Advance bounded fixture segments while preserving safe checkpoints.",
            "success": False,
        },
    )
    process_record = {
        "schema": "supervisor_fixture_process_v1",
        "runId": run_id,
        "pid": os.getpid(),
        "startedUtc": utc_now(),
        "startedEpoch": time.time(),
        "endedUtc": None,
        "endedEpoch": None,
    }
    atomic_write_json(run_dir / "fixture-process.json", process_record)
    screenshot = run_dir / "final.png"
    final_state = run_dir / "final.state"
    history: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    finish: dict[str, Any] = {
        "status": "checkpoint",
        "success": False,
        "summary": "Fixture action budget reached a safe checkpoint.",
        "failureCategory": None,
        "stopReason": "action_budget",
    }
    started = time.monotonic()
    action = 0
    while time.monotonic() - started < max(args.duration_seconds, 0.05):
        signal = control.boundary()
        if signal != "continue":
            finish = operator_finish(signal)
            break
        action += 1
        draw_fixture(screenshot, action=action, status="running")
        result_status = "blocked" if args.outcome in {"stalled", "state_gap"} else "succeeded"
        warnings = ["unclassified_visual_state"] if args.outcome == "state_gap" else []
        history.append(
            {
                "action": action,
                "skillId": "observe_checkpoint",
                "args": {"scope": "supervisor_fixture"},
                "plaintextReasoning": "Advance one bounded fixture action.",
                "result": {
                    "status": result_status,
                    "summary": (
                        "Fixture intentionally withheld progress."
                        if result_status == "blocked"
                        else "Fixture advanced safely."
                    ),
                    "evidence": [f"fixture_action={action}"],
                    "warnings": warnings,
                },
            }
        )
        observations.append(
            {
                "action": action,
                "stateHash": "fixed-state" if args.outcome == "stalled" else f"state-{action}",
                "chapterId": "durable_supervisor_soak",
                "position": {
                    "map_id": 1,
                    "map_name": "Supervisor Fixture",
                    "x": 0 if args.outcome == "stalled" else action,
                    "y": 0,
                },
                "party": [{"species_id": 7, "level": 5, "hp": 20, "status": 0}],
                "inventory": [{"item_id": 4, "quantity": 5}],
                "money": 3000,
            }
        )
        snapshot = fixture_snapshot(action, unsafe=args.outcome == "unsafe")
        control.update(
            status="running",
            actionCount=action,
            snapshot=snapshot,
            screenshotPath=str(screenshot),
            lastDecision=history[-1],
            lastSkillResult=history[-1]["result"],
        )
        time.sleep(max(args.action_seconds, 0.01))
        signal = control.boundary(after_action=True)
        if signal != "continue":
            finish = operator_finish(signal)
            break

    if args.outcome == "model_error":
        finish = {
            "status": "stopped",
            "success": False,
            "summary": "Injected fixture provider connection failure.",
            "failureCategory": "connection",
            "stopReason": None,
        }
    state_bytes = state_in.read_bytes() + f"\n{run_id}:{action}".encode()
    final_state.write_bytes(state_bytes)
    draw_fixture(screenshot, action=action, status="checkpoint")
    final_snapshot = fixture_snapshot(action, unsafe=args.outcome == "unsafe")
    report = {
        "schema": "director_segment_run_v1",
        "createdUtc": utc_now(),
        "runId": run_id,
        "mode": "supervisor_fixture",
        "status": finish["status"],
        "provider": {"provider": "fixture", "model": "deterministic-supervisor-fixture"},
        "goal": "Exercise durable segment supervision without a ROM or model.",
        "finish": finish,
        "history": history,
        "requests": [],
        "ticks": [],
        "errors": [],
        "chapterTimeline": [
            {
                "action": max(action, 1),
                "chapterId": "durable_supervisor_soak",
                "title": "Durable Supervisor Soak",
                "success": False,
            }
        ],
        "progressObservations": observations,
        "finalState": str(final_state),
        "finalScreenshot": str(screenshot),
        "finalSnapshot": final_snapshot,
        "video": {"enabled": False},
    }
    report["checkpoint"] = interrogate_run_report(report)
    if args.outcome != "missing_report":
        atomic_write_json(run_dir / "checkpoint.json", report["checkpoint"])
        atomic_write_json(run_dir / "report.json", report)
    process_record.update(endedUtc=utc_now(), endedEpoch=time.time())
    atomic_write_json(run_dir / "fixture-process.json", process_record)
    control.update(
        status="checkpoint",
        actionCount=action,
        snapshot=final_snapshot,
        screenshotPath=str(screenshot),
        checkpoint=report["checkpoint"],
        finish=finish,
    )
    return 1 if report["checkpoint"]["verdict"] in {"model_error", "unsafe_state"} else 0


def fixture_snapshot(action: int, *, unsafe: bool) -> dict[str, Any]:
    if unsafe:
        return {"mode": "unknown", "position": {}}
    return {
        "mode": "overworld",
        "position": {
            "map_id": 1,
            "map_name": "Supervisor Fixture",
            "x": action,
            "y": 0,
        },
        "party": [
            {
                "slot": 1,
                "species_id": 7,
                "species_name": "Squirtle",
                "level": 5,
                "hp": 20,
                "max_hp": 20,
                "status": 0,
            }
        ],
        "inventory": [{"item_id": 4, "item_name": "Poke Ball", "quantity": 5}],
        "money": 3000,
    }


if __name__ == "__main__":
    raise SystemExit(main())
