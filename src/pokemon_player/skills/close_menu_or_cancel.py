from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.skill_result import SkillResult
from pokemon_player.battle_ui import forced_party_selection_prompt_visible, inspect_battle_ui_screenshot
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "close_menu_or_cancel"
CANCELABLE_MODES = {"menu", "dialogue", "menu_or_dialogue_uncertain"}
BATTLE_CANCELABLE_UI = {"item_menu", "move_menu", "party_menu"}


def close_menu_or_cancel(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    visual = inspect_ui_visual_state(screenshot_path)
    in_battle = battle_type_raw not in {None, 0} or mode == "battle"
    battle_ui = None
    if in_battle and screenshot_path and Path(screenshot_path).exists():
        battle_ui = inspect_battle_ui_screenshot(screenshot_path)
    evidence = _base_evidence(snapshot) + (
        f"visual_bottom_text_box={visual.bottom_text_box}",
        f"visual_upper_menu={visual.upper_menu}",
    )

    if in_battle:
        battle_kind = battle_ui.kind if battle_ui else "unknown"
        evidence = evidence + (f"screenshot_battle_ui={battle_kind}",)
        forced_party_selection = (
            battle_kind == "party_menu"
            and screenshot_path is not None
            and Path(screenshot_path).exists()
            and forced_party_selection_prompt_visible(screenshot_path)
        )
        if before_snapshot is not None:
            before_battle_type = before_snapshot.get("battle_type_raw")
            if before_battle_type not in {None, 0} and battle_kind == "action_menu":
                return SkillResult(
                    skill_id=SKILL_ID,
                    status="succeeded",
                    summary="Cancel action recovered to the battle action menu.",
                    evidence=evidence + (f"before_battle_type_raw={before_battle_type}",),
                    warnings=warnings,
                )
        if forced_party_selection:
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="Forced party selection is active; choose a replacement party member instead of canceling.",
                evidence=evidence + ("forced_party_selection=true",),
                warnings=warnings,
            )
        if battle_kind in BATTLE_CANCELABLE_UI:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Cancelable battle {battle_kind.replace('_', ' ')} is active.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Battle UI is active, but it is not a safe cancelable submenu.",
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
        if before_battle_type in {None, 0} and before_mode in CANCELABLE_MODES:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Cancel action moved from a non-battle UI surface to a safer state.",
                evidence=evidence,
                warnings=warnings,
            )

    if mode in CANCELABLE_MODES or visual.upper_menu:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Cancelable non-battle UI is active.",
            evidence=evidence,
            warnings=warnings,
        )

    if mode == "overworld":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Already in overworld; there is no menu level to cancel.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary="State is not clearly a cancelable menu or stable overworld.",
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
