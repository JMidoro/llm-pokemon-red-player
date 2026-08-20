from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "research" / "artifacts" / "directive-evals" / "latest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a saved directive eval report.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--case-id", help="Print one case record as JSON.")
    parser.add_argument("--failures", action="store_true", help="Print failed case records as JSON.")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    if report.get("schema") != "directive_eval_report_v1":
        raise ValueError(f"{args.report} is not a directive_eval_report_v1 file.")

    if args.case_id:
        return print_case(report, args.case_id)
    if args.failures:
        failures = [case for case in report["cases"] if not case["matches"]["label"]]
        print(json.dumps(failures, indent=2, sort_keys=True))
        return 1 if failures else 0

    metrics = report["metrics"]
    print(f"Report: {args.report}")
    print(f"Created: {report['created_utc']}")
    print(f"Mode: {report['mode']}")
    print(f"Cases: {metrics['total_cases']}")
    print(f"Passed: {metrics['passed_cases']}")
    print(f"Failed: {metrics['failed_cases']}")
    print(f"Errors: {metrics['errored_cases']}")
    print(f"Label accuracy: {metrics['label_accuracy']:.2%}")
    print(f"Accepted destructive: {metrics['accepted_destructive_count']}")
    print(f"Accepted compilation rate: {metrics['accepted_compilation_rate']:.2%}")
    print(f"Explanation present rate: {metrics['explanation_present_rate']:.2%}")
    print("KPIs:")
    for key, value in report["kpis"].items():
        if key == "overall_passed":
            continue
        status = "pass" if value["passed"] else "gap"
        print(f"- {key}: {status} ({value['actual']} / target {value['target']})")
    if metrics["failure_ids"]:
        print(f"Failures: {', '.join(metrics['failure_ids'])}")
    return 0


def print_case(report: dict, case_id: str) -> int:
    for case in report["cases"]:
        if case["id"] == case_id:
            print(json.dumps(case, indent=2, sort_keys=True))
            return 0 if case["matches"]["label"] else 1
    raise ValueError(f"Case {case_id!r} was not found in report.")


if __name__ == "__main__":
    raise SystemExit(main())
