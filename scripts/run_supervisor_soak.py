from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.durable_io import atomic_write_json, read_json, utc_now  # noqa: E402
from pokemon_player.operations import OperationsPaths, OperationsStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the real-wall-clock Milestone 3 soak gate.")
    parser.add_argument("--duration-seconds", type=float, default=8 * 60 * 60)
    parser.add_argument("--restart-after-seconds", type=float, default=15 * 60)
    parser.add_argument("--segment-seconds", type=float, default=30.0)
    parser.add_argument("--action-seconds", type=float, default=0.25)
    parser.add_argument("--status-seconds", type=float, default=30.0)
    parser.add_argument("--artifact-root", default="research/artifacts/supervisor-soaks")
    parser.add_argument("--run-id", default=None)
    return parser.parse_args()


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def main() -> int:
    args = parse_args()
    started_epoch = time.time()
    started_monotonic = time.monotonic()
    run_id = args.run_id or f"soak-{timestamp()}"
    artifact_root = resolve_path(args.artifact_root)
    run_root = artifact_root / run_id
    supervisor_root = run_root / "supervisor"
    operations_dir = run_root / "operations"
    lineage_id = "eight-hour-soak"
    seed = run_root / "seed.state"
    run_root.mkdir(parents=True, exist_ok=True)
    seed.write_bytes(b"durable-supervisor-soak-seed")
    store = OperationsStore(
        OperationsPaths(
            state_dir=operations_dir,
            report_root=supervisor_root / "lineages" / lineage_id / "segments",
            supervisor_root=supervisor_root,
        )
    )
    store.command("resume", source="soak_harness_start")
    harness = {
        "schema": "supervisor_soak_harness_v1",
        "runId": run_id,
        "lineageId": lineage_id,
        "startedUtc": utc_now(),
        "startedEpoch": started_epoch,
        "requestedDurationSeconds": args.duration_seconds,
        "segmentDurationSeconds": args.segment_seconds,
        "forcedRestart": None,
        "status": "running",
    }
    atomic_write_json(run_root / "harness.json", harness)
    process = start_worker(
        run_root,
        supervisor_root=supervisor_root,
        operations_dir=operations_dir,
        lineage_id=lineage_id,
        seed=seed,
        segment_seconds=args.segment_seconds,
        action_seconds=args.action_seconds,
        generation=1,
    )
    restart_due = started_monotonic + min(
        max(args.restart_after_seconds, 0.1),
        max(args.duration_seconds * 0.8, 0.1),
    )
    deadline = started_monotonic + max(args.duration_seconds, 0.1)
    restarted = False
    generation = 1
    next_status = started_monotonic
    unexpected_exit: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        now = time.monotonic()
        if process.poll() is not None:
            unexpected_exit = {
                "generation": generation,
                "returnCode": process.returncode,
                "detectedUtc": utc_now(),
            }
            break
        if not restarted and now >= restart_due:
            state = latest_state(supervisor_root, lineage_id)
            if not state.get("childPid") or state.get("state") != "running":
                time.sleep(0.1)
                continue
            previous_pid = process.pid
            child_pid = state.get("childPid")
            current_segment = state.get("currentSegment")
            process.terminate()
            process.wait(timeout=15)
            previous_return_code = process.returncode
            child_alive = process_alive(int(child_pid)) if child_pid else False
            generation += 1
            process = start_worker(
                run_root,
                supervisor_root=supervisor_root,
                operations_dir=operations_dir,
                lineage_id=lineage_id,
                seed=seed,
                segment_seconds=args.segment_seconds,
                action_seconds=args.action_seconds,
                generation=generation,
            )
            harness["forcedRestart"] = {
                "createdUtc": utc_now(),
                "previousSupervisorPid": previous_pid,
                "previousReturnCode": previous_return_code,
                "currentSegment": current_segment,
                "childPid": child_pid,
                "childAliveAfterSupervisorTermination": child_alive,
                "replacementSupervisorPid": process.pid,
            }
            atomic_write_json(run_root / "harness.json", harness)
            restarted = True
        if now >= next_status:
            state = latest_state(supervisor_root, lineage_id)
            manifest = latest_manifest(supervisor_root, lineage_id)
            print(
                json.dumps(
                    {
                        "elapsedSeconds": round(now - started_monotonic, 1),
                        "state": state.get("state"),
                        "currentSegment": state.get("currentSegment"),
                        "segments": len(manifest.get("segments", [])),
                        "restartCompleted": restarted,
                    }
                ),
                flush=True,
            )
            next_status = now + max(args.status_seconds, 1.0)
        time.sleep(0.2)

    store.command("stop_after_action", source="soak_harness_deadline")
    if process.poll() is None:
        try:
            process.wait(timeout=max(args.segment_seconds + 30, 30))
        except subprocess.TimeoutExpired:
            store.command("emergency_stop", source="soak_harness_timeout")
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=15)
    ended_epoch = time.time()
    summary = evaluate_soak(
        run_root,
        supervisor_root=supervisor_root,
        lineage_id=lineage_id,
        requested_duration=max(args.duration_seconds, 0.1),
        started_epoch=started_epoch,
        ended_epoch=ended_epoch,
        forced_restart=harness.get("forcedRestart"),
        unexpected_exit=unexpected_exit,
        worker_return_code=process.returncode,
    )
    harness.update(status="passed" if summary["passed"] else "failed", endedUtc=utc_now())
    atomic_write_json(run_root / "harness.json", harness)
    atomic_write_json(run_root / "soak-summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["passed"] else 1


def start_worker(
    run_root: Path,
    *,
    supervisor_root: Path,
    operations_dir: Path,
    lineage_id: str,
    seed: Path,
    segment_seconds: float,
    action_seconds: float,
    generation: int,
) -> subprocess.Popen[str]:
    stdout = (run_root / f"supervisor-{generation}.out.log").open("w", encoding="utf-8")
    stderr = (run_root / f"supervisor-{generation}.err.log").open("w", encoding="utf-8")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_supervisor_fixture.py"),
        "--supervisor-root",
        str(supervisor_root),
        "--operations-dir",
        str(operations_dir),
        "--lineage-id",
        lineage_id,
        "--initial-state",
        str(seed),
        "--segment-seconds",
        str(max(segment_seconds, 0.05)),
        "--action-seconds",
        str(max(action_seconds, 0.01)),
    ]
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        text=True,
        shell=False,
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
    )
    stdout.close()
    stderr.close()
    return process


def evaluate_soak(
    run_root: Path,
    *,
    supervisor_root: Path,
    lineage_id: str,
    requested_duration: float,
    started_epoch: float,
    ended_epoch: float,
    forced_restart: Any,
    unexpected_exit: dict[str, Any] | None,
    worker_return_code: int | None,
) -> dict[str, Any]:
    lineage_root = supervisor_root / "lineages" / lineage_id
    manifest = read_json(lineage_root / "manifest.json") or {}
    final_checkpoint = read_json(lineage_root / "final-checkpoint.json") or {}
    segment_items = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
    segment_ids = [str(item.get("segmentId")) for item in segment_items if isinstance(item, dict)]
    stable_manifests = 0
    machine_reasons = 0
    intervals: list[tuple[float, float, str]] = []
    for segment_id in segment_ids:
        segment_dir = lineage_root / "segments" / segment_id
        segment = read_json(segment_dir / "manifest.json") or {}
        artifacts = segment.get("artifacts") if isinstance(segment.get("artifacts"), dict) else {}
        if artifacts.get("complete") is True:
            stable_manifests += 1
        finish = segment.get("finish") if isinstance(segment.get("finish"), dict) else {}
        if finish.get("stopReason") or (segment.get("checkpoint") or {}).get("verdict"):
            machine_reasons += 1
        process_record = read_json(segment_dir / "fixture-process.json") or {}
        if process_record.get("startedEpoch") and process_record.get("endedEpoch"):
            intervals.append(
                (
                    float(process_record["startedEpoch"]),
                    float(process_record["endedEpoch"]),
                    segment_id,
                )
            )
    intervals.sort()
    overlaps = [
        {"first": before[2], "second": after[2]}
        for before, after in zip(intervals, intervals[1:])
        if after[0] < before[1]
    ]
    elapsed = ended_epoch - started_epoch
    duration_passed = elapsed >= requested_duration
    checks = {
        "wallClockDuration": duration_passed,
        "forcedRestart": bool(
            isinstance(forced_restart, dict)
            and forced_restart.get("childPid")
            and forced_restart.get("childAliveAfterSupervisorTermination") is True
        ),
        "segmentsCompleted": len(segment_ids) > 0,
        "noDuplicateSegmentIds": len(segment_ids) == len(set(segment_ids)),
        "noConcurrentLineageExecution": not overlaps,
        "stableArtifactManifests": stable_manifests == len(segment_ids),
        "machineReadableSegmentReasons": machine_reasons == len(segment_ids),
        "stableFinalCheckpoint": bool(final_checkpoint.get("stable")),
        "expectedWorkerExit": unexpected_exit is None and worker_return_code == 0,
    }
    return {
        "schema": "supervisor_soak_summary_v1",
        "runId": run_root.name,
        "lineageId": lineage_id,
        "createdUtc": utc_now(),
        "requestedDurationSeconds": requested_duration,
        "elapsedWallSeconds": round(elapsed, 3),
        "segmentCount": len(segment_ids),
        "stableManifestCount": stable_manifests,
        "machineReasonCount": machine_reasons,
        "overlaps": overlaps,
        "forcedRestart": forced_restart,
        "unexpectedExit": unexpected_exit,
        "workerReturnCode": worker_return_code,
        "finalCheckpoint": final_checkpoint,
        "checks": checks,
        "passed": all(checks.values()),
    }


def latest_state(supervisor_root: Path, lineage_id: str) -> dict[str, Any]:
    return read_json(supervisor_root / "lineages" / lineage_id / "state.json") or {}


def latest_manifest(supervisor_root: Path, lineage_id: str) -> dict[str, Any]:
    return read_json(supervisor_root / "lineages" / lineage_id / "manifest.json") or {}


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


if __name__ == "__main__":
    raise SystemExit(main())
