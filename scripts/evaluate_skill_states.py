from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.skills.attempt_catch import attempt_catch  # noqa: E402
from pokemon_player.skills.advance_dialogue import advance_dialogue  # noqa: E402
from pokemon_player.skills.close_menu_or_cancel import close_menu_or_cancel  # noqa: E402
from pokemon_player.skills.detect_capsule_success import detect_capsule_success  # noqa: E402
from pokemon_player.skills.detect_party_changed import detect_party_changed  # noqa: E402
from pokemon_player.skills.detect_wild_battle import detect_wild_battle  # noqa: E402
from pokemon_player.skills.recover_to_overworld import recover_to_overworld  # noqa: E402
from pokemon_player.skills.walk_local_direction import walk_local_direction  # noqa: E402


SKILL_RUNNERS = {
    "advance_dialogue": advance_dialogue,
    "attempt_catch": attempt_catch,
    "close_menu_or_cancel": close_menu_or_cancel,
    "detect_capsule_success": detect_capsule_success,
    "detect_party_changed": detect_party_changed,
    "detect_wild_battle": detect_wild_battle,
    "recover_to_overworld": recover_to_overworld,
    "walk_local_direction": walk_local_direction,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate implemented skills against captured skill states.")
    parser.add_argument("skill", choices=sorted(SKILL_RUNNERS))
    parser.add_argument(
        "--states-dir",
        default=str(ROOT / "research" / "skill-states"),
        help="Root skill-state metadata directory.",
    )
    parser.add_argument(
        "--report-out",
        default=None,
        help="Optional JSON report path. Defaults to research/artifacts/skill-evals/<skill>/<timestamp>.json.",
    )
    args = parser.parse_args()

    skill_dir = Path(args.states_dir) / args.skill
    metadata_paths = sorted(skill_dir.glob("*.skill.json"))
    if not metadata_paths:
        print(f"No skill metadata found in {skill_dir}.")
        return 1

    runner = SKILL_RUNNERS[args.skill]
    records_by_capture_id = {
        record["capture_id"]: record
        for record in (json.loads(path.read_text(encoding="utf-8")) for path in metadata_paths)
    }
    passed = 0
    checked = 0
    cases: list[dict[str, object]] = []
    for path in metadata_paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("phase") == "seed":
            continue
        checked += 1
        result = run_skill(args.skill, runner, record, records_by_capture_id)
        expected = record["expected_status"]
        matched = result.status == expected
        passed += int(matched)
        marker = "PASS" if matched else "FAIL"
        print(f"{marker} {record['capture_id']}: expected={expected} actual={result.status}")
        print(f"  {result.summary}")
        for evidence in result.evidence:
            print(f"  evidence: {evidence}")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        cases.append(
            {
                "capture_id": record["capture_id"],
                "metadata_path": str(path),
                "expected_status": expected,
                "actual_status": result.status,
                "matched": matched,
                "result": result.to_dict(),
            }
        )

    print(f"{passed}/{checked} non-seed captures matched for {args.skill}.")
    report_path = Path(args.report_out) if args.report_out else default_report_path(args.skill)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "skill_eval_report_v1",
        "skill_id": args.skill,
        "created_utc": datetime.now(UTC).isoformat(),
        "passed": passed,
        "checked": checked,
        "accuracy": passed / checked if checked else 0.0,
        "cases": cases,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote report: {report_path}")
    return 0 if passed == checked else 2


def default_report_path(skill_id: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "research" / "artifacts" / "skill-evals" / skill_id / f"{stamp}.json"


def run_skill(
    skill_id: str,
    runner,
    record: dict[str, object],
    records_by_capture_id: dict[str, dict[str, object]],
):
    if skill_id == "attempt_catch":
        before_record = records_by_capture_id.get("success_before")
        before_snapshot = None
        if record.get("capture_id") in {"success_after", "failed_after_breakout"} and before_record:
            before_snapshot = before_record["snapshot"]
        return runner(
            record["snapshot"],
            before_snapshot=before_snapshot,
            screenshot_path=record.get("screenshot_file"),
        )
    if skill_id == "detect_party_changed":
        before_record = records_by_capture_id.get("success_before")
        before_snapshot = before_record["snapshot"] if before_record else None
        return runner(record["snapshot"], before_snapshot=before_snapshot)
    if skill_id == "detect_capsule_success":
        return runner(record, target_species="Pikachu")
    if skill_id in {
        "advance_dialogue",
        "close_menu_or_cancel",
        "recover_to_overworld",
        "walk_local_direction",
    }:
        before_snapshot = paired_before_snapshot(record, records_by_capture_id)
        kwargs = {
            "before_snapshot": before_snapshot,
            "screenshot_path": record.get("screenshot_file"),
        }
        if skill_id == "walk_local_direction":
            kwargs["direction"] = inferred_walk_direction(record, records_by_capture_id)
        return runner(record["snapshot"], **kwargs)
    return runner(record["snapshot"])


def paired_before_snapshot(
    record: dict[str, object],
    records_by_capture_id: dict[str, dict[str, object]],
) -> dict[str, object] | None:
    paired_capture_id = record.get("paired_capture_id")
    if record.get("phase") == "after" and isinstance(paired_capture_id, str):
        paired = records_by_capture_id.get(paired_capture_id)
        if paired:
            return paired["snapshot"]
    return None


def inferred_walk_direction(
    record: dict[str, object],
    records_by_capture_id: dict[str, dict[str, object]],
) -> str | None:
    before_snapshot = paired_before_snapshot(record, records_by_capture_id)
    if before_snapshot is None:
        return None
    before_position = before_snapshot.get("position")
    after_position = record.get("snapshot", {}).get("position")  # type: ignore[union-attr]
    if not isinstance(before_position, dict) or not isinstance(after_position, dict):
        return None
    dx = after_position.get("x", 0) - before_position.get("x", 0)
    dy = after_position.get("y", 0) - before_position.get("y", 0)
    if dx == -1 and dy == 0:
        return "left"
    if dx == 1 and dy == 0:
        return "right"
    if dx == 0 and dy == -1:
        return "up"
    if dx == 0 and dy == 1:
        return "down"
    return None


if __name__ == "__main__":
    raise SystemExit(main())
