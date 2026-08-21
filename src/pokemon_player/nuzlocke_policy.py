from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

from pokemon_player.nuzlocke_data import canonical_area, family_id, species_dex_number
from pokemon_player.nuzlocke_ledger import NuzlockeLedger
from pokemon_player.nuzlocke_rules import NuzlockeRuleset


HARD_RULE_VIOLATION = "hard_rule_violation"
STRATEGIC_RISK = "strategic_risk"
MODEL_MISTAKE = "model_mistake"
COMPLIANT = "compliant"


def _normalize_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _enemy(snapshot: dict[str, Any]) -> dict[str, Any]:
    value = snapshot.get("enemy")
    return value if isinstance(value, dict) else {}


def _family_for_species(species_id: Any, dex_number: Any = None) -> str | None:
    try:
        dex = int(dex_number) if dex_number is not None else species_dex_number(int(species_id))
    except (TypeError, ValueError):
        dex = None
    if dex is not None:
        return family_id(dex)
    try:
        return f"internal-species-{int(species_id):03d}"
    except (TypeError, ValueError):
        return None


def _is_wild_battle(snapshot: dict[str, Any]) -> bool:
    # Pokemon Red uses wIsInBattle=1 for wild battles and 2 for trainer battles.
    return snapshot.get("mode") == "battle" and snapshot.get("battle_type_raw") == 1 and bool(_enemy(snapshot))


def _matches_static_rule(
    ruleset: NuzlockeRuleset,
    *,
    map_id: int | None,
    dex_number: int | None,
    player_x: int | None,
    player_y: int | None,
) -> bool:
    values = ruleset.raw.get("staticEncounters")
    if not isinstance(values, list):
        return False
    for value in values:
        if not isinstance(value, dict):
            continue
        expected_map = value.get("mapId")
        expected_dex = value.get("speciesDex")
        if expected_map is not None and int(expected_map) != map_id:
            continue
        if expected_dex is not None and int(expected_dex) != dex_number:
            continue
        positions = value.get("objectPositions")
        if not isinstance(positions, list) or not positions:
            continue
        if player_x is None or player_y is None:
            continue
        for position in positions:
            if not isinstance(position, dict):
                continue
            try:
                object_x = int(position["x"])
                object_y = int(position["y"])
            except (KeyError, TypeError, ValueError):
                continue
            # Static encounters begin while the player faces an adjacent overworld object.
            # This prevents ordinary Power Plant Voltorb battles from being treated as static.
            if abs(player_x - object_x) + abs(player_y - object_y) == 1:
                return True
    return False


def encounter_assessment(
    ruleset: NuzlockeRuleset,
    state: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    area = canonical_area(
        snapshot.get("position") if isinstance(snapshot.get("position"), dict) else None,
        ruleset.area_aliases,
    )
    enemy = _enemy(snapshot)
    species_id = enemy.get("species_id")
    dex_number = species_dex_number(int(species_id)) if isinstance(species_id, int) else None
    current_family = _family_for_species(species_id, dex_number)
    map_id = int(area["mapId"]) if area else None
    try:
        player_x = int(area["x"]) if area and area.get("x") is not None else None
        player_y = int(area["y"]) if area and area.get("y") is not None else None
    except (TypeError, ValueError):
        player_x = player_y = None
    active = state.get("activeEncounter")
    active_source = None
    if (
        isinstance(active, dict)
        and active.get("areaId") == (area or {}).get("id")
        and active.get("familyId") == current_family
    ):
        active_source = str(active.get("source") or "")
    source = active_source or (
        "static"
        if _matches_static_rule(
            ruleset,
            map_id=map_id,
            dex_number=dex_number,
            player_x=player_x,
            player_y=player_y,
        )
        else "wild"
    )
    consumed = bool(area and area["id"] in state.get("encounters", {}))
    duplicate = bool(
        current_family
        and ruleset.encounter.get("duplicateClause") != "none"
        and current_family in state.get("knownFamilies", [])
    )
    consumes_area = source == "wild"
    if source == "static":
        consumes_area = bool(ruleset.encounter.get("staticConsumesArea"))
    eligible = ruleset.enabled and _is_wild_battle(snapshot)
    reason = "eligible_first_encounter"
    if not ruleset.enabled:
        reason = "ruleset_disabled"
    elif not _is_wild_battle(snapshot):
        eligible = False
        reason = "not_a_confirmed_wild_battle"
    elif source == "wild" and duplicate:
        eligible = False
        consumes_area = False
        reason = "duplicate_family_does_not_consume_area"
    elif consumes_area and consumed:
        eligible = False
        reason = "area_encounter_already_consumed"
    elif source == "static":
        reason = "static_encounter_independent_of_area"
    return {
        "area": area,
        "source": source,
        "speciesId": species_id,
        "speciesName": enemy.get("species_name"),
        "speciesDex": dex_number,
        "familyId": current_family,
        "duplicate": duplicate,
        "areaConsumed": consumed,
        "eligible": eligible,
        "consumesArea": consumes_area,
        "reason": reason,
    }


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    classification: str
    code: str
    summary: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "classification": self.classification,
            "code": self.code,
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


def _target_party_member(
    snapshot: dict[str, Any],
    target: Any,
) -> dict[str, Any] | None:
    party = snapshot.get("party") if isinstance(snapshot.get("party"), list) else []
    if isinstance(target, dict):
        target = target.get("slot") or target.get("nickname") or target.get("species") or target.get("name")
    for member in party:
        if not isinstance(member, dict):
            continue
        if isinstance(target, int) and member.get("slot") == target:
            return member
        if str(target).isdigit() and member.get("slot") == int(str(target)):
            return member
        normalized = _normalize_name(target)
        if normalized and normalized in {
            _normalize_name(member.get("nickname")),
            _normalize_name(member.get("species_name")),
        }:
            return member
    return None


def _ledger_record_for_member(
    state: dict[str, Any],
    member: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if member is None:
        return None
    nickname = _normalize_name(member.get("nickname"))
    species_family = _family_for_species(member.get("species_id"))
    for record in state.get("pokemon", {}).values():
        if (
            nickname
            and nickname == _normalize_name(record.get("nickname"))
            and species_family == record.get("familyId")
        ):
            return record
    for record in state.get("pokemon", {}).values():
        if species_family and species_family == record.get("familyId") and record.get("location") == "party":
            if record.get("slot") == member.get("slot"):
                return record
    return None


def assess_action(
    ruleset: NuzlockeRuleset,
    state: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    skill_id: str,
    args: dict[str, Any],
) -> PolicyDecision:
    if not ruleset.enabled:
        return PolicyDecision(True, COMPLIANT, "ruleset_disabled", "Nuzlocke enforcement is disabled.")

    enforcement = ruleset.enforcement
    if skill_id == "literal_button_press" and enforcement.get("blockRawInputBypass", True):
        return PolicyDecision(
            False,
            HARD_RULE_VIOLATION,
            "raw_input_bypasses_rules",
            "Raw controller input is disabled because it can bypass semantic legality guards.",
        )
    if skill_id == "attempt_catch":
        assessment = encounter_assessment(ruleset, state, snapshot)
        if not _is_wild_battle(snapshot):
            return PolicyDecision(
                True,
                MODEL_MISTAKE,
                "catch_without_wild_battle",
                "The catch intention has no confirmed wild encounter; the skill may reject it.",
            )
        if assessment["duplicate"] and enforcement.get("blockIllegalCapture", True):
            return PolicyDecision(
                False,
                HARD_RULE_VIOLATION,
                "duplicate_family_capture",
                "This evolutionary family is already owned; the duplicate does not consume the area.",
                (f"family={assessment['familyId']}",),
            )
        if assessment["areaConsumed"] and assessment["source"] == "wild" and enforcement.get("blockIllegalCapture", True):
            area = assessment.get("area") or {}
            return PolicyDecision(
                False,
                HARD_RULE_VIOLATION,
                "area_encounter_consumed",
                "The current area's wild encounter opportunity has already been consumed.",
                (f"area={area.get('id')}",),
            )

    if skill_id == "handle_nickname_prompt" and ruleset.raw.get("nickname", {}).get("required"):
        choice = str(args.get("choice", args.get("nicknameChoice", "decline"))).lower()
        if choice not in {"accept", "yes", "y", "true", "nickname", "name"} and enforcement.get("blockNicknameRefusal", True):
            return PolicyDecision(
                False,
                HARD_RULE_VIOLATION,
                "nickname_required",
                "Captured Pokemon must receive a nickname.",
            )
    if skill_id == "enter_nickname_text" and ruleset.raw.get("nickname", {}).get("required"):
        nickname = "".join(
            character
            for character in str(args.get("nickname") or "").strip().upper()
            if "A" <= character <= "Z"
        )[:10]
        if not nickname and enforcement.get("blockNicknameRefusal", True):
            return PolicyDecision(
                False,
                HARD_RULE_VIOLATION,
                "nickname_required",
                "Captured Pokemon must receive a non-empty nickname.",
            )
    if skill_id == "choose_starter" and ruleset.raw.get("nickname", {}).get("required"):
        if not str(args.get("nickname") or "").strip() and enforcement.get("blockNicknameRefusal", True):
            return PolicyDecision(
                False,
                HARD_RULE_VIOLATION,
                "starter_nickname_required",
                "The gift starter must receive a nickname.",
            )

    if skill_id in {"reset_game", "restart_from_save", "load_state"}:
        reset_policy = ruleset.raw.get("reset", {}).get("manual")
        reset_allowed = reset_policy == "allowed" or (
            reset_policy == "only_after_game_over" and bool(state.get("gameOver"))
        )
        if not reset_allowed and enforcement.get("blockForbiddenReset", True):
            return PolicyDecision(
                False,
                HARD_RULE_VIOLATION,
                "manual_reset_disallowed",
                "Manual reset is not allowed before a recorded game over.",
            )

    member: dict[str, Any] | None = None
    if skill_id == "switch_party_member":
        member = _target_party_member(snapshot, args.get("target"))
    elif skill_id == "use_move":
        active = snapshot.get("active_party_member")
        member = active if isinstance(active, dict) else None
    if member is not None and enforcement.get("blockDeadBattleUse", True):
        record = _ledger_record_for_member(state, member)
        restricted_ids = {
            str(item.get("pokemonId"))
            for item in state.get("exceptions", [])
            if isinstance(item, dict)
            and item.get("intentionalBattleAllowed") is False
            and item.get("pokemonId")
        }
        if record and str(record.get("pokemonId")) in restricted_ids:
            return PolicyDecision(
                False,
                HARD_RULE_VIOLATION,
                "hm_exception_battle_use",
                "This HM exception Pokemon is restricted to required field use.",
                (f"pokemon={record.get('pokemonId')}",),
            )
        if record and record.get("status") == "dead":
            return PolicyDecision(
                False,
                HARD_RULE_VIOLATION,
                "dead_pokemon_battle_use",
                "A confirmed-dead Pokemon cannot be intentionally used in battle.",
                (f"pokemon={record.get('pokemonId')}",),
            )

    return PolicyDecision(True, COMPLIANT, "allowed", "The action is legal under the active ruleset.")


def strategic_advisories(
    ruleset: NuzlockeRuleset,
    state: dict[str, Any],
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    advisories: list[dict[str, Any]] = []
    caps = ruleset.raw.get("levelCaps", {})
    if caps.get("mode") == "advisory":
        levels = caps.get("badgeAceLevels") if isinstance(caps.get("badgeAceLevels"), list) else []
        badge_count = len(state.get("badges", []))
        if badge_count < len(levels):
            cap = int(levels[badge_count])
            party = snapshot.get("party") if isinstance(snapshot.get("party"), list) else []
            over = [
                str(member.get("nickname") or member.get("species_name") or "unknown")
                for member in party
                if isinstance(member, dict) and int(member.get("level") or 0) > cap
            ]
            if over:
                advisories.append(
                    {
                        "classification": STRATEGIC_RISK,
                        "code": "advisory_level_cap_exceeded",
                        "summary": f"Advisory level cap is {cap}; over-cap party members: {', '.join(over)}.",
                        "hardBlock": False,
                    }
                )
    restricted_ids = {
        str(item.get("pokemonId"))
        for item in state.get("exceptions", [])
        if isinstance(item, dict) and item.get("placeAtBack") and item.get("pokemonId")
    }
    party = snapshot.get("party") if isinstance(snapshot.get("party"), list) else []
    for member in party:
        if not isinstance(member, dict):
            continue
        record = _ledger_record_for_member(state, member)
        if (
            record
            and str(record.get("pokemonId")) in restricted_ids
            and member.get("slot") != len(party)
        ):
            advisories.append(
                {
                    "classification": STRATEGIC_RISK,
                    "code": "hm_exception_carrier_not_at_back",
                    "summary": "The field-only HM exception carrier should remain at the back of the party.",
                    "hardBlock": False,
                }
            )
    return advisories


def filter_skill_availability(
    ruleset: NuzlockeRuleset,
    state: dict[str, Any],
    snapshot: dict[str, Any],
    skills: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    filtered: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    nickname_required = bool(ruleset.raw.get("nickname", {}).get("required"))
    available_ids = {str(skill.get("id") or "") for skill in skills}
    nickname_flow = nickname_required and bool(
        available_ids & {"handle_nickname_prompt", "enter_nickname_text"}
    )
    for skill in skills:
        skill_id = str(skill.get("id") or "")
        decision = assess_action(
            ruleset,
            state,
            snapshot,
            skill_id=skill_id,
            args={},
        )
        # Argument-dependent skills remain visible and are checked again after the Director fills
        # their arguments. Catch legality is fully knowable at availability time.
        if not decision.allowed and skill_id in {"attempt_catch", "literal_button_press"}:
            decisions.append({"skillId": skill_id, **decision.to_dict()})
            continue
        if nickname_flow and skill_id in {
            "advance_dialogue",
            "advance_battle_dialogue",
            "resolve_battle_outcome_dialogue_bundle",
        }:
            decisions.append(
                {
                    "skillId": skill_id,
                    "allowed": False,
                    "classification": HARD_RULE_VIOLATION,
                    "code": "nickname_flow_requires_semantic_handler",
                    "summary": "Generic dialogue input is hidden during the required nickname flow.",
                    "evidence": [],
                }
            )
            continue
        adjusted = deepcopy(skill)
        params = adjusted.get("params") if isinstance(adjusted.get("params"), dict) else {}
        if nickname_required and skill_id == "choose_starter":
            params = deepcopy(params)
            args_schema = params.get("argsSchema") if isinstance(params.get("argsSchema"), dict) else {}
            params["argsSchema"] = {
                **args_schema,
                "nickname": "required uppercase A-Z nickname, 1 to 10 characters",
            }
            params["requiredArgs"] = ["starter", "nickname"]
            params["exampleArgs"] = {"starter": "squirtle", "nickname": "SHELL"}
            params["nicknamePolicy"] = "A nickname is required by the active ruleset."
            adjusted["params"] = params
        elif nickname_required and skill_id == "handle_nickname_prompt":
            params = deepcopy(params)
            params["choices"] = ["accept"]
            params["defaultChoice"] = "accept"
            params["exampleArgs"] = {"choice": "accept"}
            adjusted["params"] = params
        filtered.append(adjusted)
    return filtered, decisions


def director_rules_context(
    ruleset: NuzlockeRuleset,
    ledger: NuzlockeLedger,
    snapshot: dict[str, Any],
    *,
    availability_decisions: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    summary = ledger.public_summary()
    return {
        "ruleset": ruleset.public_summary(),
        "lineage": {
            "lineageId": summary["lineageId"],
            "gameOver": summary["gameOver"],
            "consumedAreas": summary["consumedAreas"],
            "nextEligibleAreas": summary["nextEligibleAreas"],
            "deaths": summary["deaths"],
            "exceptions": summary["exceptions"],
        },
        "currentEncounter": encounter_assessment(ruleset, ledger.state, snapshot),
        "hardGuardDecisions": list(availability_decisions),
        "strategicAdvisories": strategic_advisories(ruleset, ledger.state, snapshot),
        "instruction": (
            "Hard guards enforce only objective legality. Strategic advisories do not remove "
            "your discretion over tactics, party order, training, or item use."
        ),
    }


def public_lineage_context(
    ruleset: NuzlockeRuleset,
    ledger: NuzlockeLedger,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = ledger.public_summary()
    if snapshot is not None:
        summary["currentEncounterAssessment"] = encounter_assessment(
            ruleset,
            ledger.state,
            snapshot,
        )
        summary["strategicAdvisories"] = strategic_advisories(
            ruleset,
            ledger.state,
            snapshot,
        )
    else:
        summary["currentEncounterAssessment"] = None
        summary["strategicAdvisories"] = []
    return summary


def record_guard_decision(
    ledger: NuzlockeLedger,
    decision: PolicyDecision,
    *,
    skill_id: str,
    action_index: int | None = None,
) -> None:
    ledger.append(
        "guard_decision",
        {
            "skillId": skill_id,
            "actionIndex": action_index,
            **decision.to_dict(),
        },
        evidence=decision.evidence,
        source="pre_input_guard",
    )


def authorize_hm_softlock_exception(
    ledger: NuzlockeLedger,
    ruleset: NuzlockeRuleset,
    *,
    kind: str,
    pokemon_id: str,
    move: str,
    reason: str,
    required_progression: bool,
) -> dict[str, Any]:
    policy = ruleset.raw.get("hmSoftlock", {})
    if kind not in {"dead_field_only_carrier", "out_of_encounter_utility_capture"}:
        raise ValueError("Unsupported HM softlock exception kind.")
    if policy.get("requiredProgressionOnly") and not required_progression:
        raise ValueError("HM exceptions are limited to required progression.")
    if not str(reason).strip():
        raise ValueError("HM exceptions require a recorded reason.")
    event = ledger.append(
        "exception_recorded",
        {
            "kind": kind,
            "pokemonId": pokemon_id,
            "move": move,
            "reason": reason,
            "requiredProgression": required_progression,
            "fieldUseOnly": True,
            "intentionalBattleAllowed": False,
            "placeAtBack": bool(policy.get("placeAtBack")),
            "removeAtNextPc": bool(policy.get("removeAtNextPc")),
        },
        evidence=("living_legal_options_exhausted",),
        source="hm_softlock_policy",
    )
    return event


def blocked_skill_result(skill_id: str, decision: PolicyDecision) -> dict[str, Any]:
    return {
        "actionStarted": False,
        "skillId": skill_id,
        "status": "blocked",
        "summary": decision.summary,
        "evidence": list(decision.evidence),
        "warnings": [decision.code],
        "policyDecision": deepcopy(decision.to_dict()),
    }
