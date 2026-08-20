from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.capsule_a_navigation import (
    approved_grass_patch_for_map,
    approved_grass_patch_for_position,
    resolve_grass_patch,
    snapshot_position,
)
from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.detect_wild_battle import WILD_BATTLE_TYPE


SKILL_ID = "enter_grass_search_loop"


def enter_grass_search_loop(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    patch: str | None = "forest_grass",
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    del screenshot_path
    position = snapshot_position(snapshot)
    current_patch = approved_grass_patch_for_position(position)
    target_patch = _target_patch_for_request(patch, position, current_patch)
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    evidence = _base_evidence(snapshot, patch=patch)

    if target_patch is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unknown approved grass patch for request: {patch!r}.",
            evidence=evidence,
            warnings=warnings,
        )

    evidence = evidence + (
        f"target_patch_id={target_patch.id}",
        f"target_patch_bounds={target_patch.format_bounds()}",
    )

    if mode == "battle" and battle_type_raw == WILD_BATTLE_TYPE:
        if target_patch.contains(position):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Wild battle started from the approved grass search patch.",
                evidence=evidence + _enemy_evidence(snapshot),
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Wild battle is active, but the last overworld position is outside the approved grass patch.",
            evidence=evidence + _enemy_evidence(snapshot),
            warnings=warnings,
        )

    if mode == "battle" and battle_type_raw not in {None, 0, WILD_BATTLE_TYPE}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Search loop was interrupted by a non-wild battle.",
            evidence=evidence,
            warnings=warnings + (f"Unsupported battle_type_raw={battle_type_raw}.",),
        )

    if mode != "overworld" or battle_type_raw not in {None, 0}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Grass search requires stable overworld mode or a resulting wild battle.",
            evidence=evidence,
            warnings=warnings,
        )

    if position is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Grass search cannot read the current map position.",
            evidence=evidence,
            warnings=warnings,
        )

    if current_patch is None or current_patch.id != target_patch.id:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked" if before_snapshot is None else "failed",
            summary="Player is not in or near an approved Capsule A grass patch.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        before_position = snapshot_position(before_snapshot)
        return SkillResult(
            skill_id=SKILL_ID,
            status="failed",
            summary="Grass search input budget ended before a wild battle started.",
            evidence=evidence
            + (
                f"before_position={before_position.format() if before_position else 'unknown'}",
                f"after_position={position.format()}",
            ),
            warnings=warnings,
        )

    if target_patch.contains(position):
        summary = "Search can start inside the approved grass patch."
    else:
        summary = "Search can start near the approved grass patch and step into it."
    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=summary,
        evidence=evidence,
        warnings=warnings,
    )


def _base_evidence(snapshot: Mapping[str, Any], *, patch: str | None) -> tuple[str, ...]:
    position = snapshot_position(snapshot)
    current_patch = approved_grass_patch_for_position(position)
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"position={position.format() if position else 'unknown'}",
        f"approved_patch_id={current_patch.id if current_patch else 'none'}",
        f"in_approved_grass={current_patch.contains(position) if current_patch else False}",
        f"patch={patch}",
    )


def _target_patch_for_request(
    patch: str | None,
    position: Any,
    current_patch: Any,
) -> Any:
    if patch is None or str(patch).strip().lower().replace("-", "_") in {"", "auto", "current", "current_map"}:
        if current_patch is not None:
            return current_patch
        map_id = position.map_id if position is not None else None
        return approved_grass_patch_for_map(map_id)
    return resolve_grass_patch(patch)


def _enemy_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    enemy = snapshot.get("enemy")
    if not isinstance(enemy, Mapping):
        return ()
    return (
        f"enemy_species={enemy.get('species_name', 'unknown')}",
        f"enemy_level={enemy.get('level', 'unknown')}",
    )
