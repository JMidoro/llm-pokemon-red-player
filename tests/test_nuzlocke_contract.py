from __future__ import annotations

import json
from pathlib import Path

import _path  # noqa: F401
import pytest

from pokemon_player.nuzlocke_ledger import NuzlockeLedger, replay_events, state_digest
from pokemon_player.nuzlocke_policy import (
    HARD_RULE_VIOLATION,
    MODEL_MISTAKE,
    STRATEGIC_RISK,
    assess_action,
    authorize_hm_softlock_exception,
    director_rules_context,
    encounter_assessment,
    execute_guarded_skill,
    strategic_advisories,
)
from pokemon_player.nuzlocke_reconciliation import reconcile_snapshot
from pokemon_player.nuzlocke_rules import load_ruleset
from pokemon_player.nuzlocke_runtime import apply_configured_battle_style
from pokemon_player import memory_map as mm
from scripts.evaluate_nuzlocke_contract import evaluate_directory


ROOT = Path(__file__).resolve().parents[1]
RULESET_PATH = ROOT / "research" / "rulesets" / "stream-nuzlocke-v1.json"


def ruleset():
    return load_ruleset(RULESET_PATH)


def ledger(tmp_path: Path) -> NuzlockeLedger:
    return NuzlockeLedger(tmp_path / "ledger.json", ruleset(), lineage_id="test-lineage")


def ruleset_variant(tmp_path: Path, variant_id: str, mutate) -> object:
    raw = json.loads(RULESET_PATH.read_text(encoding="utf-8"))
    raw["id"] = variant_id
    mutate(raw)
    path = tmp_path / f"{variant_id}.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return load_ruleset(path)


def party_member(
    slot: int,
    species_id: int,
    nickname: str,
    *,
    hp: int = 20,
    level: int = 8,
) -> dict:
    return {
        "slot": slot,
        "species_id": species_id,
        "species_name": nickname,
        "nickname": nickname,
        "hp": hp,
        "max_hp": 20,
        "level": level,
        "status": 0,
        "moves": [],
    }


def snapshot(
    *,
    mode: str = "overworld",
    party: list[dict] | None = None,
    owned: list[int] | None = None,
    enemy: dict | None = None,
    battle_type: int = 0,
    map_id: int = 0x33,
    x: int = 1,
    y: int = 2,
) -> dict:
    value = {
        "mode": mode,
        "battle_type_raw": battle_type,
        "position": {
            "map_id": map_id,
            "map_name": "Viridian Forest",
            "x": x,
            "y": y,
        },
        "party": party or [],
        "pokedex_owned_dex_numbers": owned or [],
        "badge_names": [],
    }
    if enemy:
        value["enemy"] = enemy
    if mode == "battle" and value["party"]:
        value["active_party_member"] = value["party"][0]
    return value


def test_approved_rules_are_configuration_not_runtime_defaults() -> None:
    active = ruleset()

    assert active.enabled
    assert active.encounter["duplicateClause"] == "evolutionary_family"
    assert active.encounter["giftConsumesArea"] is False
    assert active.encounter["staticConsumesArea"] is False
    assert active.raw["levelCaps"]["mode"] == "advisory"
    assert active.raw["battle"]["style"] == "set"
    assert active.raw["blackout"]["behavior"] == "game_over"
    assert active.raw["reset"]["manual"] == "only_after_game_over"
    assert len(active.raw["staticEncounters"]) == 8
    assert len(active.raw["giftEncounters"]) == 17
    public = active.public_summary()
    assert public["failedEncounterConsumesArea"] is True
    assert public["giftConsumesArea"] is False
    assert public["staticConsumesArea"] is False
    assert public["battleItemsAllowed"] is True
    assert public["blackoutRestartsLineage"] is True
    assert public["hmSoftlock"]["intentionalBattleDisallowed"] is True


def test_ruleset_validation_rejects_unimplemented_or_malformed_switches(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="disabled or advisory"):
        ruleset_variant(
            tmp_path,
            "hard-level-cap",
            lambda raw: raw["levelCaps"].update({"mode": "hard"}),
        )
    with pytest.raises(ValueError, match="duplicateRemainsAfterDeath"):
        ruleset_variant(
            tmp_path,
            "bad-duplicate-switch",
            lambda raw: raw["encounter"].update({"duplicateRemainsAfterDeath": "yes"}),
        )
    with pytest.raises(ValueError, match="itemsAllowed"):
        ruleset_variant(
            tmp_path,
            "bad-item-switch",
            lambda raw: raw["battle"].update({"itemsAllowed": None}),
        )


def test_complete_internal_species_mapping_preserves_all_gen1_families() -> None:
    assert len(mm.SPECIES_DATA) == 151
    assert set(mm.DEX_NUMBER_TO_SPECIES_ID) == set(range(1, 152))
    assert mm.dex_number_for_species_id(0xB4) == 6
    assert mm.dex_number_for_species_id(0x83) == 150


def test_ledger_reopens_with_identical_replay_and_digests(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    active.append(
        "encounter_resolved",
        {
            "areaId": "route-1",
            "source": "wild",
            "outcome": "caught",
            "speciesDex": 19,
            "familyId": "dex-family-019",
            "consumesArea": True,
        },
    )
    active.append(
        "pokemon_registered",
        {
            "pokemonId": "ratty-001",
            "nickname": "RATTY",
            "speciesDex": 19,
            "familyId": "dex-family-019",
            "status": "alive",
            "location": "party",
        },
    )

    reopened = NuzlockeLedger(active.path, ruleset(), lineage_id="test-lineage")
    replayed = replay_events(ruleset(), reopened.events)

    assert reopened.state == replayed
    assert state_digest(reopened.state) == state_digest(replayed)
    assert reopened.state["encounters"]["route-1"]["outcome"] == "caught"


def test_ledger_detects_derived_state_tampering(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    raw = json.loads(active.path.read_text(encoding="utf-8"))
    raw["state"]["gameOver"] = True
    active.path.write_text(json.dumps(raw), encoding="utf-8")

    try:
        NuzlockeLedger(active.path, ruleset(), lineage_id="test-lineage")
    except ValueError as exc:
        assert "derived state" in str(exc)
    else:
        raise AssertionError("Tampered derived state must not be accepted.")


def test_ledger_never_replaces_a_malformed_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "malformed-ledger.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="unreadable or malformed"):
        NuzlockeLedger(path, ruleset(), lineage_id="test-lineage")

    assert path.read_text(encoding="utf-8") == "{not-json"


def test_ledger_rejects_sequence_lineage_and_ruleset_mismatches(tmp_path: Path) -> None:
    sequence_ledger = ledger(tmp_path)
    sequence_ledger.append("checkpoint_observed", {"checkpointId": "one"})
    raw = json.loads(sequence_ledger.path.read_text(encoding="utf-8"))
    raw["events"][0]["sequence"] = 2
    sequence_ledger.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="sequence is not contiguous"):
        NuzlockeLedger(sequence_ledger.path, ruleset(), lineage_id="test-lineage")

    lineage_path = tmp_path / "lineage-mismatch.json"
    NuzlockeLedger(lineage_path, ruleset(), lineage_id="expected")
    with pytest.raises(ValueError, match="lineage id"):
        NuzlockeLedger(lineage_path, ruleset(), lineage_id="different")

    rules_path = tmp_path / "rules-mismatch-ledger.json"
    NuzlockeLedger(rules_path, ruleset(), lineage_id="rules-lineage")
    different_rules = ruleset_variant(
        tmp_path,
        "different-rules",
        lambda value: value["encounter"].update({"giftConsumesArea": True}),
    )
    with pytest.raises(ValueError, match="ruleset digest"):
        NuzlockeLedger(rules_path, different_rules, lineage_id="rules-lineage")


def test_consumed_area_duplicate_family_nickname_and_reset_are_hard_guards(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    active.append(
        "encounter_resolved",
        {
            "areaId": "viridian-forest",
            "source": "wild",
            "outcome": "failed",
            "speciesDex": 10,
            "familyId": "dex-family-010",
            "consumesArea": True,
        },
    )
    wild = snapshot(
        mode="battle",
        battle_type=1,
        enemy={"species_id": 0x70, "species_name": "Weedle"},
    )

    consumed = assess_action(
        ruleset(), active.state, wild, skill_id="attempt_catch", args={}
    )
    nickname = assess_action(
        ruleset(), active.state, wild, skill_id="handle_nickname_prompt", args={"choice": "decline"}
    )
    empty_nickname = assess_action(
        ruleset(), active.state, wild, skill_id="enter_nickname_text", args={"nickname": ""}
    )
    reset = assess_action(
        ruleset(), active.state, wild, skill_id="reset_game", args={}
    )

    assert consumed.allowed is False and consumed.classification == HARD_RULE_VIOLATION
    assert consumed.code == "area_encounter_consumed"
    assert nickname.allowed is False and nickname.code == "nickname_required"
    assert empty_nickname.allowed is False and empty_nickname.code == "nickname_required"
    assert reset.allowed is False and reset.code == "manual_reset_disallowed"

    active.append(
        "pokemon_registered",
        {
            "pokemonId": "bug-001",
            "familyId": "dex-family-013",
            "status": "alive",
            "location": "box",
        },
    )
    fresh_route = {**wild, "position": {**wild["position"], "map_id": 0x0D}}
    duplicate = assess_action(
        ruleset(), active.state, fresh_route, skill_id="attempt_catch", args={}
    )
    assert duplicate.allowed is False and duplicate.code == "duplicate_family_capture"

    active.append("blackout", {"gameOver": True, "checkpointId": "game-over"})
    after_game_over_reset = assess_action(
        ruleset(), active.state, wild, skill_id="reset_game", args={}
    )
    assert after_game_over_reset.allowed is True


def test_blocked_guard_never_invokes_the_emulator_executor(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    current = snapshot()
    executor_calls = 0

    def executor():
        nonlocal executor_calls
        executor_calls += 1
        raise AssertionError("A blocked action reached the emulator executor.")

    result = execute_guarded_skill(
        ruleset(),
        active,
        current,
        skill_id="literal_button_press",
        args={"button": "a"},
        action_index=1,
        executor=executor,
    )

    assert executor_calls == 0
    assert result["actionStarted"] is False
    assert result["status"] == "blocked"
    assert active.state["guardDecisions"][-1]["classification"] == HARD_RULE_VIOLATION


def test_static_and_gift_encounters_do_not_consume_area(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    for source in ("gift", "static"):
        active.append(
            "encounter_resolved",
            {
                "areaId": "viridian-forest",
                "source": source,
                "outcome": "caught",
                "speciesDex": 7 if source == "gift" else 25,
                "familyId": "dex-family-007" if source == "gift" else "dex-family-025",
                "consumesArea": False,
            },
        )

    assert active.state["encounters"] == {}

    static_battle = snapshot(
        mode="battle",
        battle_type=1,
        map_id=0x53,
        x=4,
        y=10,
        enemy={"species_id": 0x4B, "species_name": "Zapdos"},
    )
    assessment = encounter_assessment(ruleset(), active.state, static_battle)
    assert assessment["source"] == "static"
    assert assessment["consumesArea"] is False
    assert assessment["eligible"] is True

    ordinary_power_plant_wild = snapshot(
        mode="battle",
        battle_type=1,
        map_id=0x53,
        x=15,
        y=15,
        enemy={"species_id": 0x06, "species_name": "Voltorb"},
    )
    assert encounter_assessment(
        ruleset(), active.state, ordinary_power_plant_wild
    )["source"] == "wild"

    static_ledger = NuzlockeLedger(
        tmp_path / "static-ledger.json", ruleset(), lineage_id="static-lineage"
    )
    starter = [party_member(1, 0xB1, "SHELL")]
    reconcile_snapshot(
        static_ledger,
        ruleset(),
        snapshot(
            mode="battle",
            battle_type=1,
            party=starter,
            owned=[7],
            map_id=0x53,
            x=4,
            y=10,
            enemy={"species_id": 0x4B, "species_name": "Zapdos"},
        ),
        checkpoint_id="static-before",
    )
    reconcile_snapshot(
        static_ledger,
        ruleset(),
        snapshot(
            party=[*starter, party_member(2, 0x4B, "STORM")],
            owned=[7, 145],
            map_id=0x53,
            x=4,
            y=10,
        ),
        checkpoint_id="static-after",
        last_action={"skillId": "attempt_catch"},
    )
    assert static_ledger.state["encounters"] == {}
    zapdos = [
        record
        for record in static_ledger.state["pokemon"].values()
        if record.get("speciesDex") == 145
    ]
    assert zapdos[0]["encounterSource"] == "static"


def test_duplicate_encounter_exit_is_not_misreported_as_a_capture(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    team = [party_member(1, 0x03, "NIDO")]
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(party=team, owned=[32], map_id=0x0D),
        checkpoint_id="duplicate-baseline",
    )
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(
            mode="battle",
            battle_type=1,
            party=team,
            owned=[32],
            map_id=0x0D,
            enemy={"species_id": 0xA7, "species_name": "Nidorino"},
        ),
        checkpoint_id="duplicate-battle",
    )
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(party=team, owned=[32], map_id=0x0D),
        checkpoint_id="duplicate-exit",
        last_action={"skillId": "run_from_wild_battle"},
    )

    resolved = [event for event in active.events if event["type"] == "encounter_resolved"]
    assert resolved[-1]["data"]["outcome"] == "failed"
    assert resolved[-1]["data"]["consumesArea"] is False


def test_duplicate_modes_and_after_death_switch_are_honored(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    active.append(
        "pokemon_registered",
        {
            "pokemonId": "caterpie-001",
            "speciesDex": 10,
            "familyId": "dex-family-010",
            "status": "alive",
            "location": "party",
        },
    )
    butterfree = snapshot(
        mode="battle",
        battle_type=1,
        map_id=0x0D,
        enemy={"species_id": 0x7D, "species_name": "Butterfree"},
    )
    species_only = ruleset_variant(
        tmp_path,
        "species-only",
        lambda raw: raw["encounter"].update({"duplicateClause": "species"}),
    )

    assert encounter_assessment(ruleset(), active.state, butterfree)["duplicate"] is True
    assert encounter_assessment(species_only, active.state, butterfree)["duplicate"] is False

    active.append("death_registered", {"pokemonId": "caterpie-001"})
    caterpie = snapshot(
        mode="battle",
        battle_type=1,
        map_id=0x0D,
        enemy={"species_id": 0x7B, "species_name": "Caterpie"},
    )
    after_death_allowed = ruleset_variant(
        tmp_path,
        "after-death-allowed",
        lambda raw: raw["encounter"].update(
            {"duplicateClause": "evolutionary_family", "duplicateRemainsAfterDeath": False}
        ),
    )
    assert encounter_assessment(ruleset(), active.state, caterpie)["duplicate"] is True
    assert encounter_assessment(
        after_death_allowed, active.state, caterpie
    )["duplicate"] is False


def test_first_encounter_and_shiny_exception_switches_are_honored(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    active.append(
        "encounter_resolved",
        {
            "areaId": "route-2",
            "source": "wild",
            "outcome": "caught",
            "speciesDex": 10,
            "familyId": "dex-family-010",
            "consumesArea": True,
        },
    )
    active.append(
        "pokemon_registered",
        {
            "pokemonId": "caterpie-001",
            "speciesDex": 10,
            "familyId": "dex-family-010",
            "status": "alive",
            "location": "box",
        },
    )
    ordinary = snapshot(
        mode="battle",
        battle_type=1,
        map_id=0x0D,
        enemy={"species_id": 0x7B, "species_name": "Caterpie"},
    )
    unrestricted = ruleset_variant(
        tmp_path,
        "unrestricted-wild",
        lambda raw: raw["encounter"].update(
            {"firstEligibleWildPerArea": False, "duplicateClause": "none"}
        ),
    )
    unrestricted_assessment = encounter_assessment(unrestricted, active.state, ordinary)
    assert unrestricted_assessment["eligible"] is True
    assert unrestricted_assessment["consumesArea"] is False
    assert unrestricted_assessment["reason"] == "wild_encounters_not_limited_by_area"
    assert assess_action(
        unrestricted, active.state, ordinary, skill_id="attempt_catch", args={}
    ).allowed is True

    shiny_rules = ruleset_variant(
        tmp_path,
        "shiny-exception",
        lambda raw: raw["encounter"].update({"shinyException": True}),
    )
    shiny = {**ordinary, "enemy": {**ordinary["enemy"], "shiny": True}}
    shiny_assessment = encounter_assessment(shiny_rules, active.state, shiny)
    assert shiny_assessment["shinyExceptionApplied"] is True
    assert shiny_assessment["consumesArea"] is False
    assert shiny_assessment["reason"] == "shiny_exception_independent_of_area"
    assert assess_action(
        shiny_rules, active.state, shiny, skill_id="attempt_catch", args={}
    ).allowed is True


def test_hm_exception_authorization_honors_each_allow_switch(tmp_path: Path) -> None:
    denied_rules = ruleset_variant(
        tmp_path,
        "hm-denied",
        lambda raw: raw["hmSoftlock"].update(
            {
                "allowDeadFieldOnlyCarrier": False,
                "allowOutOfEncounterUtilityCapture": False,
            }
        ),
    )
    denied_ledger = NuzlockeLedger(
        tmp_path / "hm-denied-ledger.json", denied_rules, lineage_id="hm-denied"
    )
    for kind in ("dead_field_only_carrier", "out_of_encounter_utility_capture"):
        with pytest.raises(ValueError, match="does not allow"):
            authorize_hm_softlock_exception(
                denied_ledger,
                denied_rules,
                kind=kind,
                pokemon_id="carrier-001",
                move="Cut",
                reason="Required progression is otherwise impossible.",
                required_progression=True,
                living_legal_options_exhausted=True,
            )

    battle_allowed_rules = ruleset_variant(
        tmp_path,
        "hm-battle-allowed",
        lambda raw: raw["hmSoftlock"].update({"intentionalBattleDisallowed": False}),
    )
    battle_allowed_ledger = NuzlockeLedger(
        tmp_path / "hm-battle-ledger.json",
        battle_allowed_rules,
        lineage_id="hm-battle-allowed",
    )
    event = authorize_hm_softlock_exception(
        battle_allowed_ledger,
        battle_allowed_rules,
        kind="dead_field_only_carrier",
        pokemon_id="carrier-001",
        move="Cut",
        reason="Required progression is otherwise impossible.",
        required_progression=True,
        living_legal_options_exhausted=True,
    )
    assert event["data"]["intentionalBattleAllowed"] is True
    assert event["data"]["fieldUseOnly"] is False


def test_alternate_ruleset_switches_change_runtime_behavior_without_code_edits(
    tmp_path: Path,
) -> None:
    alternative = ruleset_variant(
        tmp_path,
        "alternate-contract",
        lambda raw: (
            raw["encounter"].update(
                {
                    "failedEligibleEncounterConsumesArea": False,
                    "giftConsumesArea": True,
                    "staticConsumesArea": True,
                }
            ),
            raw["nickname"].update({"required": False}),
            raw["battle"].update({"style": "shift"}),
            raw["blackout"].update({"behavior": "continue", "restartLineage": False}),
            raw["reset"].update({"manual": "allowed"}),
        ),
    )
    active = NuzlockeLedger(
        tmp_path / "alternate-ledger.json",
        alternative,
        lineage_id="alternate-contract",
    )

    reconcile_snapshot(
        active,
        alternative,
        snapshot(
            mode="battle",
            battle_type=1,
            map_id=0x0D,
            enemy={"species_id": 0x7B, "species_name": "Caterpie"},
        ),
        checkpoint_id="failed-before",
    )
    reconcile_snapshot(
        active,
        alternative,
        snapshot(map_id=0x0D),
        checkpoint_id="failed-after",
        last_action={"skillId": "run_from_wild_battle"},
    )
    assert "route-2" not in active.state["encounters"]

    static_battle = snapshot(
        mode="battle",
        battle_type=1,
        map_id=0x53,
        x=4,
        y=10,
        enemy={"species_id": 0x4B, "species_name": "Zapdos"},
    )
    assert encounter_assessment(
        alternative, active.state, static_battle
    )["consumesArea"] is True

    gift_ledger = NuzlockeLedger(
        tmp_path / "alternate-gift-ledger.json",
        alternative,
        lineage_id="alternate-gift",
    )
    reconcile_snapshot(
        gift_ledger,
        alternative,
        snapshot(map_id=0x28),
        checkpoint_id="gift-before",
    )
    reconcile_snapshot(
        gift_ledger,
        alternative,
        snapshot(party=[party_member(1, 0xB1, "SHELL")], owned=[7], map_id=0x28),
        checkpoint_id="gift-after",
        last_action={"skillId": "choose_starter"},
    )
    assert gift_ledger.state["encounters"]["map-28"]["source"] == "gift"

    fainted = snapshot(party=[party_member(1, 0xB1, "SHELL", hp=0)])
    reconcile_snapshot(
        active,
        alternative,
        fainted,
        checkpoint_id="non-terminal-blackout",
    )
    assert active.state["gameOver"] is False
    assert assess_action(
        alternative,
        active.state,
        fainted,
        skill_id="handle_nickname_prompt",
        args={"choice": "decline"},
    ).allowed is True
    assert assess_action(
        alternative, active.state, fainted, skill_id="reset_game", args={}
    ).allowed is True

    class Memory(dict):
        def __getitem__(self, key):
            return self.get(key, 0)

    memory = Memory({mm.OPTIONS: 0})
    style = apply_configured_battle_style(memory, alternative)
    assert style["after"] == "shift"
    assert memory[mm.OPTIONS] & (1 << 6) == 0


def test_dead_pokemon_battle_use_is_blocked_before_input(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    active.append(
        "pokemon_registered",
        {
            "pokemonId": "bird-001",
            "nickname": "BIRD",
            "speciesDex": 21,
            "familyId": "dex-family-021",
            "status": "alive",
            "location": "party",
            "slot": 1,
        },
    )
    active.append("death_registered", {"pokemonId": "bird-001"})
    battle = snapshot(
        mode="battle",
        battle_type=1,
        party=[party_member(1, 0x05, "BIRD", hp=0)],
        enemy={"species_id": 0x70, "species_name": "Weedle"},
    )

    move = assess_action(ruleset(), active.state, battle, skill_id="use_move", args={"move": "Peck"})
    switch = assess_action(
        ruleset(), active.state, battle, skill_id="switch_party_member", args={"target": 1}
    )

    assert move.allowed is False and move.code == "dead_pokemon_battle_use"
    assert switch.allowed is False and switch.code == "dead_pokemon_battle_use"


def test_level_cap_is_advice_and_does_not_remove_director_agency(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    current = snapshot(party=[party_member(1, 0xB1, "SHELL", level=15)])

    advisories = strategic_advisories(ruleset(), active.state, current)
    decision = assess_action(
        ruleset(), active.state, current, skill_id="overworld_rearrange_party", args={"target": 1}
    )

    assert advisories[0]["code"] == "advisory_level_cap_exceeded"
    assert advisories[0]["hardBlock"] is False
    assert decision.allowed is True


def test_policy_classifications_keep_legality_risk_and_model_error_distinct(
    tmp_path: Path,
) -> None:
    active = ledger(tmp_path)
    risky = snapshot(party=[party_member(1, 0xB1, "SHELL", level=15)])
    advisory = strategic_advisories(ruleset(), active.state, risky)[0]
    mistaken = assess_action(
        ruleset(), active.state, risky, skill_id="attempt_catch", args={}
    )
    hard = assess_action(
        ruleset(), active.state, risky, skill_id="literal_button_press", args={"button": "a"}
    )

    assert advisory["classification"] == STRATEGIC_RISK
    assert mistaken.classification == MODEL_MISTAKE and mistaken.allowed is True
    assert hard.classification == HARD_RULE_VIOLATION and hard.allowed is False


def test_configured_battle_item_restriction_is_a_pre_input_guard(tmp_path: Path) -> None:
    restricted = ruleset_variant(
        tmp_path,
        "battle-items-restricted",
        lambda raw: raw["battle"].update({"itemsAllowed": False}),
    )
    current = snapshot(
        mode="battle",
        battle_type=1,
        party=[party_member(1, 0xB1, "SHELL")],
        enemy={"species_id": 0x70, "species_name": "Weedle"},
    )

    decision = assess_action(
        restricted,
        ledger(tmp_path).state,
        current,
        skill_id="use_battle_item",
        args={"item": "Potion"},
    )

    assert decision.allowed is False
    assert decision.classification == HARD_RULE_VIOLATION
    assert decision.code == "battle_items_restricted"


def test_raw_controller_input_is_hidden_from_enforced_runs(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    decision = assess_action(
        ruleset(),
        active.state,
        snapshot(),
        skill_id="literal_button_press",
        args={"button": "b"},
    )

    assert decision.allowed is False
    assert decision.code == "raw_input_bypasses_rules"


def test_battle_style_configuration_changes_only_the_options_style_bit() -> None:
    class Memory(dict):
        def __getitem__(self, key):
            return self.get(key, 0)

    memory = Memory({mm.OPTIONS: 0b10000101})
    result = apply_configured_battle_style(memory, ruleset())

    assert result["before"] == "shift"
    assert result["after"] == "set"
    assert memory[mm.OPTIONS] == 0b11000101


def test_hm_softlock_exception_is_required_only_field_only_and_audited(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    active.append(
        "pokemon_registered",
        {
            "pokemonId": "carrier-001",
            "nickname": "CARRY",
            "speciesDex": 21,
            "familyId": "dex-family-021",
            "status": "alive",
            "location": "party",
            "slot": 1,
        },
    )
    event = authorize_hm_softlock_exception(
        active,
        ruleset(),
        kind="out_of_encounter_utility_capture",
        pokemon_id="carrier-001",
        move="Cut",
        reason="No living legal Pokemon can learn Cut and progression requires it.",
        required_progression=True,
        living_legal_options_exhausted=True,
    )
    current = snapshot(party=[party_member(1, 0x05, "CARRY")])
    battle_use = assess_action(
        ruleset(), active.state, current, skill_id="switch_party_member", args={"target": 1}
    )

    assert event["data"]["intentionalBattleAllowed"] is False
    assert event["data"]["removeAtNextPc"] is True
    assert battle_use.allowed is False and battle_use.code == "hm_exception_battle_use"

    try:
        authorize_hm_softlock_exception(
            active,
            ruleset(),
            kind="dead_field_only_carrier",
            pokemon_id="carrier-001",
            move="Flash",
            reason="Convenience only.",
            required_progression=False,
            living_legal_options_exhausted=True,
        )
    except ValueError as exc:
        assert "required progression" in str(exc)
    else:
        raise AssertionError("Optional HM convenience must not create a softlock exception.")

    with pytest.raises(ValueError, match="living legal HM option"):
        authorize_hm_softlock_exception(
            active,
            ruleset(),
            kind="dead_field_only_carrier",
            pokemon_id="carrier-001",
            move="Cut",
            reason="A living legal option still exists.",
            required_progression=True,
            living_legal_options_exhausted=False,
        )


def test_checkpoint_reconciliation_tracks_box_capture_death_blackout_and_gift(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    team = [
        party_member(1, 0xB1, "SHELL"),
        party_member(2, 0x24, "BIRD"),
        party_member(3, 0xA5, "RAT"),
        party_member(4, 0x05, "SPEAR"),
        party_member(5, 0x70, "BUG"),
        party_member(6, 0x03, "NIDO"),
    ]
    owned = [7, 16, 19, 21, 13, 32]
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(
            mode="battle",
            battle_type=1,
            party=team,
            owned=owned,
            enemy={"species_id": 0x54, "species_name": "Pikachu"},
        ),
        checkpoint_id="before-catch",
        snapshot_hash="before",
    )
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(party=team, owned=[*owned, 25]),
        checkpoint_id="after-catch",
        snapshot_hash="after",
        last_action={"skillId": "attempt_catch"},
    )

    boxed = [item for item in active.state["pokemon"].values() if item.get("speciesDex") == 25]
    assert boxed and boxed[0]["location"] == "box"
    assert boxed[0]["provenance"] == "capture"
    assert active.state["encounters"]["viridian-forest"]["outcome"] == "caught"

    pikachu_id = boxed[0]["pokemonId"]
    withdrawn_team = [*team[:5], party_member(6, 0x54, "SPARK")]
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(party=withdrawn_team, owned=[*owned, 25]),
        checkpoint_id="withdraw-boxed-capture",
    )
    assert len(active.state["pokemon"]) == 7
    assert active.state["pokemon"][pikachu_id]["location"] == "party"
    assert active.state["pokemon"][pikachu_id]["nickname"] == "SPARK"
    assert active.state["pokemon"]["nido-006"]["location"] == "not_in_party"

    fainted = [{**member, "hp": 0} for member in withdrawn_team]
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(party=fainted, owned=[*owned, 25]),
        checkpoint_id="blackout",
    )
    assert active.state["gameOver"] is True
    assert len(active.state["deaths"]) == 6

    gift_ledger = NuzlockeLedger(
        tmp_path / "gift-ledger.json", ruleset(), lineage_id="gift-lineage"
    )
    reconcile_snapshot(
        gift_ledger,
        ruleset(),
        snapshot(party=[], owned=[], map_id=0x28),
        checkpoint_id="before-gift",
    )
    reconcile_snapshot(
        gift_ledger,
        ruleset(),
        snapshot(
            party=[party_member(1, 0xB1, "SHELL")],
            owned=[7],
            map_id=0x28,
        ),
        checkpoint_id="after-gift",
        last_action={"skillId": "choose_starter"},
    )
    assert gift_ledger.state["encounters"] == {}
    assert next(iter(gift_ledger.state["pokemon"].values()))["encounterSource"] == "gift"


def test_checkpoint_reconciliation_ignores_transient_post_catch_party_placeholder(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    team = [party_member(1, 0xB1, "SHELL")]
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(
            mode="battle",
            battle_type=1,
            party=team,
            owned=[7],
            enemy={"species_id": 0x54, "species_name": "Pikachu"},
        ),
        checkpoint_id="before-catch",
    )
    placeholder = {
        "slot": 2,
        "species_id": 0,
        "species_name": "Species 0x00",
        "nickname": "",
        "hp": 0,
        "max_hp": 0,
        "level": 0,
        "moves": [],
    }
    reconcile_snapshot(
        active,
        ruleset(),
        snapshot(
            mode="battle",
            battle_type=1,
            party=[*team, placeholder],
            owned=[7, 25],
            enemy={"species_id": 0x54, "species_name": "Pikachu"},
        ),
        checkpoint_id="nickname-prompt",
        last_action={"skillId": "resolve_battle_outcome_dialogue_bundle"},
    )

    assert not any(record.get("speciesName") == "Species 0x00" for record in active.state["pokemon"].values())
    assert not any(pokemon_id.startswith("species-0x00") for pokemon_id in active.state["deaths"])


def test_director_context_explains_rules_eligibility_deaths_and_exceptions(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    active.append(
        "exception_recorded",
        {
            "kind": "required_hm_field_carrier",
            "summary": "Dead carrier allowed for required progression only.",
        },
    )
    wild = snapshot(
        mode="battle",
        battle_type=1,
        enemy={"species_id": 0x70, "species_name": "Weedle"},
    )

    context = director_rules_context(ruleset(), active, wild)

    assert context["ruleset"]["giftConsumesArea"] is False
    assert context["currentEncounter"]["eligible"] is True
    assert context["lineage"]["exceptions"][0]["kind"] == "required_hm_field_carrier"


def test_encounter_assessment_uses_canonical_area_aliases(tmp_path: Path) -> None:
    active = ledger(tmp_path)
    wild = snapshot(
        mode="battle",
        battle_type=1,
        enemy={"species_id": 0x70, "species_name": "Weedle"},
    )

    assessment = encounter_assessment(ruleset(), active.state, wild)

    assert assessment["area"]["id"] == "viridian-forest"
    assert assessment["familyId"] == "dex-family-013"
    assert assessment["eligible"] is True


def test_standalone_contract_evaluator_replays_every_fixture_without_inference(
    tmp_path: Path,
) -> None:
    summary = evaluate_directory(
        fixture_root=ROOT / "research" / "evals" / "nuzlocke-contract",
        ruleset_path=RULESET_PATH,
        output_root=tmp_path / "evaluation",
    )

    assert summary["allPassed"] is True
    assert summary["fixtureCount"] == 7
    assert summary["passedCount"] == 7
    assert summary["inference"] == {"used": False, "provider": None, "model": None}
    assert (tmp_path / "evaluation" / "evaluation-summary.json").is_file()


def test_captured_pikachu_artifacts_reconcile_without_new_gameplay_collection(
    tmp_path: Path,
) -> None:
    evidence_root = (
        ROOT
        / "research"
        / "promotions"
        / "evidence"
        / "capsule_success_target_ownership"
    )
    before_record = json.loads(
        (evidence_root / "step_02_target_before_battle_pikachu.promotion-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    after_record = json.loads(
        (evidence_root / "step_02_target_after_pikachu_caught.promotion-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    before = {
        **before_record["snapshot"],
        "pokedex_owned_dex_numbers": before_record["pokedex"]["owned_dex_numbers"],
    }
    after = {
        **after_record["snapshot"],
        "pokedex_owned_dex_numbers": after_record["pokedex"]["owned_dex_numbers"],
    }
    active = ledger(tmp_path)

    reconcile_snapshot(
        active,
        ruleset(),
        before,
        checkpoint_id="captured-before",
        snapshot_hash=before_record["snapshot_hash"],
    )
    reconcile_snapshot(
        active,
        ruleset(),
        after,
        checkpoint_id="captured-after",
        snapshot_hash=after_record["snapshot_hash"],
        last_action={"skillId": "attempt_catch"},
    )

    assert active.state["encounters"]["viridian-forest"]["outcome"] == "caught"
    assert any(item.get("speciesDex") == 25 for item in active.state["pokemon"].values())
    assert len(active.state["pokemon"]) == len(after["party"])
