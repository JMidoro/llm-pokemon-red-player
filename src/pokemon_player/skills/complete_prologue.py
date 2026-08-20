from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pokemon_player.pallet_navigation import MAP_PALLET_TOWN, MAP_REDS_HOUSE_2F
from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "complete_prologue"
SUPPORTED_PROLOGUE_NAME = re.compile(r"^[A-Z]{1,7}$")
PrologueHandoff = Literal["red_house_2f", "pallet_outside"]


def complete_prologue(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
    player_name: str = "RED",
    rival_name: str = "BLUE",
    handoff: PrologueHandoff = "pallet_outside",
) -> SkillResult:
    player = player_name.strip().upper()
    rival = rival_name.strip().upper()
    visual = inspect_ui_visual_state(screenshot_path)
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    evidence = _base_evidence(snapshot) + (
        f"player_name={player}",
        f"rival_name={rival}",
        f"handoff={handoff}",
        f"visual_bottom_text_box={visual.bottom_text_box}",
        f"visual_upper_menu={visual.upper_menu}",
    )

    if not SUPPORTED_PROLOGUE_NAME.fullmatch(player):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Player name must be 1-7 uppercase A-Z characters.",
            evidence=evidence,
            warnings=warnings,
        )
    if not SUPPORTED_PROLOGUE_NAME.fullmatch(rival):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Rival name must be 1-7 uppercase A-Z characters.",
            evidence=evidence,
            warnings=warnings,
        )
    if handoff not in {"red_house_2f", "pallet_outside"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unsupported prologue handoff target: {handoff}.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        if handoff == "red_house_2f" and _at_red_house_2f(snapshot) and not visual.bottom_text_box:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Prologue completed and player control reached Red's House 2F.",
                evidence=evidence + ("handoff_reached=red_house_2f",),
                warnings=warnings,
            )
        if handoff == "pallet_outside" and _at_pallet_handoff(snapshot) and not visual.bottom_text_box:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Prologue completed and player control reached Pallet Town outside Red's house.",
                evidence=evidence + ("handoff_reached=pallet_outside",),
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Prologue execution ended before the requested handoff point was verified.",
            evidence=evidence,
            warnings=warnings,
        )

    party = snapshot.get("party")
    if isinstance(party, list) and party:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Prologue requires a pre-starter state with no party Pokemon.",
            evidence=evidence,
            warnings=warnings,
        )

    if _looks_like_fresh_boot(snapshot) or _at_red_house_2f(snapshot):
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Prologue can run from the clean boot/title or intro state.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="blocked",
        summary="Prologue should start from a clean boot/title state before Pallet overworld chapters.",
        evidence=evidence,
        warnings=warnings,
    )


def _base_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    position = snapshot.get("position")
    if isinstance(position, Mapping):
        map_id = position.get("map_id")
        x = position.get("x")
        y = position.get("y")
        position_text = f"map=0x{int(map_id):02X},x={x},y={y}" if isinstance(map_id, int) else "unknown"
    else:
        position_text = "unknown"
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"position={position_text}",
    )


def _looks_like_fresh_boot(snapshot: Mapping[str, Any]) -> bool:
    position = snapshot.get("position")
    if not isinstance(position, Mapping):
        return False
    return (
        position.get("map_id") == MAP_PALLET_TOWN
        and position.get("x") == 0
        and position.get("y") == 0
        and snapshot.get("battle_type_raw") in {None, 0}
    )


def _at_red_house_2f(snapshot: Mapping[str, Any]) -> bool:
    position = snapshot.get("position")
    return isinstance(position, Mapping) and position.get("map_id") == MAP_REDS_HOUSE_2F


def _at_pallet_handoff(snapshot: Mapping[str, Any]) -> bool:
    position = snapshot.get("position")
    if not isinstance(position, Mapping):
        return False
    return position.get("map_id") == MAP_PALLET_TOWN and position.get("x") == 5 and position.get("y") == 6
