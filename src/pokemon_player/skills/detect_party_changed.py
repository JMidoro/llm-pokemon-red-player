from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from pokemon_player.skill_result import SkillResult


SKILL_ID = "detect_party_changed"


def detect_party_changed(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    target_species: str | int | None = None,
) -> SkillResult:
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    current = party_roster(snapshot)
    evidence = [f"party_count={len(current)}"]

    if before_snapshot is None:
        evidence.append("before_party_count=missing")
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Party-change detection requires a before snapshot.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    before = party_roster(before_snapshot)
    before_warnings = tuple(str(item) for item in before_snapshot.get("warnings", ()))
    added = multiset_delta(current, before)
    removed = multiset_delta(before, current)
    evidence.extend(
        [
            f"before_party_count={len(before)}",
            f"party_delta={len(current) - len(before)}",
            f"added_species={format_species_counter(added)}",
            f"removed_species={format_species_counter(removed)}",
        ]
    )

    target_name = normalize_target_species(target_species)
    if target_name:
        before_target_count = species_count(before, target_name)
        current_target_count = species_count(current, target_name)
        evidence.extend(
            [
                f"target_species={target_name}",
                f"before_target_count={before_target_count}",
                f"target_count={current_target_count}",
            ]
        )
        if current_target_count > before_target_count:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Party roster gained target species {target_name}.",
                evidence=tuple(evidence),
                warnings=before_warnings + warnings,
            )

    if current != before:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Party roster changed.",
            evidence=tuple(evidence),
            warnings=before_warnings + warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="failed",
        summary="Party roster is unchanged.",
        evidence=tuple(evidence),
        warnings=before_warnings + warnings,
    )


def party_roster(snapshot: Mapping[str, Any]) -> tuple[tuple[int, int | None, str, str], ...]:
    party = snapshot.get("party", ())
    if not isinstance(party, list):
        return ()

    members: list[tuple[int, int | None, str, str]] = []
    for member in party:
        if not isinstance(member, Mapping):
            continue
        species_id = member.get("species_id")
        members.append(
            (
                int(member.get("slot", 0)),
                int(species_id) if isinstance(species_id, int) else None,
                str(member.get("species_name", "")),
                str(member.get("nickname", "")),
            )
        )
    return tuple(members)


def species_counter(roster: tuple[tuple[int, int | None, str, str], ...]) -> Counter[str]:
    return Counter(member[2] for member in roster if member[2])


def multiset_delta(
    left: tuple[tuple[int, int | None, str, str], ...],
    right: tuple[tuple[int, int | None, str, str], ...],
) -> Counter[str]:
    return species_counter(left) - species_counter(right)


def format_species_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ",".join(f"{species}x{count}" for species, count in sorted(counter.items()))


def species_count(roster: tuple[tuple[int, int | None, str, str], ...], species_name: str) -> int:
    return sum(1 for member in roster if member[2].lower() == species_name.lower())


def normalize_target_species(target_species: str | int | None) -> str | None:
    if target_species is None:
        return None
    if isinstance(target_species, int):
        return None
    cleaned = target_species.strip()
    return cleaned or None
