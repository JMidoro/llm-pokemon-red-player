from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.capsule_a_navigation import MAP_VIRIDIAN_POKECENTER, snapshot_position
from pokemon_player.pewter_navigation import MAP_PEWTER_POKECENTER
from pokemon_player.skill_result import SkillResult


SKILL_ID = "heal_at_pokecenter"
SUPPORTED_POKECENTER_MAP_IDS = frozenset({MAP_VIRIDIAN_POKECENTER, MAP_PEWTER_POKECENTER})


def heal_at_pokecenter(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    del screenshot_path
    position = snapshot_position(snapshot)
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    evidence = (
        f"mode={mode}",
        f"battle_type_raw={battle_type_raw}",
        f"position={position.format() if position else 'unknown'}",
        f"party_needs_healing={party_needs_healing(snapshot)}",
        f"party_fully_healed={party_fully_healed(snapshot)}",
    )

    if battle_type_raw not in {None, 0} or mode == "battle":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Healing at a PokeCenter is unavailable during battle.",
            evidence=evidence,
            warnings=warnings,
        )

    if position is None or position.map_id not in SUPPORTED_POKECENTER_MAP_IDS:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Player must be inside a supported PokeCenter to heal.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        before_evidence = (
            f"before_party_needs_healing={party_needs_healing(before_snapshot)}",
            f"before_party_fully_healed={party_fully_healed(before_snapshot)}",
        )
        evidence = evidence + before_evidence
        if party_needs_healing(before_snapshot) and party_fully_healed(snapshot):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="PokeCenter healing restored the party.",
                evidence=evidence,
                warnings=warnings,
            )
        if party_fully_healed(snapshot):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Party is fully healed after PokeCenter interaction.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="PokeCenter interaction ended before the party was fully healed.",
            evidence=evidence,
            warnings=warnings,
        )

    if mode != "overworld":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Healing should start from stable overworld inside the PokeCenter.",
            evidence=evidence,
            warnings=warnings,
        )

    if party_fully_healed(snapshot):
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Party is already fully healed at the PokeCenter.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary="Party can be healed at the PokeCenter counter.",
        evidence=evidence,
        warnings=warnings,
    )


def party_needs_healing(snapshot: Mapping[str, Any]) -> bool:
    return any(member_needs_healing(member) for member in party_members(snapshot))


def party_fully_healed(snapshot: Mapping[str, Any]) -> bool:
    members = party_members(snapshot)
    return bool(members) and all(not member_needs_healing(member) for member in members)


def party_members(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    party = snapshot.get("party")
    if not isinstance(party, list):
        return []
    return [member for member in party if isinstance(member, Mapping) and int(member.get("species_id", 0) or 0) != 0]


def member_needs_healing(member: Mapping[str, Any]) -> bool:
    try:
        hp = int(member.get("hp", 0) or 0)
        max_hp = int(member.get("max_hp", 0) or 0)
        status = int(member.get("status", 0) or 0)
    except (TypeError, ValueError):
        return True
    return max_hp > 0 and (hp < max_hp or status != 0)
