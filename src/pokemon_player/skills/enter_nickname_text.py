from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.handle_nickname_prompt import screenshot_has_naming_screen


SKILL_ID = "enter_nickname_text"
SUPPORTED_NICKNAME = re.compile(r"^[A-Z]{1,10}$")


def enter_nickname_text(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
    nickname: str = "",
) -> SkillResult:
    target = nickname.strip().upper()
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    naming_screen = screenshot_has_naming_screen(screenshot_path)
    evidence = (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"nickname={target}",
        f"naming_screen={naming_screen}",
    )

    if not SUPPORTED_NICKNAME.fullmatch(target):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Nickname entry v0 supports uppercase A-Z nicknames from 1 to 10 characters.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        evidence = evidence + (
            f"before_mode={before_snapshot.get('mode', 'unknown')}",
            f"before_battle_type_raw={before_snapshot.get('battle_type_raw')}",
        )
        if party_has_nickname(snapshot, target):
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary=f"Nickname {target} was committed to party data.",
                evidence=evidence + (f"party_nickname={target}",),
                warnings=warnings,
            )
        if naming_screen:
            return SkillResult(
                skill_id=SKILL_ID,
                status="uncertain",
                summary="Naming keyboard is still active after text-entry inputs.",
                evidence=evidence,
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="uncertain",
            summary=f"Naming screen closed, but nickname {target} was not found in party data.",
            evidence=evidence + tuple(party_nickname_evidence(snapshot)),
            warnings=warnings,
        )

    if not naming_screen:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Naming keyboard is not active.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="succeeded",
        summary=f"Naming keyboard is ready to enter {target}.",
        evidence=evidence,
        warnings=warnings,
    )


def party_has_nickname(snapshot: Mapping[str, Any], nickname: str) -> bool:
    return nickname in party_nickname_evidence(snapshot)


def party_nickname_evidence(snapshot: Mapping[str, Any]) -> list[str]:
    party = snapshot.get("party")
    if not isinstance(party, list):
        return []
    names: list[str] = []
    for member in party:
        if not isinstance(member, Mapping):
            continue
        raw = member.get("nickname")
        if raw:
            names.append(str(raw).upper())
    return names
