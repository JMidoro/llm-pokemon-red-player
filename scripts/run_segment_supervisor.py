from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.config import load_dotenv  # noqa: E402
from pokemon_player.segment_supervisor import (  # noqa: E402
    DurableSegmentSupervisor,
    SubprocessSegmentRunner,
    SupervisorConfig,
    SupervisorPaths,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Supervise provider-neutral Pokemon Player segments from one safe save lineage."
    )
    parser.add_argument("--lineage-id", required=True)
    parser.add_argument(
        "--supervisor-root",
        default="research/artifacts/segment-supervisor",
    )
    parser.add_argument(
        "--initial-state",
        default=None,
        help="Required only when creating a new lineage; restarts use the manifest's last safe state.",
    )
    parser.add_argument(
        "--provider",
        choices=("lmstudio-chat", "openai-responses", "replay"),
        default="lmstudio-chat",
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--replay-path", default=None)
    parser.add_argument("--goal", default=None)
    parser.add_argument("--max-actions", type=int, default=100)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional first inference seed; segment/action offsets are deterministic.",
    )
    parser.add_argument(
        "--fresh-start",
        action="store_true",
        help="Use clean RAM for the first segment of a new lineage.",
    )
    parser.add_argument(
        "--success-target",
        choices=("chapter", "capsule-a"),
        default="chapter",
    )
    parser.add_argument("--request-timeout-seconds", type=int, default=180)
    parser.add_argument("--max-segments", type=int, default=None)
    parser.add_argument("--heartbeat-seconds", type=float, default=5.0)
    parser.add_argument("--lease-ttl-seconds", type=float, default=30.0)
    parser.add_argument("--min-free-mb", type=int, default=1024)
    parser.add_argument("--no-image", action="store_true")
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--video-output-dir", default="D:/Dropbox")
    parser.add_argument(
        "--operations-dir",
        default="research/artifacts/operations",
    )
    parser.add_argument(
        "--ruleset",
        default="research/rulesets/stream-nuzlocke-v1.json",
        help="Versioned ruleset shared by every segment in this lineage.",
    )
    parser.add_argument(
        "--require-review-before-provisional",
        action="store_true",
        help="Queue provisional checkpoints but do not continue them automatically.",
    )
    return parser.parse_args()


def resolve_project_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env")
    supervisor_root = resolve_project_path(args.supervisor_root)
    operations_dir = resolve_project_path(args.operations_dir)
    assert supervisor_root is not None and operations_dir is not None
    paths = SupervisorPaths(supervisor_root, args.lineage_id)
    runner = SubprocessSegmentRunner(
        project_root=ROOT,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        replay_path=resolve_project_path(args.replay_path),
        goal=args.goal,
        max_actions=max(args.max_actions, 1),
        max_tokens=max(args.max_tokens, 1),
        reasoning_effort=args.reasoning_effort,
        temperature=args.temperature,
        first_inference_seed=args.seed,
        fresh_start_first_segment=args.fresh_start,
        request_timeout_seconds=max(args.request_timeout_seconds, 1),
        no_image=args.no_image,
        no_video=args.no_video,
        video_output_dir=resolve_project_path(args.video_output_dir),
        operations_dir=operations_dir,
        extra_args=(
            "--ruleset",
            str(resolve_project_path(args.ruleset)),
            "--nuzlocke-ledger",
            str(paths.lineage_root / "nuzlocke" / "ledger.json"),
            "--lineage-id",
            args.lineage_id,
            "--success-target",
            args.success_target,
        ),
    )
    supervisor = DurableSegmentSupervisor(
        SupervisorConfig(
            paths=paths,
            initial_state=resolve_project_path(args.initial_state),
            operations_control_path=operations_dir / "control.json",
            allow_provisional_continue=not args.require_review_before_provisional,
            heartbeat_seconds=max(args.heartbeat_seconds, 0.05),
            lease_ttl_seconds=max(args.lease_ttl_seconds, 1.0),
            min_free_bytes=max(args.min_free_mb, 0) * 1024 * 1024,
            max_segments=max(args.max_segments, 1) if args.max_segments is not None else None,
        ),
        runner,
    )
    result = supervisor.run()
    print(json.dumps(result, indent=2))
    state = result.get("state") if isinstance(result.get("state"), dict) else {}
    return 0 if state.get("state") in {"paused", "completed", "waiting_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
