from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path

from pokemon_player import director_player
from pokemon_player.director_player import (
    DirectorPlayer,
    informative_snapshot_events,
    normalize_nickname_choice_arg,
    normalize_nickname_text_arg,
    normalize_party_target_arg,
    normalize_requested_move_arg,
    promoted_signals,
    skill_availability,
    timestamp_for_path,
)


ROOT = Path(__file__).resolve().parents[1]
GRASS_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "grass_patch_and_encounter_search"
CAPSULE_REGION_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "capsule_a_region_and_landmarks"
BATTLE_DIALOGUE_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "battle_dialogue_advancement_contract"
PARTY_SWITCH_EVIDENCE = ROOT / "research" / "promotions" / "evidence" / "party_switch_and_active_battler"
MANUAL_INPUT = ROOT / "research" / "artifacts" / "director-player-runs" / "manual_input"
INTERPRETATION_CAPTURES = ROOT / "research" / "artifacts" / "director-player-runs" / "interpretation_captures"
LOCAL_GEMMA_RUNS = ROOT / "research" / "artifacts" / "local-gemma-chapter-runs"


def load_record(name: str) -> dict:
    return json.loads((GRASS_EVIDENCE / f"{name}.promotion-evidence.json").read_text(encoding="utf-8"))


def load_skill_record(skill: str, name: str) -> dict:
    return json.loads((ROOT / "research" / "skill-states" / skill / f"{name}.skill.json").read_text(encoding="utf-8"))


def load_promotion_record(folder: Path, name: str) -> dict:
    return json.loads((folder / f"{name}.promotion-evidence.json").read_text(encoding="utf-8"))


def by_id(items: list[dict], identifier: str) -> dict:
    return next(item for item in items if item["id"] == identifier)


def test_director_availability_enables_grass_search_but_not_catch_in_overworld() -> None:
    record = load_record("step_01_standing_in_viridian_approved_grass")

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))

    assert by_id(skills, "enter_grass_search_loop")["enabled"] is True
    assert by_id(skills, "attempt_catch")["enabled"] is False
    literal = by_id(skills, "literal_button_press")
    assert literal["enabled"] is True
    assert literal["params"]["buttons"] == ["a", "b", "up", "down", "left", "right", "start", "select"]


def test_director_navigation_targets_include_viridian_pokecenter() -> None:
    record = load_promotion_record(CAPSULE_REGION_EVIDENCE, "step_01_viridian_city_ready_point")

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))

    assert "viridian_pokecenter" in by_id(skills, "navigate_within_viridian_forest_region")["params"]["targets"]


def test_director_navigation_enables_pewter_region_targets() -> None:
    record = json.loads((ROOT / "research" / "golden-states" / "pewter_city_overworld.expected.json").read_text(encoding="utf-8"))

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))
    pewter = by_id(skills, "navigate_within_pewter_region")

    assert pewter["enabled"] is True
    assert pewter["params"]["defaultTarget"] == "pewter_gym_brock_pre_battle"
    assert "pewter_gym_brock_pre_battle" in pewter["params"]["targetIds"]


def test_director_availability_enables_pokecenter_healing_inside_center() -> None:
    report = json.loads((MANUAL_INPUT / "up-20260625T003351869669Z0000" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(report["before"], Path(report["beforeScreenshotPath"]))

    heal = by_id(skills, "heal_at_pokecenter")
    assert heal["enabled"] is True
    assert by_id(skills, "navigate_within_viridian_forest_region")["enabled"] is True


def test_oaks_lab_dialogue_advances_before_navigation() -> None:
    report = json.loads((LOCAL_GEMMA_RUNS / "20260628T192232115226Z" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(
        report["finalSnapshot"],
        Path(report["finalScreenshot"]),
    )

    assert by_id(skills, "advance_dialogue")["enabled"] is True
    assert by_id(skills, "navigate_within_pallet_region")["enabled"] is False


def test_oaks_lab_menu_flagged_dialogue_still_advances_before_navigation() -> None:
    report = json.loads((LOCAL_GEMMA_RUNS / "20260628T200204479689Z" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(
        report["finalSnapshot"],
        Path(report["finalScreenshot"]),
    )

    assert by_id(skills, "advance_dialogue")["enabled"] is True
    assert by_id(skills, "navigate_within_pallet_region")["enabled"] is False


def test_literal_button_press_skill_does_not_capture_artifacts(monkeypatch, tmp_path: Path) -> None:
    player = DirectorPlayer.__new__(DirectorPlayer)
    player.pyboy = object()
    player.config = SimpleNamespace(render=False)
    player.busy = False
    player.last_result = None
    player.history = []
    player.cached_status = None
    player.event_seq = 0
    player.event_log_path = tmp_path / "events.jsonl"
    player.diagnostic_mode = False
    player.stop_after_action_latched = False

    trace_calls = []

    def fake_run_timed_trace(pyboy: object, trace: list, *, render: bool) -> None:
        trace_calls.append((pyboy, trace, render))

    def fail_save_state(*args: object, **kwargs: object) -> None:
        raise AssertionError("literal_button_press must not save state artifacts")

    monkeypatch.setattr(director_player, "run_timed_trace", fake_run_timed_trace)
    monkeypatch.setattr(director_player, "save_state", fail_save_state)
    monkeypatch.setattr(player, "_fresh_status", lambda log_observations: {"lastResult": player.last_result})

    status = player._execute_skill("literal_button_press", {"button": "a"})

    assert len(trace_calls) == 1
    assert trace_calls[0][1][0].button == "a"
    assert player.last_result["runDir"] is None
    assert player.last_result["reportPath"] is None
    assert player.last_result["warnings"] == []
    assert status["lastResult"]["summary"] == "Pressed A once."


def test_manual_input_requires_explicit_diagnostic_mode(tmp_path: Path) -> None:
    player = DirectorPlayer.__new__(DirectorPlayer)
    player.config = SimpleNamespace(operations_control_path=None)
    player.diagnostic_mode = False
    player.stop_after_action_latched = False

    try:
        player._manual_input("a")
    except PermissionError as exc:
        assert "diagnostic capture mode" in str(exc)
    else:
        raise AssertionError("Raw input must be rejected outside diagnostic mode")


def test_operations_pause_blocks_director_game_actions(tmp_path: Path) -> None:
    control_path = tmp_path / "control.json"
    control_path.write_text(json.dumps({"state": "paused", "stopAfterAction": False}), encoding="utf-8")
    player = DirectorPlayer.__new__(DirectorPlayer)
    player.config = SimpleNamespace(operations_control_path=control_path)
    player.stop_after_action_latched = False

    try:
        player._assert_game_action_allowed()
    except RuntimeError as exc:
        assert "paused" in str(exc)
    else:
        raise AssertionError("Paused Operations state must block Director actions")


def test_director_availability_prioritizes_battle_dialogue_recovery() -> None:
    record = load_record("step_01_wild_battle_in_approved_grass")

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))

    assert by_id(skills, "advance_battle_dialogue")["enabled"] is True
    assert by_id(skills, "attempt_catch")["enabled"] is False
    assert by_id(skills, "use_move")["enabled"] is False
    assert by_id(skills, "enter_grass_search_loop")["enabled"] is False


def test_director_availability_enables_battle_actions_on_action_menu() -> None:
    record = load_promotion_record(BATTLE_DIALOGUE_EVIDENCE, "step_01_move_dialogue_after")

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))
    use_move = by_id(skills, "use_move")

    assert by_id(skills, "attempt_catch")["enabled"] is True
    assert use_move["enabled"] is True
    assert use_move["params"]["argsSchema"]["move"].startswith("string move name")
    assert isinstance(use_move["params"]["exampleArgs"]["move"], str)
    assert by_id(skills, "advance_battle_dialogue")["enabled"] is False


def test_use_move_arg_normalizer_accepts_llm_move_option_object() -> None:
    assert normalize_requested_move_arg({"moveId": 33, "name": "Tackle", "slot": 2}) == "Tackle"
    assert normalize_requested_move_arg({"move_id": "33", "slot": 2}) == 33
    assert normalize_requested_move_arg("Tackle") == "Tackle"


def test_switch_party_member_availability_declares_scalar_target_args() -> None:
    record = load_promotion_record(BATTLE_DIALOGUE_EVIDENCE, "step_01_move_dialogue_after")

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))
    switch = by_id(skills, "switch_party_member")

    assert switch["params"]["argsSchema"]["target"].startswith("party slot number")
    assert isinstance(switch["params"]["exampleArgs"]["target"], int)
    assert switch["params"]["targetSlots"]


def test_party_target_normalizer_accepts_llm_target_option_object() -> None:
    assert normalize_party_target_arg({"slot": 2, "species": "Squirtle", "nickname": "SQUIRTLE"}) == 2
    assert normalize_party_target_arg({"slot": "2", "species": "Squirtle"}) == 2
    assert normalize_party_target_arg({"species": "Squirtle"}) == "Squirtle"
    assert normalize_party_target_arg("Squirtle") == "Squirtle"


def test_director_availability_enables_battle_dialogue_recovery_during_battle_text() -> None:
    record = load_skill_record("attempt_catch", "uncertain_throw_dialogue")

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))

    assert by_id(skills, "advance_battle_dialogue")["enabled"] is True
    assert "battle-dialogue-advancement-contract" in by_id(skills, "advance_battle_dialogue")["params"][
        "requiredPromotions"
    ]


def test_director_availability_enables_battle_outcome_bundle_on_aftermath_text() -> None:
    record = load_skill_record("resolve_battle_outcome_dialogue_bundle", "xp_or_level_up_dialogue")

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))
    bundle = by_id(skills, "resolve_battle_outcome_dialogue_bundle")

    assert bundle["enabled"] is True
    assert bundle["params"]["execution"] == "single_a_press"


def test_director_availability_does_not_auto_advance_forced_party_selection() -> None:
    record = load_promotion_record(PARTY_SWITCH_EVIDENCE, "step_01_party_menu_forced_nidoran")

    skills = skill_availability(record["snapshot"], Path(record["screenshot_file"]))
    bundle = by_id(skills, "resolve_battle_outcome_dialogue_bundle")

    assert bundle["enabled"] is False
    assert bundle["status"] == "uncertain"
    assert "Party selection" in bundle["reason"]


def test_director_availability_enables_switch_for_fainted_active_replacement() -> None:
    report = json.loads((LOCAL_GEMMA_RUNS / "20260628T204049377311Z" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(report["finalSnapshot"], Path(report["finalScreenshot"]))
    switch = by_id(skills, "switch_party_member")

    assert switch["enabled"] is True
    assert switch["params"]["targetSlots"] == [2]
    assert "Forced replacement" in switch["reason"]


def test_director_availability_enables_switch_on_forced_party_prompt_with_stale_active_slot() -> None:
    report = json.loads((LOCAL_GEMMA_RUNS / "20260629T061115146309Z" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(report["finalSnapshot"], Path(report["finalScreenshot"]))
    switch = by_id(skills, "switch_party_member")

    assert by_id(skills, "advance_battle_dialogue")["enabled"] is False
    assert switch["enabled"] is True
    assert switch["params"]["targetSlots"] == [3]


def test_director_availability_enables_nickname_prompt_handler() -> None:
    report = json.loads((MANUAL_INPUT / "a-20260624T222337148845Z0000" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(
        report["before"],
        MANUAL_INPUT / "a-20260624T222337148845Z0000" / "before.png",
    )
    nickname = by_id(skills, "handle_nickname_prompt")

    assert nickname["enabled"] is True
    assert nickname["params"]["argsSchema"]["choice"] == "accept or decline"
    assert nickname["params"]["exampleArgs"] == {"choice": "decline"}
    assert nickname["params"]["choices"] == ["decline", "accept"]
    assert by_id(skills, "advance_battle_dialogue")["enabled"] is False
    assert by_id(skills, "resolve_battle_outcome_dialogue_bundle")["enabled"] is False


def test_director_availability_enables_complete_prologue_on_clean_boot_sentinel() -> None:
    snapshot = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x00, "x": 0, "y": 0},
        "party": [],
        "inventory": [],
        "warnings": [],
    }

    skills = skill_availability(snapshot, ROOT / "does-not-exist.png")
    prologue = by_id(skills, "complete_prologue")

    assert prologue["enabled"] is True
    assert prologue["params"]["exampleArgs"] == {
        "playerName": "RED",
        "rivalName": "BLUE",
        "handoff": "pallet_outside",
    }


def test_director_availability_declares_nickname_text_args() -> None:
    report = json.loads((MANUAL_INPUT / "a-20260624T222352075861Z0000" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(report["after"], MANUAL_INPUT / "a-20260624T222352075861Z0000" / "after.png")
    nickname = by_id(skills, "enter_nickname_text")

    assert nickname["enabled"] is True
    assert nickname["params"]["argsSchema"]["nickname"].startswith("uppercase A-Z")
    assert nickname["params"]["exampleArgs"] == {"nickname": "ABK"}


def test_nickname_arg_normalizers_accept_llm_variants() -> None:
    assert normalize_nickname_choice_arg({"nicknameChoice": "yes"}) == "accept"
    assert normalize_nickname_choice_arg({"choice": "decline"}) == "decline"
    assert normalize_nickname_choice_arg({"choice": True}) == "accept"
    assert normalize_nickname_text_arg({"nicknameText": "jimmy"}) == "JIMMY"
    assert normalize_nickname_text_arg({"nickname": {"text": "jimmy lol"}}) == "JIMMY"


def test_director_availability_routes_pokedex_page_to_outcome_bundle() -> None:
    report = json.loads((MANUAL_INPUT / "a-20260624T225343932819Z0000" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(
        report["before"],
        MANUAL_INPUT / "a-20260624T225343932819Z0000" / "before.png",
    )

    assert by_id(skills, "resolve_battle_outcome_dialogue_bundle")["enabled"] is True
    assert by_id(skills, "attempt_catch")["enabled"] is False
    assert by_id(skills, "use_move")["enabled"] is False
    assert by_id(skills, "switch_party_member")["enabled"] is False


def test_director_availability_routes_pre_pokedex_post_catch_dialogue_to_outcome_bundle() -> None:
    report = json.loads((MANUAL_INPUT / "a-20260624T232150151921Z0000" / "report.json").read_text(encoding="utf-8"))

    skills = skill_availability(
        report["before"],
        MANUAL_INPUT / "a-20260624T232150151921Z0000" / "before.png",
    )

    assert by_id(skills, "resolve_battle_outcome_dialogue_bundle")["enabled"] is True
    assert by_id(skills, "attempt_catch")["enabled"] is False
    assert by_id(skills, "use_move")["enabled"] is False
    assert by_id(skills, "switch_party_member")["enabled"] is False


def test_director_availability_suppresses_battle_advance_on_nickname_intro() -> None:
    capture_ids = [
        "advance_battle_dialogue-20260625T003035943533Z0000",
        "advance_battle_dialogue-20260625T005556627749Z0000",
    ]

    for capture_id in capture_ids:
        report = json.loads((INTERPRETATION_CAPTURES / capture_id / "report.json").read_text(encoding="utf-8"))
        skills = skill_availability(report["snapshot"], INTERPRETATION_CAPTURES / capture_id / "screenshot.png")

        assert by_id(skills, "advance_battle_dialogue")["enabled"] is False
        assert by_id(skills, "resolve_battle_outcome_dialogue_bundle")["enabled"] is False
        assert by_id(skills, "literal_button_press")["enabled"] is False
        assert by_id(skills, "handle_nickname_prompt")["enabled"] is True


def test_director_availability_routes_generated_nickname_intro_through_handler() -> None:
    snapshot = {"mode": "battle", "battle_type_raw": 1, "enemy": {"hp": 1}, "party": []}
    screenshot = LOCAL_GEMMA_RUNS / "20260629T061115146309Z" / "action_017_before.png"

    skills = skill_availability(snapshot, screenshot)

    assert by_id(skills, "handle_nickname_prompt")["enabled"] is True
    assert by_id(skills, "literal_button_press")["enabled"] is False
    assert by_id(skills, "resolve_battle_outcome_dialogue_bundle")["enabled"] is False


def test_director_promoted_signals_include_grass_patch_and_enemy_facts() -> None:
    record = load_record("step_01_wild_battle_in_approved_grass")

    signals = promoted_signals(record["snapshot"], Path(record["screenshot_file"]))

    assert by_id(signals, "grass_patch")["value"] == "viridian_forest_south_grass"
    assert "Weedle" in by_id(signals, "enemy")["value"]
    assert by_id(signals, "battle_dialogue_ready")["value"] is True


def test_director_promoted_signals_mark_battle_dialogue_ready() -> None:
    record = load_skill_record("attempt_catch", "uncertain_throw_dialogue")

    signals = promoted_signals(record["snapshot"], Path(record["screenshot_file"]))

    assert by_id(signals, "battle_dialogue_ready")["value"] is True
    assert by_id(signals, "battle_dialogue_ready")["promotion"] == "battle-dialogue-advancement-contract"


def test_director_informational_events_report_party_move_changes() -> None:
    before = load_skill_record("attempt_catch", "success_before")["snapshot"]
    after = deepcopy(before)
    after["party"][0]["moves"].append({"move_id": 55, "move_name": "Water Gun", "pp": 25})

    events = informative_snapshot_events(before, after)

    assert events
    assert "Water Gun" in events[0][0]


def test_director_informational_events_report_battle_started() -> None:
    before = {"mode": "overworld", "battle_type_raw": 0}
    after = {
        "mode": "battle",
        "battle_type_raw": 1,
        "enemy": {"species_id": 13, "species_name": "Weedle", "level": 4, "hp": 15, "max_hp": 15},
    }

    events = informative_snapshot_events(before, after)

    assert ("Battle started.", ["battle_type_raw=1", "enemy=Weedle Lv4 HP 15/15"]) in events


def test_director_informational_events_report_battle_ended() -> None:
    before = {
        "mode": "battle",
        "battle_type_raw": 1,
        "enemy": {"species_id": 13, "species_name": "Weedle", "level": 4, "hp": 0, "max_hp": 15},
    }
    after = {"mode": "overworld", "battle_type_raw": 0}

    events = informative_snapshot_events(before, after)

    assert events[0][0] == "Battle ended."
    assert "last_enemy=Weedle Lv4 HP 0/15" in events[0][1]


def test_director_informational_events_report_opponent_changed() -> None:
    before = {
        "mode": "battle",
        "battle_type_raw": 2,
        "enemy": {"species_id": 16, "species_name": "Pidgey", "level": 9, "hp": 20, "max_hp": 20},
    }
    after = {
        "mode": "battle",
        "battle_type_raw": 2,
        "enemy": {"species_id": 19, "species_name": "Rattata", "level": 8, "hp": 18, "max_hp": 18},
    }

    events = informative_snapshot_events(before, after)

    assert events[0][0] == "Opponent Pokemon changed."
    assert "before=Pidgey Lv9 HP 20/20" in events[0][1]
    assert "after=Rattata Lv8 HP 18/18" in events[0][1]


def test_director_informational_events_report_enemy_hp_reached_zero() -> None:
    before = {
        "mode": "battle",
        "battle_type_raw": 1,
        "enemy": {"species_id": 13, "species_name": "Weedle", "level": 4, "hp": 6, "max_hp": 15},
    }
    after = {
        "mode": "battle",
        "battle_type_raw": 1,
        "enemy": {"species_id": 13, "species_name": "Weedle", "level": 4, "hp": 0, "max_hp": 15},
    }

    events = informative_snapshot_events(before, after)

    assert events[0][0] == "Enemy Pokemon HP reached 0."
    assert "before_hp=6" in events[0][1]
    assert "after_hp=0" in events[0][1]


def test_timestamp_for_path_removes_windows_path_separators() -> None:
    path_name = timestamp_for_path("2026-06-24T13:45:07.123456+00:00", prefix="a")

    assert path_name == "a-20260624T134507123456Z0000"
    assert ":" not in path_name
