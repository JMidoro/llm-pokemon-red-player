from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.switch_party_member import resolve_target_member
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "handle_trainer_switch_prompt"
TrainerSwitchChoice = Literal["keep", "switch"]
BATTLE_SET_MASK = 1 << 6


def handle_trainer_switch_prompt(
    snapshot: Mapping[str, Any],
    *,
    choice: TrainerSwitchChoice,
    target: str | int | None = None,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    prompt = screenshot_has_trainer_switch_prompt(snapshot, screenshot_path)
    evidence = (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"battle_style={battle_style(snapshot)}",
        f"trainer_switch_prompt={prompt}",
        f"choice={choice}",
        f"target={target}",
    )

    if choice not in {"keep", "switch"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unsupported trainer switch response: {choice}.",
            evidence=evidence,
            warnings=warnings,
        )

    target_member = None
    if choice == "switch":
        if target is None or target == "":
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="Switching at the trainer prompt requires a target party member.",
                evidence=evidence,
                warnings=warnings,
            )
        target_member = resolve_target_member(before_snapshot or snapshot, target)
        if target_member is None:
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary=f"Target party member {target!r} was not found.",
                evidence=evidence,
                warnings=warnings,
            )
        active_slot = (before_snapshot or snapshot).get("active_party_slot")
        if target_member.get("slot") == active_slot:
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="The requested target is already the active battler.",
                evidence=evidence,
                warnings=warnings,
            )
        if int(target_member.get("hp", 0) or 0) <= 0:
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="The requested switch target is fainted.",
                evidence=evidence,
                warnings=warnings,
            )

    if before_snapshot is not None:
        before_active = before_snapshot.get("active_party_slot")
        after_active = snapshot.get("active_party_slot")
        evidence = evidence + (
            f"before_active_party_slot={before_active}",
            f"after_active_party_slot={after_active}",
        )
        if prompt:
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary="Trainer switch prompt is still visible after the response.",
                evidence=evidence,
                warnings=warnings,
            )
        if choice == "keep" and after_active == before_active:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Kept the current Pokemon in for the trainer's next Pokemon.",
                evidence=evidence,
                warnings=warnings,
            )
        if choice == "switch" and target_member is not None and after_active == target_member.get("slot"):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Switched to {target_member.get('species_name', target)} for the trainer's next Pokemon.",
                evidence=evidence + (f"target_party_slot={target_member.get('slot')}",),
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Trainer switch response ended at an unverified battle surface.",
            evidence=evidence,
            warnings=warnings,
        )

    if not prompt:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="No Shift-style trainer switch prompt is visible.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=(
            "Trainer switch prompt is ready; keep the current Pokemon."
            if choice == "keep"
            else f"Trainer switch prompt is ready; switch to {target_member.get('species_name', target)}."
        ),
        evidence=evidence,
        warnings=warnings,
    )


def screenshot_has_trainer_switch_prompt(
    snapshot: Mapping[str, Any],
    screenshot_path: str | Path | None,
) -> bool:
    if screenshot_path is None:
        return False
    visual = inspect_ui_visual_state(screenshot_path)
    enemy = snapshot.get("enemy") if isinstance(snapshot.get("enemy"), Mapping) else {}
    return (
        snapshot.get("mode") == "battle"
        and snapshot.get("battle_type_raw") == 2
        and battle_style(snapshot) == "shift"
        and int(enemy.get("hp", 0) or 0) > 0
        and visual.bottom_text_box
        and visual.compact_choice
    )


def battle_style(snapshot: Mapping[str, Any]) -> str:
    options = int(snapshot.get("options_raw", 0) or 0)
    return "set" if options & BATTLE_SET_MASK else "shift"
