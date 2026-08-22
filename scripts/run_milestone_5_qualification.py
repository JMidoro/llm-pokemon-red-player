from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "research" / "evals" / "early-game-reliability" / "frozen-suite.json"


@dataclass(frozen=True)
class QualificationPaths:
    results_root: Path

    @property
    def state(self) -> Path:
        return self.results_root / "qualification-state.json"

    @property
    def lock(self) -> Path:
        return self.results_root / "qualification-orchestrator.lock"

    @property
    def branches(self) -> Path:
        return self.results_root / "deterministic-branches-summary.json"

    @property
    def evaluation(self) -> Path:
        return self.results_root / "evaluation-summary.json"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def update_state(
    paths: QualificationPaths,
    candidate_commit: str,
    **updates: Any,
) -> dict[str, Any]:
    state = load_json(paths.state)
    state.setdefault("schema", "milestone_5_qualification_orchestration_v1")
    state.setdefault("candidateCommit", candidate_commit)
    state.setdefault("startedUtc", utc_now())
    state.update(updates)
    state["pid"] = os.getpid()
    state["pythonExecutable"] = sys.executable
    state["updatedUtc"] = utc_now()
    atomic_write(paths.state, state)
    return state


def verify_candidate(candidate_commit: str) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != candidate_commit:
        raise RuntimeError(f"candidate commit mismatch: expected {candidate_commit}, found {head}")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise RuntimeError("candidate worktree is not clean")


def frozen_cases(suite_path: Path) -> list[tuple[str, str]]:
    suite = load_json(suite_path)
    cases: list[tuple[str, str]] = []
    for lane in ("capsuleA", "cleanBootBoulder"):
        lane_spec = suite.get(lane)
        lane_spec = lane_spec if isinstance(lane_spec, dict) else {}
        for item in lane_spec.get("cases", []):
            if isinstance(item, dict) and item.get("id"):
                cases.append((lane, str(item["id"])))
    if len(cases) != 15:
        raise RuntimeError(f"expected 15 frozen cases, found {len(cases)}")
    return cases


def case_summary(paths: QualificationPaths, case_id: str) -> dict[str, Any]:
    return load_json(paths.results_root / case_id / "case-summary.json")


def case_disposition(
    summary: Mapping[str, Any],
    *,
    case_id: str,
    restart_case: str | None,
) -> str:
    if not summary:
        return "pending"
    status = str(summary.get("status") or "")
    if status == "completed":
        return "completed"
    if status == "infrastructure_abort":
        return "restart" if restart_case == case_id else "infrastructure_abort"
    return "invalid_terminal"


def completed_case_ids(
    paths: QualificationPaths,
    cases: list[tuple[str, str]],
) -> list[str]:
    return [
        case_id
        for _, case_id in cases
        if case_disposition(
            case_summary(paths, case_id),
            case_id=case_id,
            restart_case=None,
        )
        == "completed"
    ]


def run_case(
    paths: QualificationPaths,
    suite_path: Path,
    lane: str,
    case_id: str,
    *,
    restart_infrastructure_abort: bool,
) -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_milestone_5_case.py"),
        "--lane",
        lane,
        "--case-id",
        case_id,
        "--suite",
        str(suite_path),
        "--results-root",
        str(paths.results_root),
    ]
    if restart_infrastructure_abort:
        command.append("--restart-infrastructure-abort")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def evaluate(paths: QualificationPaths, suite_path: Path) -> bool:
    branch_code = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate_milestone_5_branches.py"),
            "--out",
            str(paths.branches),
            "--require-pass",
        ],
        cwd=ROOT,
        check=False,
    ).returncode
    if branch_code != 0:
        raise RuntimeError("deterministic branch gate failed")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "evaluate_early_game_reliability.py"),
            "--suite",
            str(suite_path),
            "--results-root",
            str(paths.results_root),
            "--deterministic-branches",
            str(paths.branches),
            "--out",
            str(paths.evaluation),
        ],
        cwd=ROOT,
        check=True,
    )
    return load_json(paths.evaluation).get("passed") is True


@contextmanager
def exclusive_orchestrator(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    handle.seek(0)
    if handle.read(1) != b"1":
        handle.seek(0)
        handle.write(b"1")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RuntimeError("another qualification orchestrator is active") from exc
    try:
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or resume the frozen local-only Milestone 5 qualification."
    )
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--results-root", required=True)
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--restart-infrastructure-abort", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_commit = str(args.candidate_commit)
    paths = QualificationPaths(Path(args.results_root).resolve())
    suite_path = Path(args.suite).resolve()
    with exclusive_orchestrator(paths.lock):
        try:
            verify_candidate(candidate_commit)
            cases = frozen_cases(suite_path)
            restart_case = args.restart_infrastructure_abort
            if restart_case and restart_case not in {case_id for _, case_id in cases}:
                raise RuntimeError(f"unknown infrastructure-aborted case: {restart_case}")
            update_state(
                paths,
                candidate_commit,
                status="running",
                currentCase=None,
                completedCases=completed_case_ids(paths, cases),
                totalCases=len(cases),
                restartInfrastructureCase=restart_case,
            )
            restart_consumed = False
            for lane, case_id in cases:
                summary = case_summary(paths, case_id)
                disposition = case_disposition(
                    summary,
                    case_id=case_id,
                    restart_case=restart_case,
                )
                if disposition == "completed":
                    continue
                if disposition == "infrastructure_abort":
                    update_state(
                        paths,
                        candidate_commit,
                        status="infrastructure_abort",
                        currentCase=case_id,
                        currentLane=lane,
                        summary="A local-provider infrastructure abort requires diagnosis.",
                    )
                    return 2
                if disposition == "invalid_terminal":
                    update_state(
                        paths,
                        candidate_commit,
                        status="infrastructure_abort",
                        currentCase=case_id,
                        currentLane=lane,
                        lastCaseStatus=summary.get("status"),
                        summary="A non-gameplay terminal case artifact requires diagnosis.",
                    )
                    return 2
                should_restart = disposition == "restart"
                restart_consumed = restart_consumed or should_restart
                update_state(
                    paths,
                    candidate_commit,
                    status="running",
                    currentCase=case_id,
                    currentLane=lane,
                    currentCaseStartedUtc=utc_now(),
                )
                return_code = run_case(
                    paths,
                    suite_path,
                    lane,
                    case_id,
                    restart_infrastructure_abort=should_restart,
                )
                summary = case_summary(paths, case_id)
                update_state(
                    paths,
                    candidate_commit,
                    lastCase=case_id,
                    lastCaseReturnCode=return_code,
                    lastCaseStatus=summary.get("status"),
                    lastCaseSuccess=summary.get("success"),
                    completedCases=completed_case_ids(paths, cases),
                )
                if return_code == 2 or summary.get("status") != "completed":
                    update_state(
                        paths,
                        candidate_commit,
                        status="infrastructure_abort",
                        currentCase=case_id,
                        currentLane=lane,
                        summary="The case did not produce a completed gameplay result.",
                    )
                    return 2
            if restart_case and not restart_consumed:
                raise RuntimeError(
                    "requested infrastructure restart did not match an aborted case"
                )
            completed = completed_case_ids(paths, cases)
            if len(completed) != len(cases):
                raise RuntimeError("qualification reached evaluation with incomplete cases")
            passed = evaluate(paths, suite_path)
            update_state(
                paths,
                candidate_commit,
                status="completed_pass" if passed else "completed_fail",
                currentCase=None,
                completedCases=completed,
                passed=passed,
                evaluationSummary=str(paths.evaluation),
            )
            return 0 if passed else 1
        except Exception as exc:
            update_state(
                paths,
                candidate_commit,
                status="orchestrator_error",
                errorType=exc.__class__.__name__,
                summary=str(exc),
            )
            raise


if __name__ == "__main__":
    raise SystemExit(main())
