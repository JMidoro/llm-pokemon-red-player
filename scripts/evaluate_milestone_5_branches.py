from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.early_game_reliability import (  # noqa: E402
    evaluate_deterministic_branches,
    load_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the frozen Milestone 5 deterministic branch evidence."
    )
    parser.add_argument(
        "--manifest",
        default=str(
            ROOT
            / "research"
            / "evals"
            / "early-game-reliability"
            / "deterministic-branches.json"
        ),
    )
    parser.add_argument(
        "--out",
        default=str(
            ROOT
            / "research"
            / "artifacts"
            / "m5-evals"
            / "qualification"
            / "deterministic-branches-summary.json"
        ),
    )
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()

    summary = evaluate_deterministic_branches(
        load_json(Path(args.manifest)), project_root=ROOT
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.require_pass and not summary["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
