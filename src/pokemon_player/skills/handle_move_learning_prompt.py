from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pokemon_player.catalog import normalize_name
from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "handle_move_learning_prompt"
MoveLearningChoice = Literal["skip", "replace"]


def handle_move_learning_prompt(
    snapshot: Mapping[str, Any],
    *,
    choice: MoveLearningChoice,
    forget_move: str | int | None = None,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    prompt = screenshot_has_move_learning_prompt(snapshot, screenshot_path)
    before_member = active_member(before_snapshot or snapshot)
    before_moves = move_options(before_member)
    target_move = resolve_move(before_moves, forget_move) if choice == "replace" else None
    evidence = (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"move_learning_prompt={prompt}",
        f"choice={choice}",
        f"forget_move={forget_move}",
        f"moves={','.join(move['name'] for move in before_moves)}",
    )

    if choice not in {"skip", "replace"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unsupported move-learning choice: {choice}.",
            evidence=evidence,
            warnings=warnings,
        )
    if choice == "replace" and target_move is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Replacing a move requires the name or slot of one current move.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        after_member = member_for_slot(snapshot, before_member.get("slot") if before_member else None)
        after_moves = move_options(after_member)
        before_ids = tuple(move["id"] for move in before_moves)
        after_ids = tuple(move["id"] for move in after_moves)
        evidence = evidence + (
            f"before_move_ids={before_ids}",
            f"after_move_ids={after_ids}",
        )
        if prompt:
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary="Move-learning prompt is still visible after the response.",
                evidence=evidence,
                warnings=warnings,
            )
        if choice == "skip" and after_ids == before_ids:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Declined the new move and preserved the current moveset.",
                evidence=evidence,
                warnings=warnings,
            )
        if (
            choice == "replace"
            and target_move is not None
            and after_ids != before_ids
            and target_move["id"] not in after_ids
        ):
            learned = next((move["name"] for move in after_moves if move["id"] not in before_ids), "new move")
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Forgot {target_move['name']} and learned {learned}.",
                evidence=evidence + (f"learned_move={learned}",),
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Move-learning response ended without a verified moveset outcome.",
            evidence=evidence,
            warnings=warnings,
        )

    if not prompt:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="No four-move overwrite prompt is visible.",
            evidence=evidence,
            warnings=warnings,
        )
    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=(
            "Move-learning prompt is ready; skip the new move."
            if choice == "skip"
            else f"Move-learning prompt is ready; replace {target_move['name']}."
        ),
        evidence=evidence,
        warnings=warnings,
    )


def screenshot_has_move_learning_prompt(
    snapshot: Mapping[str, Any],
    screenshot_path: str | Path | None,
) -> bool:
    if screenshot_path is None:
        return False
    visual = inspect_ui_visual_state(screenshot_path)
    enemy = snapshot.get("enemy") if isinstance(snapshot.get("enemy"), Mapping) else {}
    return (
        snapshot.get("mode") == "battle"
        and snapshot.get("battle_type_raw") not in {None, 0}
        and int(enemy.get("hp", 0) or 0) <= 0
        and len(move_options(active_member(snapshot))) == 4
        and visual.bottom_text_box
        and visual.compact_choice
    )


def active_member(snapshot: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not snapshot:
        return None
    member = snapshot.get("active_party_member")
    if isinstance(member, Mapping):
        return member
    return member_for_slot(snapshot, snapshot.get("active_party_slot"))


def member_for_slot(snapshot: Mapping[str, Any], slot: Any) -> Mapping[str, Any] | None:
    party = snapshot.get("party")
    if not isinstance(party, list):
        return None
    return next(
        (member for member in party if isinstance(member, Mapping) and member.get("slot") == slot),
        None,
    )


def move_options(member: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not member or not isinstance(member.get("moves"), list):
        return []
    options = []
    for slot, move in enumerate(member["moves"], start=1):
        if not isinstance(move, Mapping):
            continue
        move_id = int(move.get("move_id", 0) or 0)
        if move_id <= 0:
            continue
        options.append(
            {
                "slot": slot,
                "id": move_id,
                "name": str(move.get("move_name", f"Move {move_id}")),
            }
        )
    return options


def resolve_move(options: list[dict[str, Any]], requested: str | int | None) -> dict[str, Any] | None:
    if isinstance(requested, int):
        return next((move for move in options if move["slot"] == requested or move["id"] == requested), None)
    if requested is None:
        return None
    normalized = normalize_name(str(requested))
    return next((move for move in options if normalize_name(move["name"]) == normalized), None)
