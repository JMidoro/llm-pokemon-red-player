from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.segment_supervisor import (  # noqa: E402
    DurableSegmentSupervisor,
    SupervisorConfig,
    SupervisorPaths,
)
from pokemon_player.supervisor_fixture import FixtureSegmentRunner  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ROM-free durable supervisor fixture.")
    parser.add_argument("--supervisor-root", required=True)
    parser.add_argument("--operations-dir", required=True)
    parser.add_argument("--lineage-id", required=True)
    parser.add_argument("--initial-state", required=True)
    parser.add_argument("--segment-seconds", type=float, default=30.0)
    parser.add_argument("--action-seconds", type=float, default=0.25)
    parser.add_argument("--outcome", default="healthy")
    parser.add_argument("--provider-unhealthy", action="store_true")
    parser.add_argument("--max-segments", type=int, default=None)
    parser.add_argument("--min-free-bytes", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    supervisor_root = Path(args.supervisor_root).resolve()
    operations_dir = Path(args.operations_dir).resolve()
    result = DurableSegmentSupervisor(
        SupervisorConfig(
            paths=SupervisorPaths(supervisor_root, args.lineage_id),
            initial_state=Path(args.initial_state).resolve(),
            operations_control_path=operations_dir / "control.json",
            heartbeat_seconds=0.5,
            lease_ttl_seconds=5.0,
            min_free_bytes=max(args.min_free_bytes, 0),
            max_segments=args.max_segments,
        ),
        FixtureSegmentRunner(
            project_root=ROOT,
            operations_dir=operations_dir,
            outcome=args.outcome,
            duration_seconds=max(args.segment_seconds, 0.05),
            action_seconds=max(args.action_seconds, 0.01),
            provider_healthy=not args.provider_unhealthy,
        ),
    ).run()
    print(json.dumps(result, indent=2))
    state = result.get("state") if isinstance(result.get("state"), dict) else {}
    return 0 if state.get("state") in {"paused", "completed", "waiting_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
