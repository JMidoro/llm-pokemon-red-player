from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.directive_eval import (  # noqa: E402
    DirectiveEvalThresholds,
    evaluate_directive_deck,
    write_eval_report,
)
from pokemon_player.director_client import make_director_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a directive deck.")
    parser.add_argument("--deck", default=str(ROOT / "research" / "directives" / "v0_directive_deck.json"))
    parser.add_argument("--mode", choices=["auto", "offline", "openai"], default="offline")
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "research" / "artifacts" / "directive-evals"),
        help="Directory for timestamped eval reports.",
    )
    parser.add_argument("--no-save", action="store_true", help="Do not write an eval report.")
    parser.add_argument(
        "--no-latest",
        action="store_true",
        help="Do not update latest.json when writing a report.",
    )
    parser.add_argument("--target-case-count", type=int, default=100)
    parser.add_argument("--target-label-accuracy", type=float, default=0.90)
    parser.add_argument("--target-accepted-compilation-rate", type=float, default=0.90)
    parser.add_argument("--target-explanation-rate", type=float, default=0.90)
    parser.add_argument(
        "--max-accepted-destructive",
        type=int,
        default=0,
        help="Maximum allowed accepted destructive directives.",
    )
    parser.add_argument(
        "--fail-on-kpi",
        action="store_true",
        help="Exit nonzero when any KPI gate fails, including the 100-case target.",
    )
    args = parser.parse_args()

    deck = json.loads(Path(args.deck).read_text(encoding="utf-8"))
    client = make_director_client(args.mode)
    thresholds = DirectiveEvalThresholds(
        target_case_count=args.target_case_count,
        target_label_accuracy=args.target_label_accuracy,
        max_accepted_destructive=args.max_accepted_destructive,
        target_accepted_compilation_rate=args.target_accepted_compilation_rate,
        target_explanation_rate=args.target_explanation_rate,
    )
    report = evaluate_directive_deck(
        deck=deck,
        client=client,
        mode=args.mode,
        deck_path=args.deck,
        thresholds=thresholds,
    )
    metrics = report["metrics"]

    print(f"Deck: {args.deck}")
    print(f"Cases: {metrics['total_cases']}")
    print(f"Passed: {metrics['passed_cases']}")
    print(f"Failed: {metrics['failed_cases']}")
    print(f"Errors: {metrics['errored_cases']}")
    print(f"Label accuracy: {metrics['label_accuracy']:.2%}")
    print(f"Accepted destructive: {metrics['accepted_destructive_count']}")
    print(f"Accepted compilation rate: {metrics['accepted_compilation_rate']:.2%}")
    print(f"Explanation present rate: {metrics['explanation_present_rate']:.2%}")

    if not args.no_save:
        report_path = write_eval_report(report, args.out_dir, latest=not args.no_latest)
        print(f"Report: {report_path}")
        if not args.no_latest:
            print(f"Latest: {Path(args.out_dir) / 'latest.json'}")

    failed_kpis = [
        key
        for key, value in report["kpis"].items()
        if key != "overall_passed" and not value["passed"]
    ]
    if failed_kpis:
        print(f"KPI gaps: {', '.join(failed_kpis)}")

    if metrics["failure_ids"]:
        print(json.dumps({"failure_ids": metrics["failure_ids"]}, indent=2))
    if metrics["failed_cases"] or metrics["errored_cases"]:
        return 1
    if args.fail_on_kpi and not report["kpis"]["overall_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
