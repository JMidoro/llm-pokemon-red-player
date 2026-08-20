from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.switch_party_member import party_evidence, resolve_target_member


SKILL_ID = "overworld_rearrange_party"


def overworld_rearrange_party(
    snapshot: Mapping[str, Any],
    *,
    target: str | int,
    destination_slot: int,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    evidence = base_evidence(snapshot) + (
        f"target={target}",
        f"destination_slot={destination_slot}",
    )

    if before_snapshot is not None:
        return classify_reorder_result(
            snapshot,
            before_snapshot=before_snapshot,
            target=target,
            destination_slot=destination_slot,
            evidence=evidence,
            warnings=warnings,
        )

    party = party_members(snapshot)
    if not is_stable_overworld(snapshot):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Party rearrangement must start from stable overworld.",
            evidence=evidence,
            warnings=warnings,
        )
    if len(party) < 2:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="At least two party members are needed to rearrange the party.",
            evidence=evidence + party_evidence(snapshot),
            warnings=warnings,
        )
    if destination_slot < 1 or destination_slot > len(party):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Destination slot {destination_slot} is outside the current party size.",
            evidence=evidence + party_evidence(snapshot) + (f"party_size={len(party)}",),
            warnings=warnings,
        )

    target_member = resolve_target_member(snapshot, target)
    if target_member is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Target party member {target!r} was not found.",
            evidence=evidence + party_evidence(snapshot),
            warnings=warnings,
        )

    target_slot = int(target_member.get("slot", 0) or 0)
    target_species = target_member.get("species_name", "unknown")
    evidence = evidence + party_evidence(snapshot) + (
        f"target_party_slot={target_slot}",
        f"target_species={target_species}",
    )
    if target_slot == destination_slot:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=f"{target_species} is already in party slot {destination_slot}.",
            evidence=evidence + ("noop=true",),
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=f"{target_species} can be moved from party slot {target_slot} to slot {destination_slot}.",
        evidence=evidence,
        warnings=warnings,
    )


def classify_reorder_result(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any],
    target: str | int,
    destination_slot: int,
    evidence: tuple[str, ...],
    warnings: tuple[str, ...],
) -> SkillResult:
    before_party = party_members(before_snapshot)
    after_party = party_members(snapshot)
    target_member = resolve_target_member(before_snapshot, target)
    if target_member is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Target party member {target!r} was not found in the before snapshot.",
            evidence=evidence + party_evidence(before_snapshot),
            warnings=warnings,
        )
    if destination_slot < 1 or destination_slot > len(before_party):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Destination slot {destination_slot} is outside the before party size.",
            evidence=evidence + (f"party_size={len(before_party)}",),
            warnings=warnings,
        )

    target_key = party_member_identity(target_member)
    after_target = find_member_by_identity(after_party, target_key)
    target_species = target_member.get("species_name", "unknown")
    before_slot = int(target_member.get("slot", 0) or 0)
    after_slot = int(after_target.get("slot", 0) or 0) if after_target else None
    evidence = evidence + (
        f"before_party={format_party_order(before_party)}",
        f"after_party={format_party_order(after_party)}",
        f"target_species={target_species}",
        f"before_target_slot={before_slot}",
        f"after_target_slot={after_slot}",
    )

    if party_identity_multiset(before_party) != party_identity_multiset(after_party):
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Party roster changed while checking reorder result; cannot attribute the outcome to a pure reorder.",
            evidence=evidence,
            warnings=warnings,
        )
    if after_slot == destination_slot:
        if before_slot == destination_slot:
            summary = f"{target_species} remained in requested party slot {destination_slot}."
        else:
            summary = f"{target_species} moved from party slot {before_slot} to slot {destination_slot}."
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=summary,
            evidence=evidence,
            warnings=warnings,
        )
    if before_slot == after_slot:
        return SkillResult(
            skill_id=SKILL_ID,
            status="failed",
            summary=f"{target_species} stayed in party slot {before_slot} instead of moving to slot {destination_slot}.",
            evidence=evidence,
            warnings=warnings,
        )
    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary=f"{target_species} moved to party slot {after_slot}, not requested slot {destination_slot}.",
        evidence=evidence,
        warnings=warnings,
    )


def is_stable_overworld(snapshot: Mapping[str, Any]) -> bool:
    return snapshot.get("mode") == "overworld" and snapshot.get("battle_type_raw") == 0


def party_members(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    party = snapshot.get("party", ())
    if not isinstance(party, list):
        return []
    return [member for member in party if isinstance(member, Mapping)]


def party_member_identity(member: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        member.get("species_id"),
        member.get("species_name"),
        member.get("nickname"),
        member.get("level"),
    )


def find_member_by_identity(
    party: list[Mapping[str, Any]],
    identity: tuple[Any, ...],
) -> Mapping[str, Any] | None:
    matches = [member for member in party if party_member_identity(member) == identity]
    return matches[0] if len(matches) == 1 else None


def party_identity_multiset(party: list[Mapping[str, Any]]) -> Counter[tuple[Any, ...]]:
    return Counter(party_member_identity(member) for member in party)


def format_party_order(party: list[Mapping[str, Any]]) -> str:
    return ",".join(
        f"{member.get('slot')}:{member.get('species_name', 'unknown')}"
        for member in sorted(party, key=lambda item: int(item.get("slot", 0) or 0))
    )


def base_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
    )
