from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.directive_model import DirectorContext  # noqa: E402
from pokemon_player.director_client import make_director_client  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a single user directive.")
    parser.add_argument("directive")
    parser.add_argument("--state-summary", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--mode", choices=["auto", "offline", "openai"], default="auto")
    args = parser.parse_args()

    context = DirectorContext(
        state_summary=args.state_summary,
        objective=args.objective,
    )
    decision = make_director_client(args.mode).decide(context, args.directive)
    print(decision.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
