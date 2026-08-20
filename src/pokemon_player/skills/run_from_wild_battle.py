from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.skill_result import SkillResult


SKILL_ID = "run_from_wild_battle"
WILD_BATTLE_TYPE = 1


def run_from_wild_battle(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    del screenshot_path
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    evidence = [f"mode={mode}", f"battle_type_raw={battle_type_raw}"]

    if before_snapshot is not None:
        before_mode = str(before_snapshot.get("mode", "unknown"))
        before_battle_type = before_snapshot.get("battle_type_raw")
        evidence.extend(
            [
                f"before_mode={before_mode}",
                f"before_battle_type_raw={before_battle_type}",
            ]
        )
        if before_mode == "battle" and before_battle_type == WILD_BATTLE_TYPE:
            if mode == "overworld" and battle_type_raw == 0:
                return SkillResult(
                    skill_id=SKILL_ID,
                    status="succeeded",
                    summary="Escaped the wild battle and returned to overworld.",
                    evidence=tuple(evidence),
                    warnings=warnings,
                )
            if mode == "battle" and battle_type_raw == WILD_BATTLE_TYPE:
                return SkillResult(
                    skill_id=SKILL_ID,
                    status="failed",
                    summary="Run attempt did not escape; wild battle is still active.",
                    evidence=tuple(evidence),
                    warnings=warnings,
                )

    if mode == "battle" and battle_type_raw == WILD_BATTLE_TYPE:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Wild battle is active and can attempt to run.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    if mode == "battle":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="A non-wild battle is active; running is not supported.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="blocked",
        summary="No wild battle is active.",
        evidence=tuple(evidence),
        warnings=warnings,
    )
