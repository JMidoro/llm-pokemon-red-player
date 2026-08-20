from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.battle_ui import inspect_battle_ui_screenshot
from pokemon_player.skill_result import SkillResult


SKILL_ID = "advance_battle_dialogue"
WILD_BATTLE_TYPE = 1


def advance_battle_dialogue(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    ui_kind = battle_ui_kind(screenshot_path)
    evidence = (
        f"mode={mode}",
        f"battle_type_raw={battle_type_raw}",
        f"battle_ui={ui_kind}",
    )

    if before_snapshot is not None:
        before_mode = str(before_snapshot.get("mode", "unknown"))
        before_battle_type = before_snapshot.get("battle_type_raw")
        evidence = evidence + (
            f"before_mode={before_mode}",
            f"before_battle_type_raw={before_battle_type}",
        )
        if before_mode == "battle" and before_battle_type not in {None, 0}:
            if mode != "battle" or battle_type_raw in {None, 0}:
                return SkillResult(
                    skill_id=SKILL_ID,
                    status="succeeded",
                    summary="Battle dialogue advanced until the battle ended or yielded control.",
                    evidence=evidence,
                    warnings=warnings,
                )
            if ui_kind == "action_menu":
                return SkillResult(
                    skill_id=SKILL_ID,
                    status="succeeded",
                    summary="Battle dialogue advanced back to the battle action menu.",
                    evidence=evidence,
                    warnings=warnings,
                )
            if ui_kind == "dialogue":
                return SkillResult(
                    skill_id=SKILL_ID,
                    status="uncertain",
                    summary="Battle dialogue is still visible after bounded advancement.",
                    evidence=evidence,
                    warnings=warnings,
                )
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary=f"Battle dialogue advanced to a non-neutral battle UI: {ui_kind}.",
                evidence=evidence,
                warnings=warnings,
            )

    if mode != "battle" or battle_type_raw in {None, 0}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="No battle is active, so battle dialogue advancement is unavailable.",
            evidence=evidence,
            warnings=warnings,
        )

    if ui_kind == "dialogue":
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Battle dialogue is visible and can be advanced with bounded A presses.",
            evidence=evidence,
            warnings=warnings,
        )

    if ui_kind == "action_menu":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Battle action menu is already available; no battle dialogue is waiting.",
            evidence=evidence,
            warnings=warnings,
        )

    if ui_kind in {"item_menu", "move_menu", "party_menu"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Battle UI is {ui_kind}; use a menu-specific skill instead.",
            evidence=evidence,
            warnings=warnings,
        )

    if ui_kind == "unknown":
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Battle is active but visible UI is still settling; wait for battle dialogue or menu.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary="Battle is active, but visible UI is not clearly dialogue or a neutral menu.",
        evidence=evidence,
        warnings=warnings,
    )


def battle_ui_kind(screenshot_path: str | Path | None) -> str:
    if screenshot_path is None:
        return "unknown"
    path = Path(screenshot_path)
    if not path.exists():
        return "unknown"
    try:
        return inspect_battle_ui_screenshot(path).kind
    except Exception:
        return "unknown"
