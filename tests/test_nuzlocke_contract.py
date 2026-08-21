from __future__ import annotations

import json
from pathlib import Path

import _path  # noqa: F401

from pokemon_player.nuzlocke_ledger import NuzlockeLedger, replay_events, state_digest
from pokemon_player.nuzlocke_policy import (
    HARD_RULE_VIOLATION,
    assess_action,
    authorize_hm_softlock_exception,
    director_rules_context,
    encounter_assessment,
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

    memory = Memory({mm.OPTIONS: 0b11000101})
    result = apply_configured_battle_style(memory, ruleset())

    assert result["before"] == "shift"
    assert result["after"] == "set"
    assert memory[mm.OPTIONS] == 0b10000101


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
        )
    except ValueError as exc:
        assert "required progression" in str(exc)
    else:
        raise AssertionError("Optional HM convenience must not create a softlock exception.")


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

    fainted = [{**member, "hp": 0} for member in team]
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
