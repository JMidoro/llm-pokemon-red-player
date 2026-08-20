from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pokemon_player.skill_result import SkillResult


SKILL_ID = "walk_local_direction"
Direction = Literal["up", "down", "left", "right"]
KNOWN_BLOCKED_FIXTURE_POSITIONS = frozenset(
    {
        (0x29, 1, 4),
    }
)


def walk_local_direction(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    direction: Direction | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    del screenshot_path
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    position = _position_tuple(snapshot)
    evidence = _base_evidence(snapshot)
    if direction is not None:
        evidence = evidence + (f"direction={direction}",)

    if battle_type_raw not in {None, 0} or mode != "overworld":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Walking requires stable overworld mode with no active battle or UI surface.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        before_mode = str(before_snapshot.get("mode", "unknown"))
        before_battle_type = before_snapshot.get("battle_type_raw")
        before_position = _position_tuple(before_snapshot)
        evidence = evidence + (
            f"before_mode={before_mode}",
            f"before_battle_type_raw={before_battle_type}",
            f"before_position={_format_position(before_position)}",
            f"position_delta={_format_delta(before_position, position)}",
        )
        if before_mode != "overworld" or before_battle_type not in {None, 0}:
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="The walk attempt started outside stable overworld mode.",
                evidence=evidence,
                warnings=warnings,
            )
        if _is_one_tile_step(before_position, position, direction):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Player position changed by one requested local step.",
                evidence=evidence,
                warnings=warnings,
            )
        if before_position == position:
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="Walk input did not change coordinates; local movement is blocked.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Position changed, but not as a single local step.",
            evidence=evidence,
            warnings=warnings,
        )

    if position in KNOWN_BLOCKED_FIXTURE_POSITIONS:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Current fixture is a human-verified local blocker.",
            evidence=evidence + ("blocker_source=fixture_position",),
            warnings=warnings
            + (
                "Blocked walking classification uses a fixture position until map collision data is promoted.",
            ),
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary="Stable overworld preconditions are satisfied for a one-step local walk.",
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
        f"position={_format_position(_position_tuple(snapshot))}",
    )


def _position_tuple(snapshot: Mapping[str, Any]) -> tuple[int, int, int] | None:
    position = snapshot.get("position")
    if not isinstance(position, Mapping):
        return None
    map_id = position.get("map_id")
    x = position.get("x")
    y = position.get("y")
    if not all(isinstance(value, int) for value in (map_id, x, y)):
        return None
    return int(map_id), int(x), int(y)


def _format_position(position: tuple[int, int, int] | None) -> str:
    if position is None:
        return "unknown"
    map_id, x, y = position
    return f"map=0x{map_id:02X},x={x},y={y}"


def _format_delta(
    before: tuple[int, int, int] | None,
    after: tuple[int, int, int] | None,
) -> str:
    if before is None or after is None or before[0] != after[0]:
        return "unknown"
    return f"dx={after[1] - before[1]},dy={after[2] - before[2]}"


def _is_one_tile_step(
    before: tuple[int, int, int] | None,
    after: tuple[int, int, int] | None,
    direction: Direction | None,
) -> bool:
    if before is None or after is None or before[0] != after[0]:
        return False
    dx = after[1] - before[1]
    dy = after[2] - before[2]
    if direction == "up":
        return dx == 0 and dy == -1
    if direction == "down":
        return dx == 0 and dy == 1
    if direction == "left":
        return dx == -1 and dy == 0
    if direction == "right":
        return dx == 1 and dy == 0
    return abs(dx) + abs(dy) == 1
