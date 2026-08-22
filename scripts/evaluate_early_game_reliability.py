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
    evaluate_suite,
    load_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score the frozen Milestone 5 early-game reliability suite."
    )
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
    parser.add_argument("--deterministic-branches", default=None)
    parser.add_argument(
        "--out",
        default=str(
            ROOT
            / "research"
            / "artifacts"
            / "m5-evals"
            / "qualification"
            / "evaluation-summary.json"
        ),
    )
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()

    suite = load_json(Path(args.suite))
    branches = (
        load_json(Path(args.deterministic_branches))
        if args.deterministic_branches
        else None
    )
    summary = evaluate_suite(
        suite,
        results_root=Path(args.results_root),
        project_root=ROOT,
        deterministic_branches=branches,
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.require_pass and not summary["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
