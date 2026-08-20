from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.generated_state_io import default_report_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark a generated state report approved or rejected.")
    parser.add_argument("state", help="Generated .state file")
    parser.add_argument("--status", choices=["approved", "rejected"], required=True)
    parser.add_argument("--by", default="Joey")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    report_path = default_report_path(args.state)
    record = json.loads(report_path.read_text(encoding="utf-8"))
    record["approval"] = {
        "status": args.status,
        "approved_by": args.by,
        "approved_at": datetime.now(UTC).isoformat(),
        "notes": args.notes,
    }
    report_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Updated {report_path}")
    print(f"Status: {args.status}")
    if record.get("goal"):
        print(f"Goal: {record['goal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
