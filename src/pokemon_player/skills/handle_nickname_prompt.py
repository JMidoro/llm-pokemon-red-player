from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from pokemon_player.battle_ui import dark_ratio, inspect_battle_ui_screenshot
from pokemon_player.skill_result import SkillResult


SKILL_ID = "handle_nickname_prompt"
NicknameChoice = Literal["decline", "accept"]


def handle_nickname_prompt(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
    choice: NicknameChoice = "decline",
) -> SkillResult:
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    prompt = screenshot_has_nickname_prompt(screenshot_path)
    intro = screenshot_has_nickname_intro_dialogue(screenshot_path)
    naming = screenshot_has_naming_screen(screenshot_path)
    evidence = base_evidence(snapshot) + (
        f"choice={choice}",
        f"nickname_prompt={prompt}",
        f"nickname_intro={intro}",
        f"naming_screen={naming}",
    )

    if choice not in {"decline", "accept"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unsupported nickname prompt choice: {choice}.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        before_evidence = base_evidence(before_snapshot, prefix="before_")
        evidence = evidence + before_evidence
        if not battle_active(before_snapshot):
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="No post-catch nickname prompt was active before this skill ran.",
                evidence=evidence,
                warnings=warnings,
            )
        if choice == "accept" and naming:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Accepted the nickname prompt and reached the naming keyboard.",
                evidence=evidence,
                warnings=warnings,
            )
        if choice == "decline" and not battle_active(snapshot):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Declined the nickname prompt and returned to stable play.",
                evidence=evidence,
                warnings=warnings,
            )
        if prompt:
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary="Nickname prompt is still visible after input.",
                evidence=evidence,
                warnings=warnings,
            )
        if naming:
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary="Naming keyboard is active; use the nickname text-entry skill next.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Nickname prompt input led to an unclassified post-catch state.",
            evidence=evidence,
            warnings=warnings,
        )

    if naming:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Naming keyboard is already active; use the nickname text-entry skill.",
            evidence=evidence,
            warnings=warnings,
        )

    if not battle_active(snapshot):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="No battle/post-catch prompt is active.",
            evidence=evidence,
            warnings=warnings,
        )

    if (prompt or intro) and not post_catch_enemy_context(snapshot):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Nickname-like dialogue was visible, but the enemy facts do not match a post-catch prompt.",
            evidence=evidence + (f"enemy_hp={enemy_hp(snapshot)}",),
            warnings=warnings,
        )

    if prompt or intro:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=(
                "Post-catch nickname yes/no prompt is ready."
                if prompt
                else "Post-catch nickname intro is active and can be advanced to the yes/no prompt."
            ),
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="blocked",
        summary="No nickname yes/no prompt is visible.",
        evidence=evidence,
        warnings=warnings,
    )


def screenshot_has_nickname_prompt(path: str | Path | None) -> bool:
    if path is None:
        return False
    image_path = Path(path)
    if not image_path.exists():
        return False
    try:
        battle_ui = inspect_battle_ui_screenshot(image_path)
    except Exception:
        battle_ui = None
    if battle_ui is not None and battle_ui.kind in {"action_menu", "item_menu", "move_menu", "party_menu"}:
        return False
    image = Image.open(image_path).convert("L")
    if image.size[0] < 160 or image.size[1] < 144:
        return False
    yes_no_box = dark_ratio(image.crop((116, 68, 160, 105)))
    yes_no_left = dark_ratio(image.crop((116, 70, 123, 103)))
    yes_no_top = dark_ratio(image.crop((116, 68, 160, 74)))
    yes_no_text = dark_ratio(image.crop((124, 78, 154, 99)))
    yes_no_outside_left = dark_ratio(image.crop((100, 68, 114, 105)))
    bottom_top = dark_ratio(image.crop((0, 96, 160, 102)))
    return (
        yes_no_box > 0.18
        and yes_no_left > 0.16
        and yes_no_top > 0.12
        and yes_no_text > 0.16
        and yes_no_outside_left < 0.16
        and bottom_top > 0.25
    )


def screenshot_has_nickname_intro_dialogue(path: str | Path | None) -> bool:
    if path is None:
        return False
    image_path = Path(path)
    if not image_path.exists():
        return False
    try:
        battle_ui = inspect_battle_ui_screenshot(image_path)
    except Exception:
        battle_ui = None
    if battle_ui is not None and battle_ui.kind in {"action_menu", "item_menu", "move_menu", "party_menu"}:
        return False
    image = Image.open(image_path).convert("L")
    if image.size[0] < 160 or image.size[1] < 144:
        return False
    bottom_border = dark_ratio(image.crop((0, 96, 160, 103)))
    first_line_left = dark_ratio(image.crop((8, 112, 84, 121)))
    first_line_right = dark_ratio(image.crop((84, 112, 154, 121)))
    second_line_left = dark_ratio(image.crop((8, 128, 94, 137)))
    second_line_right = dark_ratio(image.crop((94, 128, 154, 137)))
    yes_no_box = dark_ratio(image.crop((116, 68, 160, 105)))
    standard_intro = (
        bottom_border > 0.25
        and first_line_left > 0.16
        and first_line_right > 0.05
        and second_line_left > 0.12
        and second_line_right > 0.10
        and yes_no_box < 0.16
    )
    final_question = (
        bottom_border > 0.25
        and first_line_left > 0.10
        and first_line_right > 0.10
        and second_line_left > 0.18
        and second_line_right < 0.05
        and yes_no_box < 0.16
    )
    return standard_intro or final_question


def screenshot_has_naming_screen(path: str | Path | None) -> bool:
    if path is None:
        return False
    image_path = Path(path)
    if not image_path.exists():
        return False
    image = Image.open(image_path).convert("L")
    if image.size[0] < 160 or image.size[1] < 144:
        return False
    if dark_ratio(image.crop((0, 0, 160, 144))) > 0.95:
        return False
    if dark_ratio(image.crop((0, 0, 160, 144))) > 0.35:
        return False
    name_label = dark_ratio(image.crop((0, 32, 100, 48)))
    keyboard_left = dark_ratio(image.crop((0, 54, 8, 136)))
    keyboard_top = dark_ratio(image.crop((0, 54, 160, 60)))
    keyboard_area = dark_ratio(image.crop((0, 54, 160, 136)))
    keyboard_bottom = dark_ratio(image.crop((0, 120, 160, 136)))
    return (
        name_label > 0.20
        and keyboard_left > 0.18
        and keyboard_top > 0.10
        and keyboard_area < 0.25
        and keyboard_bottom < 0.25
    )


def battle_active(snapshot: Mapping[str, Any]) -> bool:
    return snapshot.get("mode") == "battle" and snapshot.get("battle_type_raw") not in {None, 0}


def post_catch_enemy_context(snapshot: Mapping[str, Any]) -> bool:
    value = enemy_hp(snapshot)
    return value is not None and value > 0


def enemy_hp(snapshot: Mapping[str, Any]) -> int | None:
    enemy = snapshot.get("enemy")
    if not isinstance(enemy, Mapping):
        return None
    value = enemy.get("hp")
    return int(value) if isinstance(value, int) else None


def base_evidence(snapshot: Mapping[str, Any], *, prefix: str = "") -> tuple[str, ...]:
    return (
        f"{prefix}mode={snapshot.get('mode', 'unknown')}",
        f"{prefix}battle_type_raw={snapshot.get('battle_type_raw')}",
    )
