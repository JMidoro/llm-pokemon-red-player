from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.battle_ui import forced_party_selection_prompt_visible, inspect_battle_ui_screenshot
from pokemon_player.catalog import resolve_move
from pokemon_player.memory_map import move_name
from pokemon_player.skill_result import SkillResult


SKILL_ID = "use_move"


def use_move(
    snapshot: Mapping[str, Any],
    *,
    requested_move: str | int,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    try:
        requested = resolve_requested_move(requested_move)
    except ValueError as exc:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=str(exc),
            evidence=base_evidence(snapshot) + (f"requested_move={requested_move}",),
            warnings=warnings,
        )
    evidence = base_evidence(snapshot) + (f"requested_move={requested.name}",)

    if before_snapshot is not None:
        return classify_use_move_result(
            snapshot,
            before_snapshot=before_snapshot,
            requested=requested,
            screenshot_path=screenshot_path,
            evidence=evidence,
            warnings=warnings,
        )

    if snapshot.get("mode") != "battle" or snapshot.get("battle_type_raw") in {None, 0}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="A battle must be active before using a move.",
            evidence=evidence,
            warnings=warnings,
        )

    if screenshot_path:
        battle_ui = inspect_battle_ui_screenshot(screenshot_path)
        if battle_ui.kind == "dialogue":
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="Battle dialogue is waiting; advance battle dialogue before selecting a move.",
                evidence=evidence + ("screenshot=battle_dialogue",),
                warnings=warnings,
            )
        if battle_ui.kind == "party_menu" and forced_party_selection_prompt_visible(screenshot_path):
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary="Forced party selection is active; switch to a conscious party member before using a move.",
                evidence=evidence + ("screenshot_battle_ui=party_menu", "forced_party_selection=true"),
                warnings=warnings,
            )
        if battle_ui.kind not in {"action_menu", "move_menu", "item_menu", "party_menu"}:
            return SkillResult(
                skill_id=SKILL_ID,
                status="blocked",
                summary=f"Battle UI is {battle_ui.kind}; wait for the action or move menu before selecting a move.",
                evidence=evidence + (f"screenshot_battle_ui={battle_ui.kind}",),
                warnings=warnings,
            )

    active = active_party_member(snapshot)
    if not active:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Active battler is unavailable, so the requested move cannot be resolved.",
            evidence=evidence + ("active_party_member=missing",),
            warnings=warnings,
        )

    slot = move_slot(active, requested)
    evidence = evidence + active_move_evidence(snapshot, active, slot)
    if slot is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Active battler does not know {requested.name}.",
            evidence=evidence,
            warnings=warnings,
        )

    if slot.pp <= 0:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"{requested.name} has 0 PP and cannot be selected.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=f"{requested.name} can be selected from active move slot {slot.slot}.",
        evidence=evidence,
        warnings=warnings,
    )


def classify_use_move_result(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any],
    requested: "ResolvedMove",
    screenshot_path: str | Path | None,
    evidence: tuple[str, ...],
    warnings: tuple[str, ...],
) -> SkillResult:
    before_active = active_party_member(before_snapshot)
    if not before_active:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Before snapshot is missing the active battler.",
            evidence=evidence + ("before_active_party_member=missing",),
            warnings=warnings,
        )

    before_slot = move_slot(before_active, requested)
    if before_slot is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Before snapshot active battler does not know {requested.name}.",
            evidence=evidence + ("before_requested_move=missing",),
            warnings=warnings,
        )

    before_active_slot = before_snapshot.get("active_party_slot")
    after_member = party_member_by_slot(snapshot, before_active_slot)
    after_slot = move_slot(after_member, requested) if after_member else None
    before_enemy_hp = enemy_hp(before_snapshot)
    after_enemy_hp = enemy_hp(snapshot)
    evidence = evidence + (
        f"before_active_party_slot={before_active_slot}",
        f"requested_move_slot={before_slot.slot}",
        f"before_pp={before_slot.pp}",
        f"after_pp={after_slot.pp if after_slot else 'missing'}",
        f"before_enemy_hp={before_enemy_hp}",
        f"after_enemy_hp={after_enemy_hp}",
    )

    if after_slot and after_slot.pp < before_slot.pp:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=f"{requested.name} was used; PP decreased from {before_slot.pp} to {after_slot.pp}.",
            evidence=evidence + (f"pp_delta={after_slot.pp - before_slot.pp}",),
            warnings=warnings,
        )

    if screenshot_path and battle_dialogue_visible(screenshot_path):
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Move result dialogue is still visible; wait for PP or battle state to settle.",
            evidence=evidence + ("screenshot=battle_dialogue",),
            warnings=warnings,
        )

    if after_enemy_hp is not None and before_enemy_hp is not None and after_enemy_hp < before_enemy_hp:
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Enemy HP decreased, but requested move PP did not show a matching delta.",
            evidence=evidence + (f"enemy_hp_delta={after_enemy_hp - before_enemy_hp}",),
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary=f"{requested.name} execution did not produce a confirmed PP delta.",
        evidence=evidence,
        warnings=warnings,
    )


class ResolvedMove:
    def __init__(self, move_id: int) -> None:
        self.move_id = move_id
        self.name = move_name(move_id)


class MoveSlot:
    def __init__(self, slot: int, pp: int) -> None:
        self.slot = slot
        self.pp = pp


def resolve_requested_move(value: str | int) -> ResolvedMove:
    return ResolvedMove(resolve_move(value))


def active_party_member(snapshot: Mapping[str, Any]) -> Mapping[str, Any] | None:
    active = snapshot.get("active_party_member")
    if isinstance(active, Mapping):
        return active
    return party_member_by_slot(snapshot, snapshot.get("active_party_slot"))


def party_member_by_slot(snapshot: Mapping[str, Any], slot: object) -> Mapping[str, Any] | None:
    if not isinstance(slot, int):
        return None
    party = snapshot.get("party", ())
    if not isinstance(party, list):
        return None
    for member in party:
        if isinstance(member, Mapping) and member.get("slot") == slot:
            return member
    return None


def move_slot(member: Mapping[str, Any] | None, requested: ResolvedMove) -> MoveSlot | None:
    if member is None:
        return None
    moves = member.get("moves", ())
    if not isinstance(moves, list):
        return None
    for index, move in enumerate(moves, start=1):
        if not isinstance(move, Mapping):
            continue
        if move.get("move_id") == requested.move_id or str(move.get("move_name", "")).lower() == requested.name.lower():
            return MoveSlot(slot=index, pp=int(move.get("pp", 0)))
    return None


def active_move_evidence(
    snapshot: Mapping[str, Any],
    active: Mapping[str, Any],
    slot: MoveSlot | None,
) -> tuple[str, ...]:
    active_slot = snapshot.get("active_party_slot")
    active_species = active.get("species_name", "unknown")
    moves = active.get("moves", ())
    names = []
    if isinstance(moves, list):
        names = [str(move.get("move_name", "")) for move in moves if isinstance(move, Mapping)]
    return (
        f"active_party_slot={active_slot}",
        f"active_species={active_species}",
        f"active_moves={','.join(name for name in names if name)}",
        f"requested_move_slot={slot.slot if slot else 'missing'}",
        f"requested_move_pp={slot.pp if slot else 'missing'}",
    )


def base_evidence(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
    )


def enemy_hp(snapshot: Mapping[str, Any]) -> int | None:
    enemy = snapshot.get("enemy")
    if not isinstance(enemy, Mapping):
        return None
    value = enemy.get("hp")
    return int(value) if isinstance(value, int) else None


def battle_dialogue_visible(path: str | Path) -> bool:
    return inspect_battle_ui_screenshot(path).kind == "dialogue"
