from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from pokemon_player.durable_io import atomic_write_json, read_json, utc_now
from pokemon_player.nuzlocke_rules import NuzlockeRuleset


LEDGER_SCHEMA = "nuzlocke_lineage_ledger_v1"
EVENT_SCHEMA = "nuzlocke_lineage_event_v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def event_stream_digest(ruleset_digest: str, events: Iterable[dict[str, Any]]) -> str:
    value = {"rulesetDigest": ruleset_digest, "events": list(events)}
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def state_digest(state: dict[str, Any]) -> str:
    return sha256(_canonical_json(state).encode("utf-8")).hexdigest()


def initial_lineage_state(ruleset: NuzlockeRuleset) -> dict[str, Any]:
    return {
        "schema": "nuzlocke_lineage_state_v1",
        "rulesetId": ruleset.id,
        "rulesetVersion": ruleset.version,
        "encounters": {},
        "activeEncounter": None,
        "pokemon": {},
        "knownSpecies": [],
        "knownFamilies": [],
        "deaths": [],
        "badges": [],
        "exceptions": [],
        "guardDecisions": [],
        "gameOver": False,
        "lastCheckpoint": None,
    }


def _sorted_unique(values: Iterable[Any]) -> list[Any]:
    return sorted(set(values))


def apply_event(state: dict[str, Any], event: dict[str, Any]) -> None:
    event_type = str(event.get("type") or "")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    sequence = int(event.get("sequence") or 0)

    if event_type == "checkpoint_observed":
        state["lastCheckpoint"] = {
            "id": data.get("checkpointId"),
            "sequence": sequence,
            "snapshotHash": data.get("snapshotHash"),
        }
    elif event_type == "encounter_observed":
        state["activeEncounter"] = {
            **deepcopy(data),
            "observedSequence": sequence,
        }
    elif event_type == "encounter_resolved":
        area_id = str(data.get("areaId") or "unknown-area")
        if bool(data.get("consumesArea")):
            state["encounters"][area_id] = {
                "areaId": area_id,
                "areaName": data.get("areaName"),
                "source": data.get("source"),
                "outcome": data.get("outcome"),
                "speciesDex": data.get("speciesDex"),
                "familyId": data.get("familyId"),
                "consumedSequence": sequence,
            }
        state["activeEncounter"] = None
    elif event_type == "pokemon_registered":
        pokemon_id = str(data.get("pokemonId") or f"pokemon-{sequence:06d}")
        record = deepcopy(data)
        record["pokemonId"] = pokemon_id
        record["registeredSequence"] = sequence
        record.setdefault("status", "alive")
        state["pokemon"][pokemon_id] = record
        family = record.get("familyId")
        species_dex = record.get("speciesDex")
        if isinstance(species_dex, int):
            state["knownSpecies"] = _sorted_unique((*state["knownSpecies"], species_dex))
        if family:
            state["knownFamilies"] = _sorted_unique((*state["knownFamilies"], str(family)))
    elif event_type == "pokemon_observed":
        pokemon_id = str(data.get("pokemonId") or "")
        if pokemon_id in state["pokemon"]:
            state["pokemon"][pokemon_id].update(deepcopy(data))
            state["pokemon"][pokemon_id]["lastObservedSequence"] = sequence
            species_dex = data.get("speciesDex")
            family = data.get("familyId")
            if isinstance(species_dex, int):
                state["knownSpecies"] = _sorted_unique((*state["knownSpecies"], species_dex))
            if family:
                state["knownFamilies"] = _sorted_unique(
                    (*state["knownFamilies"], str(family))
                )
    elif event_type == "death_registered":
        pokemon_id = str(data.get("pokemonId") or "")
        if pokemon_id in state["pokemon"]:
            state["pokemon"][pokemon_id]["status"] = "dead"
            state["pokemon"][pokemon_id]["deathSequence"] = sequence
        if pokemon_id and pokemon_id not in state["deaths"]:
            state["deaths"].append(pokemon_id)
    elif event_type == "badge_observed":
        badge = str(data.get("badge") or "").strip()
        if badge:
            state["badges"] = _sorted_unique((*state["badges"], badge))
    elif event_type == "exception_recorded":
        state["exceptions"].append({**deepcopy(data), "sequence": sequence})
    elif event_type == "guard_decision":
        decision = {**deepcopy(data), "sequence": sequence}
        state["guardDecisions"] = [*state["guardDecisions"][-49:], decision]
    elif event_type == "blackout":
        state["gameOver"] = bool(data.get("gameOver", True))
    elif event_type == "lineage_restarted":
        state["gameOver"] = False
        state["activeEncounter"] = None


def replay_events(
    ruleset: NuzlockeRuleset,
    events: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    state = initial_lineage_state(ruleset)
    expected_sequence = 1
    for event in events:
        if event.get("schema") != EVENT_SCHEMA:
            raise ValueError("Ledger event has an unsupported schema.")
        if int(event.get("sequence") or 0) != expected_sequence:
            raise ValueError(
                f"Ledger event sequence is not contiguous at {expected_sequence}."
            )
        apply_event(state, event)
        expected_sequence += 1
    return state


class NuzlockeLedger:
    def __init__(
        self,
        path: str | Path,
        ruleset: NuzlockeRuleset,
        *,
        lineage_id: str,
    ) -> None:
        self.path = Path(path).resolve()
        self.ruleset = ruleset
        self.lineage_id = lineage_id
        self.events: list[dict[str, Any]] = []
        self.state = initial_lineage_state(ruleset)
        self.created_utc = utc_now()
        self._load_or_create()

    def _load_or_create(self) -> None:
        ledger_exists = self.path.exists()
        existing = read_json(self.path)
        if existing is None:
            if ledger_exists:
                raise ValueError(
                    f"Existing Nuzlocke ledger is unreadable or malformed: {self.path}"
                )
            self._persist()
            return
        if existing.get("schema") != LEDGER_SCHEMA:
            raise ValueError(f"Unsupported Nuzlocke ledger schema at {self.path}.")
        if existing.get("lineageId") != self.lineage_id:
            raise ValueError("Nuzlocke ledger lineage id does not match the active lineage.")
        ruleset = existing.get("ruleset") if isinstance(existing.get("ruleset"), dict) else {}
        if ruleset.get("digest") != self.ruleset.digest:
            raise ValueError("Nuzlocke ledger ruleset digest does not match the selected ruleset.")
        events = existing.get("events") if isinstance(existing.get("events"), list) else []
        if not all(isinstance(event, dict) for event in events):
            raise ValueError("Nuzlocke ledger events must be objects.")
        replayed = replay_events(self.ruleset, events)
        expected_digest = event_stream_digest(self.ruleset.digest, events)
        if existing.get("eventStreamDigest") != expected_digest:
            raise ValueError("Nuzlocke ledger event stream digest is invalid.")
        if existing.get("state") != replayed:
            raise ValueError("Nuzlocke ledger derived state does not match event replay.")
        if existing.get("stateDigest") != state_digest(replayed):
            raise ValueError("Nuzlocke ledger state digest is invalid.")
        self.events = list(events)
        self.state = replayed
        self.created_utc = str(existing.get("createdUtc") or self.created_utc)

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        evidence: Iterable[str] = (),
        source: str = "runtime",
    ) -> dict[str, Any]:
        sequence = len(self.events) + 1
        event = {
            "schema": EVENT_SCHEMA,
            "id": f"event-{sequence:06d}",
            "sequence": sequence,
            "type": event_type,
            "createdUtc": utc_now(),
            "source": source,
            "data": deepcopy(data),
            "evidence": [str(item) for item in evidence],
        }
        apply_event(self.state, event)
        self.events.append(event)
        self._persist()
        return deepcopy(event)

    def has_checkpoint(self, checkpoint_id: str) -> bool:
        return any(
            event.get("type") == "checkpoint_observed"
            and isinstance(event.get("data"), dict)
            and event["data"].get("checkpointId") == checkpoint_id
            for event in self.events
        )

    def _persist(self) -> None:
        atomic_write_json(
            self.path,
            {
                "schema": LEDGER_SCHEMA,
                "lineageId": self.lineage_id,
                "createdUtc": self.created_utc,
                "updatedUtc": utc_now(),
                "ruleset": {
                    "id": self.ruleset.id,
                    "version": self.ruleset.version,
                    "digest": self.ruleset.digest,
                },
                "eventStreamDigest": event_stream_digest(self.ruleset.digest, self.events),
                "stateDigest": state_digest(self.state),
                "events": self.events,
                "state": self.state,
            },
        )

    def public_summary(self) -> dict[str, Any]:
        pokemon = self.state["pokemon"]
        deaths = [
            {
                "pokemonId": pokemon_id,
                "nickname": pokemon.get(pokemon_id, {}).get("nickname"),
                "speciesName": pokemon.get(pokemon_id, {}).get("speciesName"),
            }
            for pokemon_id in self.state["deaths"]
        ]
        consumed = sorted(self.state["encounters"].values(), key=lambda item: item["areaId"])
        all_areas = sorted(set(self.ruleset.area_aliases.values()))
        next_eligible = [area for area in all_areas if area not in self.state["encounters"]]
        return {
            "schema": "nuzlocke_public_summary_v1",
            "lineageId": self.lineage_id,
            "ruleset": self.ruleset.public_summary(),
            "eventCount": len(self.events),
            "eventStreamDigest": event_stream_digest(self.ruleset.digest, self.events),
            "stateDigest": state_digest(self.state),
            "gameOver": bool(self.state["gameOver"]),
            "activeEncounter": deepcopy(self.state["activeEncounter"]),
            "consumedAreas": deepcopy(consumed),
            "nextEligibleAreas": next_eligible,
            "livingCount": sum(
                1 for item in pokemon.values() if item.get("status") != "dead"
            ),
            "deaths": deaths,
            "badges": list(self.state["badges"]),
            "exceptions": deepcopy(self.state["exceptions"]),
            "recentGuardDecisions": deepcopy(self.state["guardDecisions"][-10:]),
        }
