from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.config import load_dotenv  # noqa: E402
from pokemon_player.durable_io import atomic_write_json  # noqa: E402
from pokemon_player.early_game_reliability import (  # noqa: E402
    evaluate_case,
    load_json,
    validate_frozen_suite,
)
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.segment_supervisor import (  # noqa: E402
    DurableSegmentSupervisor,
    SubprocessSegmentRunner,
    SupervisorConfig,
    SupervisorPaths,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one frozen Milestone 5 case with local LM Studio inference."
    )
    parser.add_argument("--lane", choices=("capsuleA", "cleanBootBoulder"), required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--suite",
        default=str(
            ROOT / "research" / "evals" / "early-game-reliability" / "frozen-suite.json"
        ),
    )
    parser.add_argument(
        "--results-root",
        default=str(ROOT / "research" / "artifacts" / "m5-evals" / "qualification"),
    )
    parser.add_argument("--rom", default=None)
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--max-actions", type=int, default=50)
    parser.add_argument("--max-segments", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--request-timeout-seconds", type=int, default=180)
    parser.add_argument("--with-video", action="store_true")
    parser.add_argument(
        "--restart-infrastructure-abort",
        action="store_true",
        help=(
            "Archive a completed infrastructure-aborted attempt and rerun the "
            "frozen case from its original start."
        ),
    )
    args = parser.parse_args()

    suite_path = Path(args.suite).resolve()
    suite = load_json(suite_path)
    issues = validate_frozen_suite(suite, ROOT)
    if issues:
        print(json.dumps({"status": "invalid_suite", "issues": issues}, indent=2))
        return 2
    lane_spec = suite.get(args.lane)
    lane_spec = lane_spec if isinstance(lane_spec, dict) else {}
    case = next(
        (
            item
            for item in lane_spec.get("cases", [])
            if isinstance(item, dict) and item.get("id") == args.case_id
        ),
        None,
    )
    if case is None:
        print(f"Frozen case not found in {args.lane}: {args.case_id}")
        return 2

    try:
        tested_commit = clean_tested_commit(ROOT)
    except RuntimeError as exc:
        print(json.dumps({"status": "invalid_worktree", "summary": str(exc)}, indent=2))
        return 2
    env_file = (
        Path(args.env_file).resolve()
        if args.env_file
        else resolve_repository_file(ROOT, Path(".env"))
    )
    load_dotenv(env_file)
    provider_profile = suite["providerProfile"]
    if provider_profile.get("provider") != "lmstudio-chat":
        raise RuntimeError("Milestone 5 case runner refuses non-local providers.")

    results_root = Path(args.results_root).resolve()
    case_root = results_root / args.case_id
    restart_existing, disposition_error = existing_case_disposition(
        case_root,
        restart_infrastructure_abort=args.restart_infrastructure_abort,
    )
    if disposition_error:
        print(json.dumps(disposition_error, indent=2))
        return 2
    lineage_root = case_root / "supervisor" / args.case_id
    metadata_path = case_root / "case-metadata.json"
    first_seed = int(case["firstInferenceSeed"])

    initial_state, fresh_start, success_target = case_configuration(
        args.lane,
        lane_spec,
        case,
    )
    ruleset = (ROOT / str(lane_spec["ruleset"])).resolve()
    rom = (
        Path(args.rom).resolve()
        if args.rom
        else resolve_repository_file(ROOT, Path("research") / "PokemonRed.gb")
    )
    if not rom.is_file():
        print(json.dumps({"status": "missing_rom", "path": str(rom)}, indent=2))
        return 2
    rom_fingerprint = fingerprint_rom(rom)
    expected_rom = suite["romProfile"]
    rom_mismatches = [
        key
        for key, actual in (
            ("title", rom_fingerprint.title),
            ("sizeBytes", rom_fingerprint.size_bytes),
            ("sha256", rom_fingerprint.sha256),
        )
        if actual != expected_rom.get(key)
    ]
    if rom_mismatches:
        print(
            json.dumps(
                {"status": "rom_mismatch", "mismatches": rom_mismatches},
                indent=2,
            )
        )
        return 2
    operations_dir = case_root / "operations"
    paths = SupervisorPaths(case_root / "supervisor", args.case_id)
    runner = SubprocessSegmentRunner(
        project_root=ROOT,
        provider="lmstudio-chat",
        model=str(provider_profile["model"]),
        base_url=args.base_url,
        max_actions=max(args.max_actions, 1),
        max_tokens=max(args.max_tokens, 1),
        reasoning_effort="low",
        temperature=float(provider_profile["temperature"]),
        first_inference_seed=first_seed,
        fresh_start_first_segment=fresh_start,
        request_timeout_seconds=max(args.request_timeout_seconds, 1),
        no_image=False,
        no_video=not args.with_video,
        video_output_dir=case_root / "videos",
        operations_dir=operations_dir,
        extra_args=(
            "--rom",
            str(rom),
            "--ruleset",
            str(ruleset),
            "--nuzlocke-ledger",
            str(lineage_root / "nuzlocke" / "ledger.json"),
            "--lineage-id",
            args.case_id,
            "--success-target",
            success_target,
        ),
    )
    health = runner.health_check()
    if health.get("healthy") is not True:
        case_root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(case_root / "provider-health.json", health)
        print(json.dumps({"status": "provider_unavailable", "health": health}, indent=2))
        return 2
    if restart_existing:
        archive_infrastructure_abort(case_root, results_root)
    case_root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(case_root / "provider-health.json", health)

    metadata = {
        "schema": "milestone_5_case_metadata_v1",
        "caseId": args.case_id,
        "lane": args.lane,
        "suitePath": str(suite_path),
        "suiteFrozenAtUtc": suite.get("frozenAtUtc"),
        "testedCommit": tested_commit,
        "provider": "lmstudio-chat",
        "model": provider_profile["model"],
        "temperature": provider_profile["temperature"],
        "firstInferenceSeed": first_seed,
        "humanGameplayInterventions": 0,
        "romSha256": rom_fingerprint.sha256,
        "startedUtc": datetime.now(UTC).isoformat(),
    }
    if metadata_path.is_file():
        existing = load_json(metadata_path)
        immutable_keys = (
            "caseId",
            "lane",
            "suiteFrozenAtUtc",
            "testedCommit",
            "provider",
            "model",
            "temperature",
            "firstInferenceSeed",
            "romSha256",
        )
        mismatches = [
            key for key in immutable_keys if existing.get(key) != metadata.get(key)
        ]
        if mismatches:
            print(
                json.dumps(
                    {
                        "status": "case_identity_mismatch",
                        "mismatches": mismatches,
                        "caseRoot": str(case_root),
                    },
                    indent=2,
                )
            )
            return 2
        metadata = existing
    else:
        atomic_write_json(metadata_path, metadata)

    default_segments = 8 if args.lane == "capsuleA" else 40
    supervisor = DurableSegmentSupervisor(
        SupervisorConfig(
            paths=paths,
            initial_state=initial_state,
            operations_control_path=operations_dir / "control.json",
            allow_provisional_continue=True,
            heartbeat_seconds=5.0,
            lease_ttl_seconds=30.0,
            min_free_bytes=1024 * 1024 * 1024,
            max_segments=max(args.max_segments or default_segments, 1),
        ),
        runner,
    )
    supervisor_result = supervisor.run()
    atomic_write_json(case_root / "supervisor-result.json", supervisor_result)
    case_summary = evaluate_case(
        lane=args.lane,
        case=case,
        case_root=case_root,
        project_root=ROOT,
        provider_profile=provider_profile,
        rom_profile=expected_rom,
    )
    case_summary["completedUtc"] = datetime.now(UTC).isoformat()
    atomic_write_json(case_root / "case-summary.json", case_summary)
    print(json.dumps(case_summary, indent=2, sort_keys=True))
    if case_summary["status"] == "infrastructure_abort":
        return 2
    return 0 if case_summary["success"] else 1


def clean_tested_commit(root: Path) -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise RuntimeError(
            "Frozen Milestone 5 cases require a clean worktree and fixed commit."
        )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def resolve_repository_file(root: Path, relative: Path) -> Path:
    local = (root / relative).resolve()
    if local.is_file():
        return local
    common_dir = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    common_path = Path(common_dir)
    if not common_path.is_absolute():
        common_path = (root / common_path).resolve()
    return (common_path.parent / relative).resolve()


def existing_case_disposition(
    case_root: Path, *, restart_infrastructure_abort: bool
) -> tuple[bool, dict[str, Any] | None]:
    summary_path = case_root / "case-summary.json"
    if not summary_path.is_file():
        if restart_infrastructure_abort:
            return False, {
                "status": "restart_not_applicable",
                "summary": "No completed infrastructure-aborted attempt exists.",
                "caseRoot": str(case_root),
            }
        return False, None
    summary = load_json(summary_path)
    if restart_infrastructure_abort and summary.get("status") == "infrastructure_abort":
        return True, None
    return False, {
        "status": "case_already_finished",
        "caseStatus": summary.get("status"),
        "success": summary.get("success"),
        "caseRoot": str(case_root),
    }


def archive_infrastructure_abort(case_root: Path, results_root: Path) -> Path:
    archive_root = results_root / "aborted-attempts"
    archive_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = archive_root / f"{case_root.name}-{timestamp}"
    case_root.replace(destination)
    return destination


def case_configuration(
    lane: str,
    lane_spec: dict[str, Any],
    case: dict[str, Any],
) -> tuple[Path, bool, str]:
    if lane == "capsuleA":
        return (ROOT / str(case["statePath"])).resolve(), False, "capsule-a"
    bootstrap = lane_spec.get("bootstrapStatePath")
    if not bootstrap:
        raise RuntimeError("Clean-boot lane is missing bootstrapStatePath.")
    return resolve_repository_file(ROOT, Path(str(bootstrap))), True, "chapter"


if __name__ == "__main__":
    raise SystemExit(main())
