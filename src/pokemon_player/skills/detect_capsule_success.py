from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pokemon_player import memory_map as mm
from pokemon_player.skill_result import SkillResult


SKILL_ID = "detect_capsule_success"


def detect_capsule_success(
    state: Mapping[str, Any],
    *,
    target_species: str | int | None = None,
    pokedex: Mapping[str, Any] | None = None,
) -> SkillResult:
    snapshot = snapshot_from_state(state)
    pokedex_facts = pokedex if pokedex is not None else pokedex_from_state(state)
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    target = resolve_target(target_species)
    evidence = base_evidence(snapshot)

    if target is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Capsule success detection requires a supported target species.",
            evidence=evidence + ("target_species=missing_or_unsupported",),
            warnings=warnings,
        )

    target_name, dex_number = target
    party_count = party_species_count(snapshot, target_name)
    evidence = evidence + (
        f"target_species={target_name}",
        f"target_dex_number={dex_number}",
        f"party_target_count={party_count}",
    )

    if not isinstance(pokedex_facts, Mapping):
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Pokedex-owned facts are unavailable, so Capsule success cannot be confirmed.",
            evidence=evidence + ("pokedex=missing",),
            warnings=warnings,
        )

    entry = pokedex_entry(pokedex_facts, dex_number)
    if not isinstance(entry, Mapping):
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary=f"Pokedex entry for target species {target_name} is unavailable.",
            evidence=evidence + (f"pokedex_entry={dex_number}:missing",),
            warnings=warnings,
        )

    owned = bool(entry.get("owned"))
    seen = bool(entry.get("seen"))
    mapped_name = str(entry.get("species_name", "unknown"))
    evidence = evidence + (
        f"pokedex_species_name={mapped_name}",
        f"pokedex_owned={owned}",
        f"pokedex_seen={seen}",
    )

    if mapped_name != target_name:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary=f"Pokedex target mapping mismatch: expected {target_name}, got {mapped_name}.",
            evidence=evidence,
            warnings=warnings,
        )

    if owned:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=f"Capsule target {target_name} is Pokedex-owned.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="failed",
        summary=f"Capsule target {target_name} is not Pokedex-owned yet.",
        evidence=evidence,
        warnings=warnings,
    )


def snapshot_from_state(state: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = state.get("snapshot")
    return nested if isinstance(nested, Mapping) else state


def pokedex_from_state(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
    pokedex = state.get("pokedex")
    return pokedex if isinstance(pokedex, Mapping) else None


def base_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    position = snapshot.get("position")
    map_name = position.get("map_name") if isinstance(position, Mapping) else "unknown"
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"map_name={map_name}",
    )


def resolve_target(target_species: str | int | None) -> tuple[str, int] | None:
    if target_species is None:
        return None

    if isinstance(target_species, int):
        if target_species in mm.PROMOTED_SPECIES_IDS or target_species > mm.POKEDEX_SPECIES_COUNT:
            dex_number = mm.dex_number_for_species_id(target_species)
            if dex_number is not None:
                return mm.species_name(target_species), dex_number
        if 1 <= target_species <= mm.POKEDEX_SPECIES_COUNT:
            species_id = mm.DEX_NUMBER_TO_SPECIES_ID.get(target_species)
            if species_id is None:
                return None
            return mm.species_name(species_id), target_species
        return None

    normalized = target_species.strip().lower()
    if not normalized:
        return None
    for species_id, species_name in mm.SPECIES_NAMES.items():
        if species_name.lower() == normalized:
            dex_number = mm.dex_number_for_species_id(species_id)
            if dex_number is None:
                return None
            return species_name, dex_number
    return None


def pokedex_entry(pokedex: Mapping[str, Any], dex_number: int) -> Mapping[str, Any] | None:
    by_dex_number = pokedex.get("by_dex_number")
    if not isinstance(by_dex_number, Mapping):
        return None
    entry = by_dex_number.get(str(dex_number))
    return entry if isinstance(entry, Mapping) else None


def party_species_count(snapshot: Mapping[str, Any], species_name: str) -> int:
    party = snapshot.get("party", ())
    if not isinstance(party, list):
        return 0
    return sum(
        1
        for member in party
        if isinstance(member, Mapping)
        and str(member.get("species_name", "")).lower() == species_name.lower()
    )
