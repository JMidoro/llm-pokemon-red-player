from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from pokemon_player.battle_ui import inspect_battle_ui_screenshot
from pokemon_player.battle_ui import dark_ratio
from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "resolve_battle_outcome_dialogue_bundle"


def resolve_battle_outcome_dialogue_bundle(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    ui_kind = battle_ui_kind(screenshot_path)
    visual = inspect_ui_visual_state(screenshot_path)
    pokedex_page = screenshot_has_pokedex_page(screenshot_path)
    hp = enemy_hp(snapshot)
    pokedex_intro = hp > 0 and screenshot_has_pokedex_intro_dialogue(screenshot_path)
    evidence = base_evidence(snapshot) + (
        f"battle_ui={ui_kind}",
        f"visual_bottom_text_box={visual.bottom_text_box}",
        f"visual_upper_menu={visual.upper_menu}",
        f"pokedex_page={pokedex_page}",
        f"pokedex_intro={pokedex_intro}",
    )
    if before_snapshot is not None:
        before_evidence = base_evidence(before_snapshot, prefix="before_")
        evidence = evidence + before_evidence
        if not battle_active(before_snapshot):
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="No battle outcome dialogue was active before this skill ran.",
                evidence=evidence,
                warnings=warnings,
            )
        if not battle_active(snapshot):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Battle outcome dialogue advanced until the battle ended.",
                evidence=evidence,
                warnings=warnings,
            )
        if ui_kind == "party_menu":
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary="Battle outcome dialogue reached a party-selection decision surface.",
                evidence=evidence,
                warnings=warnings,
            )
        if pokedex_page or pokedex_intro:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Advanced post-catch Pokedex registration dialogue; more aftermath dialogue may remain.",
                evidence=evidence,
                warnings=warnings,
            )
        if visual.bottom_text_box and (ui_kind == "dialogue" or hp <= 0):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Advanced one battle outcome dialogue prompt; more aftermath dialogue may remain.",
                evidence=evidence,
                warnings=warnings,
            )
        if ui_kind == "action_menu":
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Battle outcome dialogue advanced back to the battle action menu.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary=f"Battle outcome dialogue advanced to an unclassified battle UI: {ui_kind}.",
            evidence=evidence,
            warnings=warnings,
        )

    if not battle_active(snapshot):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="No battle is active, so battle outcome dialogue resolution is unavailable.",
            evidence=evidence,
            warnings=warnings,
        )

    if ui_kind == "party_menu":
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Party selection is active; the Director must choose a replacement or switch response.",
            evidence=evidence,
            warnings=warnings,
        )

    if visual.bottom_text_box and visual.upper_menu and hp > 0:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="A battle choice surface is visible; the Director must choose before advancing.",
            evidence=evidence,
            warnings=warnings,
        )

    if pokedex_page:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Post-catch Pokedex registration page is visible and can be advanced.",
            evidence=evidence,
            warnings=warnings,
        )

    if pokedex_intro:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Post-catch Pokedex registration dialogue is visible and can be advanced.",
            evidence=evidence,
            warnings=warnings,
        )

    if ui_kind == "dialogue" or (visual.bottom_text_box and hp <= 0):
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=outcome_summary(snapshot),
            evidence=evidence,
            warnings=warnings,
        )

    if ui_kind == "action_menu":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Battle action menu is already available; use a tactical battle skill.",
            evidence=evidence,
            warnings=warnings,
        )

    if ui_kind in {"item_menu", "move_menu"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Battle UI is {ui_kind}; use a menu-specific skill instead.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary="Battle is active, but outcome dialogue is not clearly visible.",
        evidence=evidence,
        warnings=warnings,
    )


def outcome_summary(snapshot: Mapping[str, Any]) -> str:
    if enemy_hp(snapshot) <= 0:
        return "Battle outcome dialogue is visible after the enemy Pokemon fainted."
    return "Battle outcome dialogue is visible and can be advanced one prompt."


def battle_active(snapshot: Mapping[str, Any]) -> bool:
    return snapshot.get("mode") == "battle" and snapshot.get("battle_type_raw") not in {None, 0}


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


def base_evidence(snapshot: Mapping[str, Any], *, prefix: str = "") -> tuple[str, ...]:
    return (
        f"{prefix}mode={snapshot.get('mode', 'unknown')}",
        f"{prefix}battle_type_raw={snapshot.get('battle_type_raw')}",
        f"{prefix}enemy_hp={enemy_hp(snapshot)}",
    )


def enemy_hp(snapshot: Mapping[str, Any]) -> int:
    enemy = snapshot.get("enemy")
    if not isinstance(enemy, Mapping):
        return -1
    try:
        return int(enemy.get("hp", 0) or 0)
    except (TypeError, ValueError):
        return -1


def screenshot_has_pokedex_page(path: str | Path | None) -> bool:
    if path is None:
        return False
    image_path = Path(path)
    if not image_path.exists():
        return False
    image = Image.open(image_path).convert("L")
    if image.size[0] < 160 or image.size[1] < 144:
        return False
    full_top = dark_ratio(image.crop((0, 0, 160, 8)))
    full_left = dark_ratio(image.crop((0, 0, 8, 144)))
    full_right = dark_ratio(image.crop((152, 0, 160, 144)))
    mid_rule = dark_ratio(image.crop((0, 72, 160, 82)))
    return full_top > 0.11 and 0.10 < full_left < 0.18 and 0.10 < full_right < 0.18 and mid_rule > 0.20


def screenshot_has_pokedex_intro_dialogue(path: str | Path | None) -> bool:
    if path is None:
        return False
    image_path = Path(path)
    if not image_path.exists():
        return False
    image = Image.open(image_path).convert("L")
    if image.size[0] < 160 or image.size[1] < 144:
        return False
    try:
        ui = inspect_battle_ui_screenshot(image_path)
    except Exception:
        return False
    visual = inspect_ui_visual_state(image_path)
    if not visual.bottom_text_box or visual.upper_menu or ui.kind != "action_menu":
        return False

    first_line_left = dark_ratio(image.crop((8, 112, 80, 120)))
    first_line_right = dark_ratio(image.crop((80, 112, 152, 120)))
    second_line_right = dark_ratio(image.crop((80, 128, 152, 136)))
    return first_line_left > 0.18 and first_line_right > 0.12 and second_line_right > 0.12
