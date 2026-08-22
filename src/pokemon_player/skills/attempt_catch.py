from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.battle_ui import inspect_battle_ui_screenshot
from pokemon_player.skill_result import SkillResult


SKILL_ID = "attempt_catch"
POKE_BALL_ITEM_ID = 0x04
WILD_BATTLE_TYPE = 1


def attempt_catch(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    ball_count = poke_ball_count(snapshot)
    party_signature = party_members(snapshot)
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    evidence = [
        f"mode={mode}",
        f"battle_type_raw={battle_type_raw}",
        f"poke_ball_count={ball_count}",
        f"party_count={len(party_signature)}",
    ]

    if before_snapshot is not None:
        before_balls = poke_ball_count(before_snapshot)
        before_party = party_members(before_snapshot)
        ball_delta = ball_count - before_balls
        party_delta = len(party_signature) - len(before_party)
        evidence.extend(
            [
                f"before_poke_ball_count={before_balls}",
                f"poke_ball_delta={ball_delta}",
                f"before_party_count={len(before_party)}",
                f"party_delta={party_delta}",
            ]
        )

        if party_delta > 0:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="A Pokemon joined the party after the catch attempt.",
                evidence=tuple(evidence),
                warnings=warnings,
            )

        if ball_delta < 0 and party_signature == before_party and is_wild_battle(snapshot):
            return SkillResult(
                skill_id=SKILL_ID,
                status="failed",
                summary="A ball was consumed, but the wild battle continues and party is unchanged.",
                evidence=tuple(evidence),
                warnings=warnings,
            )

        if ball_delta < 0:
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary="A ball was consumed, but catch outcome evidence is incomplete.",
                evidence=tuple(evidence),
                warnings=warnings,
            )

        if screenshot_path and screenshot_has_throw_dialogue(screenshot_path):
            evidence.append("screenshot=battle_dialogue")
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary="Catch-result dialogue is still visible after the throw.",
                evidence=tuple(evidence),
                warnings=warnings,
            )

        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="No ball consumption or party change was observed after execution.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    if screenshot_path and screenshot_has_throw_dialogue(screenshot_path):
        evidence.append("screenshot=battle_dialogue")
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary="Battle dialogue is visible; advance battle dialogue before attempting a catch.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    if is_wild_battle(snapshot) and ball_count <= 0:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="A wild battle is active, but no Poke Balls are available.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    if is_wild_battle(snapshot) and ball_count > 0:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Catch attempt preconditions are satisfied.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary="State is not a stable wild-battle catch attempt or post-throw result.",
        evidence=tuple(evidence),
        warnings=warnings,
    )


def is_wild_battle(snapshot: Mapping[str, Any]) -> bool:
    return snapshot.get("mode") == "battle" and snapshot.get("battle_type_raw") == WILD_BATTLE_TYPE


def poke_ball_count(snapshot: Mapping[str, Any]) -> int:
    inventory = snapshot.get("inventory", ())
    if not isinstance(inventory, list):
        return 0
    for item in inventory:
        if not isinstance(item, Mapping):
            continue
        if item.get("item_id") == POKE_BALL_ITEM_ID or item.get("item_name") == "Poke Ball":
            return int(item.get("quantity", 0))
    return 0


def party_members(snapshot: Mapping[str, Any]) -> tuple[tuple[int, str, str], ...]:
    party = snapshot.get("party", ())
    if not isinstance(party, list):
        return ()
    members: list[tuple[int, str, str]] = []
    for member in party:
        if not isinstance(member, Mapping):
            continue
        members.append(
            (
                int(member.get("slot", 0)),
                str(member.get("species_name", "")),
                str(member.get("nickname", "")),
            )
        )
    return tuple(members)


def screenshot_has_throw_dialogue(path: str | Path) -> bool:
    image_path = Path(path)
    if not image_path.exists():
        return False

    try:
        return inspect_battle_ui_screenshot(image_path).kind == "dialogue"
    except Exception:
        return False
