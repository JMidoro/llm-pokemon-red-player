from __future__ import annotations

import re
from typing import Any

from pokemon_player.nuzlocke_data import canonical_area, family_id, species_dex_number
from pokemon_player.nuzlocke_ledger import NuzlockeLedger
from pokemon_player.nuzlocke_policy import encounter_assessment
from pokemon_player.nuzlocke_rules import NuzlockeRuleset


def _normalize_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _owned(snapshot: dict[str, Any]) -> set[int]:
    values = snapshot.get("pokedex_owned_dex_numbers")
    if not isinstance(values, list):
        return set()
    result: set[int] = set()
    for value in values:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _party(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    values = snapshot.get("party")
    if not isinstance(values, list):
        return []
    # During post-catch registration, Gen I increments party count before it
    # finishes populating the new party struct. Do not turn that temporary
    # species-0/HP-0 slot into a captured-and-dead Pokemon in the ledger.
    return [
        value
        for value in values
        if isinstance(value, dict)
        and value.get("species_id") not in {None, 0, 0xFF}
        and int(value.get("max_hp", 0) or 0) > 0
    ]


def _member_family(member: dict[str, Any]) -> str | None:
    dex = species_dex_number(member.get("species_id"))
    if dex is not None:
        return family_id(dex)
    try:
        return f"internal-species-{int(member.get('species_id')):03d}"
    except (TypeError, ValueError):
        return None


def _existing_pokemon_id(
    ledger: NuzlockeLedger,
    member: dict[str, Any],
) -> str | None:
    nickname = _normalize_name(member.get("nickname"))
    member_family = _member_family(member)
    if nickname:
        for pokemon_id, record in ledger.state["pokemon"].items():
            if (
                nickname == _normalize_name(record.get("nickname"))
                and member_family == record.get("familyId")
            ):
                return str(pokemon_id)
    for pokemon_id, record in ledger.state["pokemon"].items():
        if (
            record.get("location") == "party"
            and record.get("slot") == member.get("slot")
            and record.get("familyId") == member_family
        ):
            return str(pokemon_id)
    # A full-party capture has no party nickname/slot evidence until it is withdrawn. The
    # evolutionary-family clause normally makes this candidate unique; only join it when the
    # ledger has exactly one non-party record in the family so identity is never guessed.
    non_party_candidates = [
        str(pokemon_id)
        for pokemon_id, record in ledger.state["pokemon"].items()
        if record.get("location") != "party" and record.get("familyId") == member_family
    ]
    if len(non_party_candidates) == 1:
        return non_party_candidates[0]
    return None


def _new_pokemon_id(ledger: NuzlockeLedger, member: dict[str, Any] | None, dex: int | None) -> str:
    raw_name = (member or {}).get("nickname") or (member or {}).get("species_name") or (
        f"dex-{dex:03d}" if dex is not None else "pokemon"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", str(raw_name).lower()).strip("-") or "pokemon"
    base = f"{slug}-{len(ledger.state['pokemon']) + 1:03d}"
    candidate = base
    suffix = 2
    while candidate in ledger.state["pokemon"]:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _last_checkpoint_owned(ledger: NuzlockeLedger) -> set[int]:
    for event in reversed(ledger.events):
        if event.get("type") != "checkpoint_observed" or not isinstance(event.get("data"), dict):
            continue
        values = event["data"].get("ownedDexNumbers")
        if isinstance(values, list):
            return {int(value) for value in values}
    return set()


def _capture_success(
    active: dict[str, Any],
    snapshot: dict[str, Any],
    previous_owned: set[int],
) -> bool:
    dex = active.get("speciesDex")
    if isinstance(dex, int) and dex in (_owned(snapshot) - previous_owned):
        return True
    family = active.get("familyId")
    return (
        family is not None
        and not bool(active.get("historicalFamilyKnown"))
        and any(_member_family(member) == family for member in _party(snapshot))
    )


def _acquisition_area(
    ruleset: NuzlockeRuleset,
    snapshot: dict[str, Any],
    *,
    fallback_id: str,
    fallback_name: str,
) -> tuple[str, str]:
    area = canonical_area(
        snapshot.get("position") if isinstance(snapshot.get("position"), dict) else None,
        ruleset.area_aliases,
    )
    if not area:
        return fallback_id, fallback_name
    return str(area["id"]), str(area["mapName"])


def _configured_acquisition_source(
    ruleset: NuzlockeRuleset,
    snapshot: dict[str, Any],
    dex: int | None,
) -> str | None:
    position = snapshot.get("position") if isinstance(snapshot.get("position"), dict) else {}
    try:
        map_id = int(position.get("map_id"))
    except (TypeError, ValueError):
        map_id = None
    for collection, source in (("giftEncounters", "gift"), ("staticEncounters", "static")):
        values = ruleset.raw.get(collection)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            if value.get("mapId") is not None and int(value["mapId"]) != map_id:
                continue
            if value.get("speciesDex") is not None and int(value["speciesDex"]) != dex:
                continue
            return source
    return None


def reconcile_snapshot(
    ledger: NuzlockeLedger,
    ruleset: NuzlockeRuleset,
    snapshot: dict[str, Any],
    *,
    checkpoint_id: str,
    snapshot_hash: str | None = None,
    last_action: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if ledger.has_checkpoint(checkpoint_id):
        return []
    appended: list[dict[str, Any]] = []
    has_prior_checkpoint = any(
        event.get("type") == "checkpoint_observed" for event in ledger.events
    )
    previous_owned = _last_checkpoint_owned(ledger)
    owned_now = _owned(snapshot)
    new_owned = owned_now - previous_owned if has_prior_checkpoint else set()
    active = ledger.state.get("activeEncounter")
    resolved_capture_source: str | None = None
    assessment = encounter_assessment(ruleset, ledger.state, snapshot)
    same_encounter = bool(
        isinstance(active, dict)
        and assessment.get("eligible") is not None
        and snapshot.get("mode") == "battle"
        and active.get("areaId") == (assessment.get("area") or {}).get("id")
        and active.get("familyId") == assessment.get("familyId")
    )
    if isinstance(active, dict) and not same_encounter:
        caught = _capture_success(
            active,
            snapshot,
            previous_owned,
        )
        consumes = bool(active.get("consumesArea")) and (
            caught or bool(ruleset.encounter.get("failedEligibleEncounterConsumesArea"))
        )
        outcome = "caught" if caught else "failed"
        if caught:
            resolved_capture_source = str(active.get("source") or "wild")
        appended.append(
            ledger.append(
                "encounter_resolved",
                {
                    **active,
                    "outcome": outcome,
                    "consumesArea": consumes,
                },
                evidence=(f"checkpoint={checkpoint_id}",),
                source="checkpoint_reconciliation",
            )
        )
        active = None

    if snapshot.get("mode") == "battle" and snapshot.get("battle_type_raw") == 1 and not same_encounter:
        area = assessment.get("area") or {}
        encounter = {
            "areaId": area.get("id"),
            "areaName": area.get("mapName"),
            "source": assessment.get("source"),
            "speciesId": assessment.get("speciesId"),
            "speciesName": assessment.get("speciesName"),
            "speciesDex": assessment.get("speciesDex"),
            "familyId": assessment.get("familyId"),
            "duplicate": assessment.get("duplicate"),
            "historicalFamilyKnown": assessment.get("historicalFamilyKnown"),
            "eligible": assessment.get("eligible"),
            "consumesArea": assessment.get("consumesArea"),
            "reason": assessment.get("reason"),
        }
        appended.append(
            ledger.append(
                "encounter_observed",
                encounter,
                evidence=(f"checkpoint={checkpoint_id}",),
                source="checkpoint_reconciliation",
            )
        )

    action_skill = str((last_action or {}).get("skillId") or "")
    observed_pokemon_ids: set[str] = set()
    for member in _party(snapshot):
        pokemon_id = _existing_pokemon_id(ledger, member)
        member_dex = species_dex_number(member.get("species_id"))
        member_family = _member_family(member)
        if pokemon_id is None:
            pokemon_id = _new_pokemon_id(ledger, member, member_dex)
            provenance = "observed_existing"
            source = "unknown"
            configured_source = (
                _configured_acquisition_source(ruleset, snapshot, member_dex)
                if has_prior_checkpoint
                else None
            )
            if action_skill == "choose_starter" or configured_source == "gift":
                provenance, source = "capture", "gift"
            elif member_dex in new_owned:
                provenance = "capture"
                source = resolved_capture_source or configured_source or "wild"
            appended.append(
                ledger.append(
                    "pokemon_registered",
                    {
                        "pokemonId": pokemon_id,
                        "nickname": member.get("nickname"),
                        "speciesId": member.get("species_id"),
                        "speciesName": member.get("species_name"),
                        "speciesDex": member_dex,
                        "familyId": member_family,
                        "provenance": provenance,
                        "encounterSource": source,
                        "status": "alive",
                        "location": "party",
                        "slot": member.get("slot"),
                        "level": member.get("level"),
                    },
                    evidence=(f"checkpoint={checkpoint_id}",),
                    source="checkpoint_reconciliation",
                )
            )
            if source == "gift":
                area_id, area_name = _acquisition_area(
                    ruleset,
                    snapshot,
                    fallback_id="gift",
                    fallback_name="Gift Pokemon",
                )
                appended.append(
                    ledger.append(
                        "encounter_resolved",
                        {
                            "areaId": area_id,
                            "areaName": area_name,
                            "source": "gift",
                            "outcome": "caught",
                            "speciesDex": member_dex,
                            "familyId": member_family,
                            "consumesArea": bool(ruleset.encounter.get("giftConsumesArea")),
                        },
                        source="checkpoint_reconciliation",
                    )
                )
        else:
            appended.append(
                ledger.append(
                    "pokemon_observed",
                    {
                        "pokemonId": pokemon_id,
                        "nickname": member.get("nickname"),
                        "speciesId": member.get("species_id"),
                        "speciesName": member.get("species_name"),
                        "speciesDex": member_dex,
                        "familyId": member_family,
                        "location": "party",
                        "slot": member.get("slot"),
                        "level": member.get("level"),
                        "hp": member.get("hp"),
                    },
                    source="checkpoint_reconciliation",
                )
            )
        observed_pokemon_ids.add(pokemon_id)
        record = ledger.state["pokemon"].get(pokemon_id, {})
        if int(member.get("hp") or 0) <= 0 and record.get("status") != "dead":
            appended.append(
                ledger.append(
                    "death_registered",
                    {
                        "pokemonId": pokemon_id,
                        "nickname": member.get("nickname"),
                        "speciesName": member.get("species_name"),
                        "checkpointId": checkpoint_id,
                    },
                    evidence=("party_hp=0",),
                    source="checkpoint_reconciliation",
                )
            )

    for pokemon_id, record in list(ledger.state["pokemon"].items()):
        if record.get("location") != "party" or pokemon_id in observed_pokemon_ids:
            continue
        appended.append(
            ledger.append(
                "pokemon_observed",
                {
                    "pokemonId": pokemon_id,
                    "location": "not_in_party",
                    "slot": None,
                },
                evidence=("absent_from_checkpoint_party",),
                source="checkpoint_reconciliation",
            )
        )

    registered_dex = {
        int(record["speciesDex"])
        for record in ledger.state["pokemon"].values()
        if isinstance(record.get("speciesDex"), int)
    }
    owned_to_register = new_owned if has_prior_checkpoint else owned_now
    for dex in sorted(owned_to_register - registered_dex):
        pokemon_id = _new_pokemon_id(ledger, None, dex)
        configured_source = (
            _configured_acquisition_source(ruleset, snapshot, dex)
            if has_prior_checkpoint
            else None
        )
        acquisition_source = (
            resolved_capture_source
            or configured_source
            or ("wild" if action_skill == "attempt_catch" else "unknown")
        )
        provenance = (
            "capture"
            if action_skill == "attempt_catch" or acquisition_source in {"gift", "static"}
            else "observed_owned"
        )
        appended.append(
            ledger.append(
                "pokemon_registered",
                {
                    "pokemonId": pokemon_id,
                    "nickname": None,
                    "speciesId": None,
                    "speciesName": f"Pokedex #{dex}",
                    "speciesDex": dex,
                    "familyId": family_id(dex),
                    "provenance": provenance,
                    "encounterSource": acquisition_source,
                    "status": "alive",
                    "location": "box",
                    "slot": None,
                    "level": None,
                },
                evidence=("new_pokedex_owned_flag", "party_slot_not_present"),
                source="checkpoint_reconciliation",
            )
        )
        if acquisition_source == "gift":
            area_id, area_name = _acquisition_area(
                ruleset,
                snapshot,
                fallback_id="gift",
                fallback_name="Gift Pokemon",
            )
            appended.append(
                ledger.append(
                    "encounter_resolved",
                    {
                        "areaId": area_id,
                        "areaName": area_name,
                        "source": "gift",
                        "outcome": "caught",
                        "speciesDex": dex,
                        "familyId": family_id(dex),
                        "consumesArea": bool(ruleset.encounter.get("giftConsumesArea")),
                    },
                    source="checkpoint_reconciliation",
                )
            )

    badge_names = snapshot.get("badge_names") if isinstance(snapshot.get("badge_names"), list) else []
    for badge in badge_names:
        if str(badge) not in ledger.state["badges"]:
            appended.append(
                ledger.append(
                    "badge_observed",
                    {"badge": str(badge), "checkpointId": checkpoint_id},
                    source="checkpoint_reconciliation",
                )
            )

    party = _party(snapshot)
    if party and all(int(member.get("hp") or 0) <= 0 for member in party) and not ledger.state["gameOver"]:
        game_over = ruleset.raw.get("blackout", {}).get("behavior") == "game_over"
        appended.append(
            ledger.append(
                "blackout",
                {"gameOver": game_over, "checkpointId": checkpoint_id},
                evidence=("all_observed_party_hp_zero",),
                source="checkpoint_reconciliation",
            )
        )

    appended.append(
        ledger.append(
            "checkpoint_observed",
            {
                "checkpointId": checkpoint_id,
                "snapshotHash": snapshot_hash,
                "ownedDexNumbers": sorted(_owned(snapshot)),
                "partyCount": len(party),
                "mode": snapshot.get("mode"),
            },
            source="checkpoint_reconciliation",
        )
    )
    return appended
