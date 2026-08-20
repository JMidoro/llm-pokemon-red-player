from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.promotion_evidence_io import (  # noqa: E402
    PROMOTION_EVIDENCE_SCHEMA,
    evaluate_assertions,
)


EVIDENCE_ROOT = ROOT / "research" / "promotions" / "evidence"


def evidence_paths(args: argparse.Namespace) -> list[Path]:
    if args.metadata:
        return [Path(path) for path in args.metadata]
    if args.promotion:
        return sorted((EVIDENCE_ROOT / args.promotion).glob("*.promotion-evidence.json"))
    return sorted(EVIDENCE_ROOT.glob("*/*.promotion-evidence.json"))


def validate_one(metadata_path: Path) -> dict:
    record = json.loads(metadata_path.read_text(encoding="utf-8"))
    if record.get("schema") != PROMOTION_EVIDENCE_SCHEMA:
        raise ValueError(f"{metadata_path} is not a {PROMOTION_EVIDENCE_SCHEMA} record.")
    results = evaluate_assertions(record)
    status = "not_asserted"
    if results:
        status = "passed" if all(result["passed"] for result in results) else "failed"
    return {
        "metadata_path": str(metadata_path),
        "promotion_id": record.get("promotion_id"),
        "evidence_id": record.get("evidence_id"),
        "label": record.get("label"),
        "status": status,
        "results": results,
    }


def print_text_report(results: list[dict]) -> None:
    for item in results:
        print(f"{item['status'].upper()} {item['promotion_id']} / {item['evidence_id']} - {item['label']}")
        if not item["results"]:
            print("  no assertions recorded")
        for result in item["results"]:
            marker = "PASS" if result["passed"] else "FAIL"
            print(
                f"  {marker} {result['id']}: actual={result['actual']!r} "
                f"op={result['op']} expected={result['expected']!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate promotion evidence assertions.")
    parser.add_argument("metadata", nargs="*", help="Specific promotion evidence metadata JSON files.")
    parser.add_argument("--promotion", help="Promotion id subdirectory under research/promotions/evidence.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    results = [validate_one(path) for path in evidence_paths(args)]
    if args.json:
        print(json.dumps({"schema": "promotion_evidence_validation_v1", "results": results}, indent=2))
    else:
        print_text_report(results)

    return 1 if any(item["status"] == "failed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
