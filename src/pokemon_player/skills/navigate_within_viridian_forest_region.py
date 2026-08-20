from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from pokemon_player.battle_ui import dark_ratio
from pokemon_player.capsule_a_navigation import (
    ALLOWED_MAP_IDS,
    at_landmark,
    is_allowed_position,
    is_boundary_position,
    resolve_landmark,
    snapshot_position,
)
from pokemon_player.skill_result import SkillResult


SKILL_ID = "navigate_within_viridian_forest_region"
STALE_TEXT_MENU_OVERWORLD_WARNING = "Screen tiles indicate overworld despite stale text/menu WRAM flags."


def navigate_within_viridian_forest_region(
    snapshot: Mapping[str, Any],
    *,
    target: str | None = "forest_grass",
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    landmark = resolve_landmark(target)
    position = snapshot_position(snapshot)
    evidence = _base_evidence(snapshot, target=target)
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))

    if landmark is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unknown Capsule A navigation target: {target!r}.",
            evidence=evidence,
            warnings=warnings,
        )

    evidence = evidence + (
        f"target_id={landmark.id}",
        f"target_position={landmark.position.format()}",
    )

    if snapshot.get("battle_type_raw") not in {None, 0} or snapshot.get("mode") == "battle":
        if before_snapshot is not None and snapshot.get("battle_type_raw") in {1, 2}:
            battle_type = snapshot.get("battle_type_raw")
            battle_kind = "wild" if battle_type == 1 else "trainer"
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Navigation reached a {battle_kind} battle route waypoint before the requested landmark.",
                evidence=evidence
                + (
                    f"{battle_kind}_battle_position={position.format() if position else 'unknown'}",
                    f"{battle_kind}_battle_waypoint=true",
                ),
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain" if before_snapshot is not None else "blocked",
            summary="Navigation is interrupted by an active battle.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None and snapshot.get("mode") in {"dialogue", "menu_or_dialogue_uncertain"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Navigation reached a forced trainer engagement dialogue waypoint before the requested landmark.",
            evidence=evidence
            + (
                f"trainer_engagement_position={position.format() if position else 'unknown'}",
                "trainer_engagement_waypoint=true",
            ),
            warnings=warnings,
        )

    if snapshot.get("mode") != "overworld":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Navigation requires stable overworld mode.",
            evidence=evidence,
            warnings=warnings,
        )

    if position is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Navigation cannot read the current map position.",
            evidence=evidence,
            warnings=warnings,
        )

    if not is_allowed_position(position):
        boundary = " boundary" if is_boundary_position(position) else ""
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked" if before_snapshot is None else "failed",
            summary=f"Current map is outside the Capsule A Viridian Forest region{boundary}.",
            evidence=evidence + (f"allowed_maps={_format_allowed_maps()}",),
            warnings=warnings,
        )

    if at_landmark(position, landmark):
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=f"Player is at {landmark.label}.",
            evidence=evidence,
            warnings=warnings,
        )

    if STALE_TEXT_MENU_OVERWORLD_WARNING in warnings and screenshot_has_bottom_text_box(screenshot_path):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked" if before_snapshot is None else "failed",
            summary="Navigation requires clearing stale text/menu before movement.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        before_position = snapshot_position(before_snapshot)
        return SkillResult(
            skill_id=SKILL_ID,
            status="failed",
            summary=f"Navigation ended before reaching {landmark.label}.",
            evidence=evidence
            + (
                f"before_position={before_position.format() if before_position else 'unknown'}",
                f"after_position={position.format()}",
            ),
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=f"Navigation can start toward {landmark.label}.",
        evidence=evidence + (f"allowed_maps={_format_allowed_maps()}",),
        warnings=warnings,
    )


def _base_evidence(snapshot: Mapping[str, Any], *, target: str | None) -> tuple[str, ...]:
    position = snapshot_position(snapshot)
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"position={position.format() if position else 'unknown'}",
        f"target={target}",
    )


def _format_allowed_maps() -> str:
    return ",".join(f"0x{map_id:02X}" for map_id in sorted(ALLOWED_MAP_IDS))


def screenshot_has_bottom_text_box(path: str | Path | None) -> bool:
    if path is None:
        return False
    image_path = Path(path)
    if not image_path.exists():
        return False
    image = Image.open(image_path).convert("L")
    if image.size[0] < 160 or image.size[1] < 144:
        return False
    top_line = dark_ratio(image.crop((0, 96, 160, 98)))
    border_inner = dark_ratio(image.crop((8, 98, 152, 102)))
    bottom_line = dark_ratio(image.crop((0, 136, 160, 144)))
    left_edge = dark_ratio(image.crop((0, 104, 8, 144)))
    right_edge = dark_ratio(image.crop((152, 104, 160, 144)))
    body = dark_ratio(image.crop((0, 104, 160, 144)))
    body_inner = dark_ratio(image.crop((8, 112, 152, 136)))
    return (
        top_line < 0.08
        and border_inner > 0.55
        and bottom_line > 0.30
        and left_edge > 0.20
        and right_edge > 0.20
        and 0.03 < body < 0.65
        and body_inner < 0.25
    )


def trainer_alert_pending_dialogue(snapshot: Mapping[str, Any]) -> bool:
    return (
        snapshot.get("mode") == "overworld"
        and snapshot.get("battle_type_raw") in {None, 0}
        and STALE_TEXT_MENU_OVERWORLD_WARNING in snapshot.get("warnings", ())
    )
