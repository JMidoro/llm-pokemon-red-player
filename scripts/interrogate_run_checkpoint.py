from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.run_interrogation import interrogate_run_report, load_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a Director segment checkpoint.")
    parser.add_argument("report", help="Path to a director_segment_run_v1 report.json")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write checkpoint.json next to the report and merge the checkpoint into report.json.",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    report = load_report(report_path)
    checkpoint = interrogate_run_report(report)

    if args.write:
        checkpoint_path = report_path.with_name("checkpoint.json")
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
        report["checkpoint"] = checkpoint
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(checkpoint, indent=2))
    return 0 if checkpoint.get("verdict") not in {"unsafe_state", "model_error"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

