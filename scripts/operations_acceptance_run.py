from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.operations import OperationsPaths, OperationsRunControl, OperationsStore  # noqa: E402


def run_id() -> str:
    return datetime.now(UTC).strftime("operations-test-%Y%m%dT%H%M%SZ")


def screenshot(path: Path, action: int, status: str) -> None:
    image = Image.new("RGB", (160, 144), "#e8f1df")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 159, 18), fill="#273d34")
    draw.text((7, 5), "REMOTE OPS TEST", fill="#f4fff7")
    draw.rectangle((12, 32, 147, 107), fill="#b7d69c", outline="#557b4a", width=2)
    draw.text((23, 48), f"ACTION {action:03d}", fill="#20372b")
    draw.text((23, 66), status.upper().replace("_", " "), fill="#20372b")
    draw.text((23, 88), "SAFE CHECKPOINT", fill="#557b4a")
    draw.text((7, 126), "No ROM or model required", fill="#3f554b")
    image.save(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ROM-free Remote Operations phone acceptance fixture.")
    parser.add_argument("--actions", type=int, default=3600)
    parser.add_argument("--action-seconds", type=float, default=1.0)
    parser.add_argument("--operations-dir", default="research/artifacts/operations")
    parser.add_argument("--report-root", default="research/artifacts/local-gemma-chapter-runs")
    parser.add_argument("--dropbox-root", default="D:/Dropbox")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    identifier = run_id()
    report_root = (ROOT / args.report_root).resolve()
    run_dir = report_root / identifier
    run_dir.mkdir(parents=True, exist_ok=True)
    image_path = run_dir / "final.png"
    store = OperationsStore(
        OperationsPaths(
            state_dir=(ROOT / args.operations_dir).resolve(),
            report_root=report_root,
            dropbox_root=Path(args.dropbox_root).resolve() if args.dropbox_root else None,
        )
    )
    control = OperationsRunControl(store, identifier)
    control.begin(
        status="starting",
        actionCount=0,
        model="deterministic-acceptance-fixture",
        goal="Verify phone observation, pause/resume, safe stop, and disconnect independence.",
        chapter={
            "id": "remote_operations_acceptance",
            "title": "Remote Operations Acceptance",
            "objective": "Observe this fixture from a phone and pause it without remote desktop.",
            "success": False,
        },
    )
    history: list[dict] = []
    finish = {
        "status": "checkpoint",
        "success": False,
        "summary": "Acceptance fixture reached its bounded action checkpoint.",
        "failureCategory": None,
        "stopReason": "action_budget",
    }

    for action in range(1, max(args.actions, 1) + 1):
        signal = control.boundary()
        if signal != "continue":
            finish = {
                "status": "checkpoint",
                "success": False,
                "summary": f"Acceptance fixture stopped safely: {signal}.",
                "failureCategory": None,
                "stopReason": f"operator_{signal}",
            }
            break
        screenshot(image_path, action, "running")
        decision = {
            "action": action,
            "skillId": "observe_checkpoint",
            "args": {"scope": "remote_operations_fixture"},
            "plaintextReasoning": "Advance one bounded fixture action so the operator can verify live status and durable controls.",
        }
        result = {
            "skill_id": "observe_checkpoint",
            "status": "succeeded",
            "summary": f"Acceptance action {action} completed without touching the emulator.",
            "evidence": [f"fixture_action={action}", "emulator_touched=false"],
            "warnings": [],
        }
        history_item = {**decision, "result": result}
        history.append(history_item)
        snapshot = {
            "mode": "acceptance_fixture",
            "position": {"map_id": 0, "map_name": "Remote Operations Lab", "x": action, "y": 0},
            "party": [
                {"slot": 1, "species_name": "Squirtle", "nickname": "TESTER", "level": 5, "hp": 20, "max_hp": 20, "status": 0}
            ],
            "inventory": [{"item_name": "Poke Ball", "quantity": 5}],
        }
        control.update(
            status="running",
            actionCount=action,
            model="deterministic-acceptance-fixture",
            goal="Verify phone observation, pause/resume, safe stop, and disconnect independence.",
            chapter={
                "id": "remote_operations_acceptance",
                "title": "Remote Operations Acceptance",
                "objective": "Observe this fixture from a phone and pause it without remote desktop.",
                "success": False,
            },
            snapshot=snapshot,
            screenshotPath=str(image_path),
            lastDecision=decision,
            lastSkillResult=result,
        )
        time.sleep(max(args.action_seconds, 0.05))
        signal = control.boundary(after_action=True)
        if signal != "continue":
            finish = {
                "status": "checkpoint",
                "success": False,
                "summary": f"Acceptance fixture stopped safely: {signal}.",
                "failureCategory": None,
                "stopReason": f"operator_{signal}",
            }
            break

    final_snapshot = {
        "mode": "acceptance_fixture",
        "position": {"map_id": 0, "map_name": "Remote Operations Lab", "x": len(history), "y": 0},
        "party": [
            {"slot": 1, "species_name": "Squirtle", "nickname": "TESTER", "level": 5, "hp": 20, "max_hp": 20, "status": 0}
        ],
        "inventory": [{"item_name": "Poke Ball", "quantity": 5}],
    }
    screenshot(image_path, len(history), "checkpoint")
    checkpoint = {
        "schema": "checkpoint_interrogation_v1",
        "verdict": "healthy_needs_review" if str(finish.get("stopReason", "")).startswith("operator_") else "healthy_continue",
        "confidence": "high",
        "continueRecommended": not str(finish.get("stopReason", "")).startswith("operator_"),
        "summary": "Remote Operations acceptance fixture ended at a durable safe checkpoint.",
        "evidence": ["fixture_only=true", f"actions={len(history)}", f"stop_reason={finish.get('stopReason')}"],
        "reviewItems": [],
        "fallbackTaken": [],
    }
    report = {
        "schema": "local_gemma_chapter_run_v1",
        "createdUtc": datetime.now(UTC).isoformat(),
        "model": "deterministic-acceptance-fixture",
        "goal": "Verify phone observation, pause/resume, safe stop, and disconnect independence.",
        "finish": finish,
        "chapterTimeline": [
            {
                "action": max(len(history), 1),
                "chapterId": "remote_operations_acceptance",
                "title": "Remote Operations Acceptance",
                "objective": "Observe this fixture from a phone and pause it without remote desktop.",
                "success": False,
            }
        ],
        "history": history,
        "requests": [],
        "finalScreenshot": str(image_path),
        "finalState": None,
        "finalSnapshot": final_snapshot,
        "checkpoint": checkpoint,
    }
    (run_dir / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    control.update(
        status="checkpoint",
        actionCount=len(history),
        snapshot=final_snapshot,
        screenshotPath=str(image_path),
        checkpoint=checkpoint,
        finish=finish,
    )
    print(json.dumps({"runId": identifier, "actions": len(history), "finish": finish}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
