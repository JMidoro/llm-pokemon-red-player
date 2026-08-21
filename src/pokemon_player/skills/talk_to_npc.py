from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "talk_to_npc"


@dataclass(frozen=True)
class NpcInteraction:
    id: str
    label: str
    map_id: int
    x: int
    y: int
    buttons: tuple[str, ...]


INTERACTIONS: dict[str, NpcInteraction] = {
    "professor_oak": NpcInteraction(
        id="professor_oak",
        label="Professor Oak at the starter table",
        map_id=0x28,
        x=5,
        y=3,
        buttons=("up", "a"),
    ),
    "viridian_mart_clerk": NpcInteraction(
        id="viridian_mart_clerk",
        label="Viridian Mart clerk",
        map_id=0x2A,
        x=2,
        y=5,
        buttons=("up", "a"),
    ),
    "brock": NpcInteraction(
        id="brock",
        label="Brock",
        map_id=0x36,
        x=5,
        y=1,
        buttons=("left", "a"),
    ),
}

ALIASES = {
    "oak": "professor_oak",
    "professor_oak": "professor_oak",
    "mart_clerk": "viridian_mart_clerk",
    "viridian_clerk": "viridian_mart_clerk",
    "viridian_mart_clerk": "viridian_mart_clerk",
    "brock": "brock",
}


def talk_to_npc(
    snapshot: Mapping[str, Any],
    *,
    target: str,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    interaction = resolve_interaction(target)
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    visual = inspect_ui_visual_state(screenshot_path)
    evidence = base_evidence(snapshot) + (
        f"target={interaction.id if interaction else target}",
        f"visual_bottom_text_box={visual.bottom_text_box}",
        f"visual_upper_menu={visual.upper_menu}",
    )

    if interaction is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unknown supported NPC target: {target!r}.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        before_position = position_tuple(before_snapshot)
        evidence += (
            f"before_position={format_position(before_position)}",
            f"before_mode={before_snapshot.get('mode', 'unknown')}",
            f"before_battle_type_raw={before_snapshot.get('battle_type_raw')}",
        )
        if before_position != (interaction.map_id, interaction.x, interaction.y):
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary=f"The player was not at the interaction point for {interaction.label}.",
                evidence=evidence,
                warnings=warnings,
            )
        if interaction_started(before_snapshot, snapshot, visual_bottom=visual.bottom_text_box):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Started the interaction with {interaction.label}.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="failed",
            summary=f"The interaction input did not visibly start dialogue or battle with {interaction.label}.",
            evidence=evidence,
            warnings=warnings,
        )

    if visual.bottom_text_box:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Dialogue is already active; advance it instead of starting the NPC interaction again.",
            evidence=evidence,
            warnings=warnings,
        )

    if snapshot.get("mode") != "overworld" or snapshot.get("battle_type_raw") not in {None, 0}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="NPC interaction requires stable overworld control.",
            evidence=evidence,
            warnings=warnings,
        )

    position = position_tuple(snapshot)
    if position != (interaction.map_id, interaction.x, interaction.y):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Navigate to {interaction.label} before trying to talk.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=f"The player can talk to {interaction.label} from this position.",
        evidence=evidence + ("buttons_hidden_by_semantic_skill=true",),
        warnings=warnings,
    )


def interaction_options(snapshot: Mapping[str, Any]) -> list[dict[str, str]]:
    position = position_tuple(snapshot)
    if snapshot.get("mode") != "overworld" or snapshot.get("battle_type_raw") not in {None, 0}:
        return []
    return [
        {"id": interaction.id, "label": interaction.label}
        for interaction in INTERACTIONS.values()
        if position == (interaction.map_id, interaction.x, interaction.y)
    ]


def default_interaction_target(snapshot: Mapping[str, Any]) -> str | None:
    options = interaction_options(snapshot)
    return options[0]["id"] if options else None


def interaction_buttons(target: str) -> tuple[str, ...]:
    interaction = resolve_interaction(target)
    if interaction is None:
        raise ValueError(f"Unknown supported NPC target: {target!r}.")
    return interaction.buttons


def resolve_interaction(target: str) -> NpcInteraction | None:
    normalized = str(target).strip().lower().replace(" ", "_").replace("-", "_")
    return INTERACTIONS.get(ALIASES.get(normalized, normalized))


def interaction_started(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    visual_bottom: bool,
) -> bool:
    before_battle = int(before.get("battle_type_raw", 0) or 0)
    after_battle = int(after.get("battle_type_raw", 0) or 0)
    if after.get("mode") == "battle" or (before_battle == 0 and after_battle != 0):
        return True
    if visual_bottom or after.get("mode") in {"dialogue", "menu", "menu_or_dialogue_uncertain"}:
        return True
    if before.get("inventory") != after.get("inventory"):
        return True
    if before.get("story_events") != after.get("story_events"):
        return True
    return False


def position_tuple(snapshot: Mapping[str, Any]) -> tuple[int, int, int] | None:
    position = snapshot.get("position")
    if not isinstance(position, Mapping):
        return None
    try:
        return (
            int(position.get("map_id")),
            int(position.get("x")),
            int(position.get("y")),
        )
    except (TypeError, ValueError):
        return None


def format_position(position: tuple[int, int, int] | None) -> str:
    if position is None:
        return "unknown"
    return f"map=0x{position[0]:02X},x={position[1]},y={position[2]}"


def base_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"position={format_position(position_tuple(snapshot))}",
    )
