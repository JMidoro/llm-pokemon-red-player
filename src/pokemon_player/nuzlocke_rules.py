from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


RULESET_SCHEMA = "pokemon_player_ruleset_v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class NuzlockeRuleset:
    path: Path
    raw: dict[str, Any]
    digest: str

    @property
    def id(self) -> str:
        return str(self.raw["id"])

    @property
    def version(self) -> int:
        return int(self.raw["version"])

    @property
    def enabled(self) -> bool:
        return bool(self.raw.get("enabled"))

    @property
    def encounter(self) -> dict[str, Any]:
        value = self.raw.get("encounter")
        return value if isinstance(value, dict) else {}

    @property
    def enforcement(self) -> dict[str, Any]:
        value = self.raw.get("enforcement")
        return value if isinstance(value, dict) else {}

    @property
    def area_aliases(self) -> dict[str, str]:
        value = self.raw.get("areaAliases")
        if not isinstance(value, dict):
            return {}
        return {str(key): str(item) for key, item in value.items()}

    def public_summary(self) -> dict[str, Any]:
        encounter = self.encounter
        return {
            "schema": RULESET_SCHEMA,
            "id": self.id,
            "version": self.version,
            "digest": self.digest,
            "enabled": self.enabled,
            "firstEncounter": bool(encounter.get("firstEligibleWildPerArea")),
            "duplicateClause": str(encounter.get("duplicateClause") or "none"),
            "giftConsumesArea": bool(encounter.get("giftConsumesArea")),
            "staticConsumesArea": bool(encounter.get("staticConsumesArea")),
            "shinyException": bool(encounter.get("shinyException")),
            "nicknameRequired": bool(self.raw.get("nickname", {}).get("required")),
            "levelCapMode": str(self.raw.get("levelCaps", {}).get("mode") or "disabled"),
            "battleStyle": str(self.raw.get("battle", {}).get("style") or "shift"),
            "blackout": str(self.raw.get("blackout", {}).get("behavior") or "continue"),
            "manualReset": str(self.raw.get("reset", {}).get("manual") or "allowed"),
        }


def validate_ruleset(raw: dict[str, Any]) -> None:
    if raw.get("schema") != RULESET_SCHEMA:
        raise ValueError(f"Ruleset schema must be {RULESET_SCHEMA!r}.")
    if not isinstance(raw.get("id"), str) or not str(raw["id"]).strip():
        raise ValueError("Ruleset id must be a non-empty string.")
    if not isinstance(raw.get("version"), int) or int(raw["version"]) < 1:
        raise ValueError("Ruleset version must be a positive integer.")
    if not isinstance(raw.get("enabled"), bool):
        raise ValueError("Ruleset enabled must be a boolean.")
    encounter = raw.get("encounter")
    if not isinstance(encounter, dict):
        raise ValueError("Ruleset encounter must be an object.")
    duplicate_clause = encounter.get("duplicateClause")
    if duplicate_clause not in {"none", "species", "evolutionary_family"}:
        raise ValueError("encounter.duplicateClause must be none, species, or evolutionary_family.")
    for key in (
        "firstEligibleWildPerArea",
        "failedEligibleEncounterConsumesArea",
        "giftConsumesArea",
        "staticConsumesArea",
        "shinyException",
    ):
        if not isinstance(encounter.get(key), bool):
            raise ValueError(f"encounter.{key} must be a boolean.")
    if raw.get("blackout", {}).get("behavior") not in {"game_over", "continue"}:
        raise ValueError("blackout.behavior must be game_over or continue.")
    if raw.get("reset", {}).get("manual") not in {"disallowed", "only_after_game_over", "allowed"}:
        raise ValueError("reset.manual has an unsupported value.")
    if raw.get("levelCaps", {}).get("mode") not in {"disabled", "advisory", "hard"}:
        raise ValueError("levelCaps.mode must be disabled, advisory, or hard.")
    if raw.get("battle", {}).get("style") not in {"set", "shift"}:
        raise ValueError("battle.style must be set or shift.")
    for collection in ("staticEncounters", "giftEncounters"):
        values = raw.get(collection, [])
        if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
            raise ValueError(f"{collection} must be a list of objects.")
        for item in values:
            try:
                map_id = int(item["mapId"])
                species_dex = int(item["speciesDex"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Every {collection} entry must have integer mapId and speciesDex values."
                ) from exc
            if not 0 <= map_id <= 0xFF or not 1 <= species_dex <= 151:
                raise ValueError(f"{collection} mapId or speciesDex is outside Pokemon Red bounds.")
            if collection == "staticEncounters":
                positions = item.get("objectPositions")
                if not isinstance(positions, list) or not positions:
                    raise ValueError(
                        "Every staticEncounters entry must identify at least one object position."
                    )
                for position in positions:
                    if not isinstance(position, dict):
                        raise ValueError("Static encounter object positions must be objects.")
                    try:
                        x = int(position["x"])
                        y = int(position["y"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ValueError(
                            "Static encounter object positions require integer x and y values."
                        ) from exc
                    if x < 0 or y < 0:
                        raise ValueError("Static encounter object positions cannot be negative.")


def load_ruleset(path: str | Path) -> NuzlockeRuleset:
    resolved = Path(path).resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load ruleset {resolved}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Ruleset root must be an object.")
    validate_ruleset(raw)
    digest = sha256(_canonical_json(raw).encode("utf-8")).hexdigest()
    return NuzlockeRuleset(path=resolved, raw=raw, digest=digest)
