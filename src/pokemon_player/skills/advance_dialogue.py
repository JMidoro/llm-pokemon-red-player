from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "advance_dialogue"
RECOVERABLE_TEXT_MODES = {"dialogue", "menu_or_dialogue_uncertain"}


def advance_dialogue(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    visual = inspect_ui_visual_state(screenshot_path)
    evidence = _base_evidence(snapshot) + (
        f"visual_bottom_text_box={visual.bottom_text_box}",
        f"visual_upper_menu={visual.upper_menu}",
    )

    if battle_type_raw not in {None, 0} or mode == "battle":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Battle is active; dialogue advancement should be routed through battle handling.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        before_mode = str(before_snapshot.get("mode", "unknown"))
        before_battle_type = before_snapshot.get("battle_type_raw")
        evidence = evidence + (
            f"before_mode={before_mode}",
            f"before_battle_type_raw={before_battle_type}",
        )
        if before_battle_type in {None, 0} and before_mode in RECOVERABLE_TEXT_MODES | {"menu"}:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Dialogue advance produced a non-battle follow-up state.",
                evidence=evidence,
                warnings=warnings,
            )

    position = snapshot.get("position")
    map_id = position.get("map_id") if isinstance(position, Mapping) else None
    party = snapshot.get("party")
    has_party = isinstance(party, list) and bool(party)
    if visual.bottom_text_box and mode in {"dialogue", "menu", "menu_or_dialogue_uncertain"} and map_id == 0x28 and has_party:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Oak's Lab dialogue/text prompt is ready for one bounded A press.",
            evidence=evidence,
            warnings=warnings,
        )

    if visual.bottom_text_box and mode == "overworld" and warnings and map_id == 0x28:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Stale overworld state has a visible dialogue/text prompt ready for bounded A presses.",
            evidence=evidence,
            warnings=warnings,
        )

    if visual.bottom_text_box and visual.upper_menu:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Text is visible, but an upper menu or choice surface is also active.",
            evidence=evidence,
            warnings=warnings,
        )

    if visual.bottom_text_box or mode in RECOVERABLE_TEXT_MODES:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Dialogue/text prompt is ready for a bounded A press.",
            evidence=evidence,
            warnings=warnings,
        )

    if mode == "menu":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="A menu is active with no clear dialogue prompt to advance.",
            evidence=evidence,
            warnings=warnings,
        )

    if mode == "overworld" and warnings:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Overworld mode has stale UI warnings, so dialogue state is not cleanly resolved.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="blocked",
        summary="No dialogue/text prompt is active.",
        evidence=evidence,
        warnings=warnings,
    )


def _base_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    position = snapshot.get("position")
    map_name = position.get("map_name") if isinstance(position, Mapping) else "unknown"
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"map_name={map_name}",
    )
