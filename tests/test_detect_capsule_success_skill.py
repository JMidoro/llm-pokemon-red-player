from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.skills.detect_capsule_success import detect_capsule_success, resolve_target


ROOT = Path(__file__).resolve().parents[1]
PROMOTION_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "capsule_success_target_ownership"


def load_record(name: str) -> dict:
    return json.loads((PROMOTION_EVIDENCE / f"{name}.promotion-evidence.json").read_text(encoding="utf-8"))


def test_detect_capsule_success_succeeds_when_target_owned_bit_is_set() -> None:
    record = load_record("step_02_target_after_pikachu_caught")

    result = detect_capsule_success(record, target_species="Pikachu")

    assert result.status == "succeeded"
    assert result.summary == "Capsule target Pikachu is Pokedex-owned."
    assert "pokedex_owned=True" in result.evidence


def test_detect_capsule_success_fails_before_target_owned_bit_is_set() -> None:
    record = load_record("step_02_target_before_battle_pikachu")

    result = detect_capsule_success(record, target_species="Pikachu")

    assert result.status == "failed"
    assert result.summary == "Capsule target Pikachu is not Pokedex-owned yet."
    assert "pokedex_owned=False" in result.evidence


def test_detect_capsule_success_does_not_treat_party_as_authoritative() -> None:
    record = load_record("step_02_target_after_pikachu_caught")

    result = detect_capsule_success(record["snapshot"], target_species="Pikachu")

    assert result.status == "uncertain"
    assert "Pokedex-owned facts are unavailable" in result.summary
    assert "party_target_count=1" in result.evidence


def test_detect_capsule_success_requires_supported_target() -> None:
    record = load_record("step_02_target_after_pikachu_caught")

    result = detect_capsule_success(record)

    assert result.status == "blocked"


def test_resolve_target_prefers_known_internal_species_id_over_dex_number() -> None:
    assert resolve_target(0x54) == ("Pikachu", 25)
    assert resolve_target(25) == ("Pikachu", 25)
