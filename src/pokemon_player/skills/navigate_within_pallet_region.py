from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.pallet_navigation import (
    PALLET_MAP_IDS,
    at_pallet_landmark,
    default_navigation_target,
    is_allowed_position,
    resolve_landmark,
    snapshot_position,
    target_options_for_current_map,
)
from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "navigate_within_pallet_region"


def navigate_within_pallet_region(
    snapshot: Mapping[str, Any],
    *,
    target: str | None = None,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    if target is None:
        target = default_navigation_target(snapshot)
    landmark = resolve_landmark(target)
    position = snapshot_position(snapshot)
    evidence = _base_evidence(snapshot, target=target)
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    visual = inspect_ui_visual_state(screenshot_path)

    if landmark is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unknown Pallet navigation target: {target!r}.",
            evidence=evidence,
            warnings=warnings,
        )

    evidence = evidence + (
        f"target_id={landmark.id}",
        f"target_position={landmark.position.format()}",
        f"target_source={landmark.source}",
    )

    if snapshot.get("battle_type_raw") not in {None, 0} or snapshot.get("mode") == "battle":
        if before_snapshot is not None:
            battle_type = snapshot.get("battle_type_raw")
            battle_kind = "wild" if battle_type == 1 else "trainer" if battle_type == 2 else "unknown"
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Pallet navigation reached a {battle_kind} battle waypoint before the requested landmark.",
                evidence=evidence
                + (
                    f"battle_position={position.format() if position else 'unknown'}",
                    f"battle_type={battle_kind}",
                    "battle_waypoint=true",
                ),
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Pallet navigation is interrupted by an active battle.",
            evidence=evidence,
            warnings=warnings,
        )

    if snapshot.get("mode") not in {"overworld", "dialogue", "menu_or_dialogue_uncertain"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Pallet navigation requires stable overworld or story-dialogue state.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is None and snapshot.get("mode") == "dialogue":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Active dialogue/text must be advanced before starting Pallet navigation.",
            evidence=evidence
            + (
                f"visual_bottom_text_box={visual.bottom_text_box}",
                f"visual_upper_menu={visual.upper_menu}",
            ),
            warnings=warnings,
        )

    if position is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Pallet navigation cannot read the current map position.",
            evidence=evidence,
            warnings=warnings,
        )

    if not is_allowed_position(position):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked" if before_snapshot is None else "failed",
            summary="Current map is outside the Pallet navigation region.",
            evidence=evidence + (f"allowed_maps={_format_allowed_maps()}",),
            warnings=warnings,
        )

    if at_pallet_landmark(position, landmark):
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded" if before_snapshot is not None else "blocked",
            summary=(
                f"Navigation reached {landmark.label}."
                if before_snapshot is not None
                else f"Player is already at {landmark.label}; choose the next semantic action."
            ),
            evidence=evidence + (("navigation_noop=true",) if before_snapshot is None else ()),
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

    targets = target_options_for_current_map(snapshot)
    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=f"Pallet navigation can start toward {landmark.label}.",
        evidence=evidence
        + (
            f"allowed_maps={_format_allowed_maps()}",
            "current_map_targets=" + ",".join(str(option["id"]) for option in targets),
        ),
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
    return ",".join(f"0x{map_id:02X}" for map_id in sorted(PALLET_MAP_IDS))
