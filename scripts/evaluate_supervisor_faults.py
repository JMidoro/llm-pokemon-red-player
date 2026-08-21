from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.durable_io import atomic_write_json, read_json, utc_now  # noqa: E402
from pokemon_player.operations import OperationsPaths, OperationsStore  # noqa: E402
from pokemon_player.segment_supervisor import (  # noqa: E402
    DurableSegmentSupervisor,
    LeaseBusyError,
    LineageLease,
    SupervisorConfig,
    SupervisorPaths,
)
from pokemon_player.supervisor_fixture import FixtureSegmentRunner  # noqa: E402


DIAGNOSTIC_OUTCOMES = ("stalled", "state_gap", "unsafe", "model_error", "missing_report")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Milestone 3 supervisor fault handling.")
    parser.add_argument("--samples-per-outcome", type=int, default=4)
    parser.add_argument("--artifact-root", default="research/artifacts/supervisor-fault-evals")
    parser.add_argument("--run-id", default=None)
    return parser.parse_args()


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def main() -> int:
    args = parse_args()
    run_id = args.run_id or f"fault-eval-{timestamp()}"
    root = resolve_path(args.artifact_root) / run_id
    root.mkdir(parents=True, exist_ok=True)
    cases: list[dict[str, Any]] = []
    sampled: list[dict[str, Any]] = []
    for outcome in DIAGNOSTIC_OUTCOMES:
        for sample_index in range(1, max(args.samples_per_outcome, 1) + 1):
            case = run_diagnostic_case(root, outcome, sample_index)
            cases.append(case)
            sampled.extend(case["diagnosticSegments"])
    resilience = {
        "staleLease": run_stale_lease_case(root),
        "diskPressure": run_disk_pressure_case(root),
        "partialStateWrite": run_partial_state_case(root),
        "concurrentLease": run_concurrent_lease_case(root),
    }
    diagnosable = sum(1 for item in sampled if item.get("diagnosable") is True)
    rate = diagnosable / max(len(sampled), 1)
    checks = {
        "diagnosticSamplePresent": bool(sampled),
        "diagnosableRateAtLeast95Percent": rate >= 0.95,
        "staleLeaseRecovered": resilience["staleLease"]["passed"],
        "diskPressureStoppedSafely": resilience["diskPressure"]["passed"],
        "partialStateRecovered": resilience["partialStateWrite"]["passed"],
        "concurrentLeaseRejected": resilience["concurrentLease"]["passed"],
    }
    summary = {
        "schema": "supervisor_fault_evaluation_v1",
        "runId": run_id,
        "createdUtc": utc_now(),
        "sampleCount": len(sampled),
        "diagnosableCount": diagnosable,
        "diagnosableRate": round(rate, 4),
        "targetRate": 0.95,
        "cases": cases,
        "resilience": resilience,
        "checks": checks,
        "passed": all(checks.values()),
    }
    atomic_write_json(root / "fault-evaluation-summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


def run_diagnostic_case(root: Path, outcome: str, index: int) -> dict[str, Any]:
    case_id = f"{outcome}-{index:02d}"
    case_root = root / "cases" / case_id
    seed = case_root / "seed.state"
    seed.parent.mkdir(parents=True, exist_ok=True)
    seed.write_bytes(f"seed-{case_id}".encode())
    supervisor_root = case_root / "supervisor"
    operations_dir = case_root / "operations"
    paths = SupervisorPaths(supervisor_root, case_id)
    store = OperationsStore(
        OperationsPaths(
            state_dir=operations_dir,
            report_root=paths.segments,
            supervisor_root=supervisor_root,
        )
    )
    store.command("resume", source="fault_evaluation")
    result = DurableSegmentSupervisor(
        SupervisorConfig(
            paths=paths,
            initial_state=seed,
            operations_control_path=operations_dir / "control.json",
            heartbeat_seconds=0.05,
            lease_ttl_seconds=2,
            min_free_bytes=0,
            max_segments=None,
        ),
        FixtureSegmentRunner(
            project_root=ROOT,
            operations_dir=operations_dir,
            outcome=outcome,
            duration_seconds=0.14,
            action_seconds=0.01,
            poll_seconds=0.02,
        ),
    ).run()
    diagnostic_segments: list[dict[str, Any]] = []
    manifest = result["manifest"]
    for item in manifest.get("segments", []):
        if not isinstance(item, dict):
            continue
        segment = read_json(paths.lineage_root / str(item.get("manifestPath"))) or {}
        diagnostic = (
            segment.get("diagnostic") if isinstance(segment.get("diagnostic"), dict) else {}
        )
        if diagnostic.get("needsDiagnosis") is True:
            diagnostic_segments.append(
                {
                    "caseId": case_id,
                    "segmentId": segment.get("segmentId"),
                    "verdict": (segment.get("checkpoint") or {}).get("verdict"),
                    "diagnosable": diagnostic.get("diagnosable") is True,
                    "manifestPath": str(
                        (paths.lineage_root / str(item.get("manifestPath"))).resolve()
                    ),
                }
            )
    return {
        "caseId": case_id,
        "outcome": outcome,
        "supervisorState": result["state"]["state"],
        "machineReason": result["checkpoint"]["machineReason"],
        "stableFinalCheckpoint": result["checkpoint"]["stable"],
        "diagnosticSegments": diagnostic_segments,
    }


def run_stale_lease_case(root: Path) -> dict[str, Any]:
    case_root = root / "resilience" / "stale-lease"
    seed = prepare_seed(case_root)
    paths = SupervisorPaths(case_root / "supervisor", "stale-lease")
    paths.lineage_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        paths.lease_record,
        {
            "schema": "segment_supervisor_lease_v1",
            "ownerId": "crashed-owner",
            "pid": 99999999,
            "expiresUtc": "2000-01-01T00:00:00+00:00",
        },
    )
    result = DurableSegmentSupervisor(
        SupervisorConfig(paths=paths, initial_state=seed, min_free_bytes=0, max_segments=0),
        FixtureSegmentRunner(ROOT, case_root / "operations"),
    ).run()
    return {"passed": result["state"]["state"] == "completed", "state": result["state"]}


def run_disk_pressure_case(root: Path) -> dict[str, Any]:
    case_root = root / "resilience" / "disk-pressure"
    seed = prepare_seed(case_root)
    paths = SupervisorPaths(case_root / "supervisor", "disk-pressure")
    result = DurableSegmentSupervisor(
        SupervisorConfig(
            paths=paths,
            initial_state=seed,
            min_free_bytes=10**30,
            max_segments=None,
        ),
        FixtureSegmentRunner(ROOT, case_root / "operations"),
    ).run()
    passed = (
        result["state"]["state"] == "failed"
        and result["checkpoint"]["machineReason"] == "insufficient_disk_space"
        and result["checkpoint"]["stable"] is True
    )
    return {"passed": passed, "state": result["state"], "checkpoint": result["checkpoint"]}


def run_partial_state_case(root: Path) -> dict[str, Any]:
    case_root = root / "resilience" / "partial-state"
    seed = prepare_seed(case_root)
    paths = SupervisorPaths(case_root / "supervisor", "partial-state")
    paths.lineage_root.mkdir(parents=True, exist_ok=True)
    paths.state.write_text('{"schema":', encoding="utf-8")
    result = DurableSegmentSupervisor(
        SupervisorConfig(paths=paths, initial_state=seed, min_free_bytes=0, max_segments=0),
        FixtureSegmentRunner(ROOT, case_root / "operations"),
    ).run()
    return {
        "passed": result["state"]["state"] == "completed" and read_json(paths.state) is not None,
        "state": result["state"],
    }


def run_concurrent_lease_case(root: Path) -> dict[str, Any]:
    paths = SupervisorPaths(root / "resilience" / "concurrent-lease", "same-lineage")
    first = LineageLease(paths, "first", ttl_seconds=1)
    second = LineageLease(paths, "second", ttl_seconds=1)
    first.acquire()
    rejected = False
    try:
        try:
            second.acquire()
        except LeaseBusyError:
            rejected = True
    finally:
        first.release()
    return {"passed": rejected, "secondLeaseRejected": rejected}


def prepare_seed(case_root: Path) -> Path:
    case_root.mkdir(parents=True, exist_ok=True)
    seed = case_root / "seed.state"
    seed.write_bytes(b"fault-evaluation-seed")
    return seed


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


if __name__ == "__main__":
    raise SystemExit(main())
