from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.battle_ui import inspect_battle_ui_screenshot
from pokemon_player.catalog import normalize_name
from pokemon_player.skill_result import SkillResult


SKILL_ID = "switch_party_member"


def switch_party_member(
    snapshot: Mapping[str, Any],
    *,
    target: str | int,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    evidence = base_evidence(snapshot) + (f"target={target}",)

    if before_snapshot is not None:
        return classify_switch_result(
            snapshot,
            before_snapshot=before_snapshot,
            target=target,
            screenshot_path=screenshot_path,
            evidence=evidence,
            warnings=warnings,
        )

    if snapshot.get("mode") != "battle" or snapshot.get("battle_type_raw") in {None, 0}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="A battle must be active before switching party members.",
            evidence=evidence,
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

    active_slot = snapshot.get("active_party_slot")
    active = active_party_member(snapshot)
    active_hp = int(active.get("hp", 0) or 0) if active else 0
    target_slot = target_member.get("slot")
    target_species = target_member.get("species_name", "unknown")
    target_hp = int(target_member.get("hp", 0))
    evidence = evidence + party_evidence(snapshot) + (
        f"active_party_slot={active_slot}",
        f"active_hp={active_hp}",
        f"target_party_slot={target_slot}",
        f"target_species={target_species}",
        f"target_hp={target_hp}",
    )

    forced_replacement = active_hp <= 0 and target_hp > 0 and target_slot != active_slot
    if screenshot_path and battle_dialogue_visible(screenshot_path) and not forced_replacement:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Battle dialogue is waiting; advance battle dialogue before switching party members.",
            evidence=evidence + ("screenshot=battle_dialogue",),
            warnings=warnings,
        )

    if target_slot == active_slot:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"{target_species} is already the active battler.",
            evidence=evidence,
            warnings=warnings,
        )

    if target_hp <= 0:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"{target_species} is fainted and cannot be switched in.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=(
            f"Forced replacement can bring out {target_species} in party slot {target_slot}."
            if forced_replacement
            else f"{target_species} in party slot {target_slot} can be switched in."
        ),
        evidence=evidence + (("forced_replacement=true",) if forced_replacement else ()),
        warnings=warnings,
    )


def classify_switch_result(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any],
    target: str | int,
    screenshot_path: str | Path | None,
    evidence: tuple[str, ...],
    warnings: tuple[str, ...],
) -> SkillResult:
    target_member = resolve_target_member(before_snapshot, target)
    if target_member is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Target party member {target!r} was not found in the before snapshot.",
            evidence=evidence + party_evidence(before_snapshot),
            warnings=warnings,
        )

    before_active_slot = before_snapshot.get("active_party_slot")
    target_slot = target_member.get("slot")
    target_species = target_member.get("species_name", "unknown")
    after_active_slot = snapshot.get("active_party_slot")
    after_active = active_party_member(snapshot)
    evidence = evidence + (
        f"before_active_party_slot={before_active_slot}",
        f"target_party_slot={target_slot}",
        f"target_species={target_species}",
        f"after_active_party_slot={after_active_slot}",
        f"after_active_species={after_active.get('species_name', 'unknown') if after_active else 'missing'}",
    )

    if after_active_slot == target_slot and before_active_slot != target_slot:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=f"Active battler changed to {target_species} in party slot {target_slot}.",
            evidence=evidence,
            warnings=warnings,
        )

    if screenshot_path and battle_dialogue_visible(screenshot_path):
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Switch dialogue is still visible; wait for active battler facts to settle.",
            evidence=evidence + ("screenshot=battle_dialogue",),
            warnings=warnings,
        )

    if after_active_slot == before_active_slot:
        return SkillResult(
            skill_id=SKILL_ID,
            status="failed",
            summary="Active battler did not change after the switch attempt.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary="Active battler changed, but not to the requested party member.",
        evidence=evidence,
        warnings=warnings,
    )


def resolve_target_member(snapshot: Mapping[str, Any], target: str | int) -> Mapping[str, Any] | None:
    party = snapshot.get("party", ())
    if not isinstance(party, list):
        return None
    if isinstance(target, int):
        for member in party:
            if isinstance(member, Mapping) and member.get("slot") == target:
                return member
        return None

    normalized_target = normalize_name(target)
    for member in party:
        if not isinstance(member, Mapping):
            continue
        species = normalize_name(str(member.get("species_name", "")))
        nickname = normalize_name(str(member.get("nickname", "")))
        if normalized_target in {species, nickname}:
            return member
    return None


def active_party_member(snapshot: Mapping[str, Any]) -> Mapping[str, Any] | None:
    active = snapshot.get("active_party_member")
    if isinstance(active, Mapping):
        return active
    slot = snapshot.get("active_party_slot")
    return resolve_target_member(snapshot, slot) if isinstance(slot, int) else None


def party_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    party = snapshot.get("party", ())
    if not isinstance(party, list):
        return ("party=missing",)
    parts = []
    for member in party:
        if not isinstance(member, Mapping):
            continue
        parts.append(
            f"{member.get('slot')}:{member.get('species_name', 'unknown')}:hp{member.get('hp', 'unknown')}"
        )
    return (f"party={','.join(parts)}",)


def base_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
    )


def battle_dialogue_visible(path: str | Path) -> bool:
    return inspect_battle_ui_screenshot(path).kind == "dialogue"
