from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pokemon_player.skill_result import SkillResult


SKILL_ID = "detect_wild_battle"
WILD_BATTLE_TYPE = 1
VIRIDIAN_FOREST_MAP_ID = 0x33


def detect_wild_battle(snapshot: Mapping[str, Any]) -> SkillResult:
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    position = snapshot.get("position")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    map_id = position.get("map_id") if isinstance(position, Mapping) else None
    map_name = position.get("map_name") if isinstance(position, Mapping) else "unknown"

    evidence = tuple(
        item
        for item in (
            f"mode={mode}",
            f"battle_type_raw={battle_type_raw}",
            f"map_id={_format_map_id(map_id)}",
            f"map_name={map_name}",
        )
        if item
    )

    if battle_type_raw == WILD_BATTLE_TYPE and mode == "battle":
        if map_id == VIRIDIAN_FOREST_MAP_ID:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Wild battle detected in Viridian Forest.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Wild battle detected outside the first Capsule A map.",
            evidence=evidence,
            warnings=warnings,
        )

    if mode == "battle" and battle_type_raw not in {None, 0, WILD_BATTLE_TYPE}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="A battle is active, but it is not classified as a wild battle.",
            evidence=evidence,
            warnings=warnings + (f"Unsupported battle_type_raw={battle_type_raw}.",),
        )

    if mode in {"menu", "dialogue", "menu_or_dialogue_uncertain", "unknown"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="UI state prevents a dependable wild-battle decision.",
            evidence=evidence,
            warnings=warnings,
        )

    if warnings:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Non-battle state has snapshot warnings, so battle absence is not cleanly established.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="failed",
        summary="No wild battle is active.",
        evidence=evidence,
        warnings=warnings,
    )


def _format_map_id(map_id: object) -> str:
    if isinstance(map_id, int):
        return f"0x{map_id:02X}"
    return "unknown"
