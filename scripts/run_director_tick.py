from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.director_gateway import run_browser_director_tick  # noqa: E402


def main() -> int:
    try:
        body = json.loads(sys.stdin.read() or "{}")
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        result = run_browser_director_tick(body, repo_root=ROOT)
        print(json.dumps(result))
        return 0 if result.get("status") != "error" else 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": "director_segment_run_v1",
                    "status": "error",
                    "error": str(exc),
                    "errorCategory": "runtime_startup_error",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
