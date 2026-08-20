from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.visual_state import inspect_ui_visual_state


SKILL_ID = "choose_starter"
StarterChoice = Literal["bulbasaur", "charmander", "squirtle"]
STARTER_SPECIES = {
    "bulbasaur": "Bulbasaur",
    "charmander": "Charmander",
    "squirtle": "Squirtle",
}


def choose_starter(
    snapshot: Mapping[str, Any],
    *,
    starter: str = "squirtle",
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    normalized = normalize_starter(starter)
    evidence = base_evidence(snapshot, starter=normalized)
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))

    if normalized is None:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary=f"Unknown starter choice: {starter!r}.",
            evidence=evidence,
            warnings=warnings,
        )

    if before_snapshot is not None:
        return classify_choose_starter_result(
            snapshot,
            before_snapshot=before_snapshot,
            starter=normalized,
            evidence=evidence,
            warnings=warnings,
        )

    position = snapshot.get("position") if isinstance(snapshot.get("position"), Mapping) else {}
    if position.get("map_id") != 0x28:
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Starter selection requires Oak's Lab.",
            evidence=evidence,
            warnings=warnings,
        )

    if snapshot.get("battle_type_raw") not in {None, 0} or snapshot.get("mode") == "battle":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Starter selection is unavailable while a battle is active.",
            evidence=evidence,
            warnings=warnings,
        )

    if party_species(snapshot):
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="A party Pokemon is already present; starter selection appears complete.",
            evidence=evidence + ("party_present=true",),
            warnings=warnings,
        )

    visual = inspect_ui_visual_state(screenshot_path)
    if visual.bottom_text_box or snapshot.get("mode") in {"overworld", "dialogue", "menu_or_dialogue_uncertain"}:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=f"{STARTER_SPECIES[normalized]} can be selected from Oak's Lab starter surface.",
            evidence=evidence
            + (
                f"visual_bottom_text_box={visual.bottom_text_box}",
                f"visual_upper_menu={visual.upper_menu}",
            ),
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary="Oak's Lab is active, but the starter selection surface is not clearly visible.",
        evidence=evidence
        + (
            f"visual_bottom_text_box={visual.bottom_text_box}",
            f"visual_upper_menu={visual.upper_menu}",
        ),
        warnings=warnings,
    )


def classify_choose_starter_result(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any],
    starter: StarterChoice,
    evidence: tuple[str, ...],
    warnings: tuple[str, ...],
) -> SkillResult:
    before_party = party_species(before_snapshot)
    after_party = party_species(snapshot)
    expected = STARTER_SPECIES[starter]
    evidence = evidence + (
        "before_party=" + ",".join(before_party),
        "after_party=" + ",".join(after_party),
        f"expected_species={expected}",
    )

    if expected in after_party and expected not in before_party:
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary=f"{expected} was added to the party.",
            evidence=evidence,
            warnings=warnings,
        )

    if after_party and expected not in after_party:
        return SkillResult(
            skill_id=SKILL_ID,
            status="failed",
            summary=f"A starter was selected, but it was not {expected}.",
            evidence=evidence,
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary=f"{expected} was not confirmed in the party after starter selection.",
        evidence=evidence,
        warnings=warnings,
    )


def normalize_starter(value: str) -> StarterChoice | None:
    normalized = str(value).strip().lower()
    aliases = {
        "bulba": "bulbasaur",
        "bulbasaur": "bulbasaur",
        "charmander": "charmander",
        "char": "charmander",
        "squirtle": "squirtle",
        "squirt": "squirtle",
    }
    resolved = aliases.get(normalized)
    if resolved in STARTER_SPECIES:
        return resolved  # type: ignore[return-value]
    return None


def party_species(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    party = snapshot.get("party")
    if not isinstance(party, list):
        return ()
    species: list[str] = []
    for member in party:
        if not isinstance(member, Mapping):
            continue
        name = str(member.get("species_name", ""))
        if name and not name.startswith("Species 0x00"):
            species.append(name)
    return tuple(species)


def base_evidence(snapshot: Mapping[str, Any], *, starter: str | None) -> tuple[str, ...]:
    position = snapshot.get("position") if isinstance(snapshot.get("position"), Mapping) else {}
    return (
        f"mode={snapshot.get('mode', 'unknown')}",
        f"battle_type_raw={snapshot.get('battle_type_raw')}",
        f"map_id={position.get('map_id', 'unknown')}",
        f"x={position.get('x', 'unknown')}",
        f"y={position.get('y', 'unknown')}",
        f"starter={starter}",
    )
