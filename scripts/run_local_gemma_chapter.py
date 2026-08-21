from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Policy helpers remain import-compatible for existing tests and local notebooks.
from scripts.chapter_segment_support import (  # noqa: E402, F401
    apply_chapter_skill_policy,
    default_active_battle_move,
    default_purchase_quantity,
    infer_missing_skill_args,
    normalize_selected_skill,
)
from scripts.run_chapter_segment import main as run_provider_neutral_segment  # noqa: E402


def main() -> int:
    """Pin the canonical chapter segment runner to the local LM Studio adapter."""

    return run_provider_neutral_segment(
        sys.argv[1:],
        forced_provider="lmstudio-chat",
    )


if __name__ == "__main__":
    raise SystemExit(main())
