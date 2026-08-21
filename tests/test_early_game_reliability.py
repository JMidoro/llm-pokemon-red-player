from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pokemon_player.early_game_reliability import (
    accepted_lineage_reports,
    action_audit,
    capsule_a_success,
    clean_boot_boulder_success,
    evaluate_deterministic_branches,
    evaluate_suite,
    failure_is_useful,
    validate_frozen_suite,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def frozen_suite(tmp_path: Path) -> dict:
    capsule_cases = []
    for index in range(1, 6):
        state = tmp_path / "states" / f"capsule-{index}.state"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_bytes(f"state-{index}".encode())
        snapshot_hash = f"snapshot-{index}"
        write_json(
            state.with_suffix(".state.report.json"),
            {
                "snapshot_hash": snapshot_hash,
                "snapshot": {
                    "party": [{"species_name": "Squirtle", "hp": 20}],
                    "inventory": [{"item_name": "Poke Ball", "quantity": 3}],
                },
            },
        )
        capsule_cases.append(
            {
                "id": f"capsule-{index}",
                "statePath": str(state.relative_to(tmp_path)),
                "stateSha256": hashlib.sha256(state.read_bytes()).hexdigest(),
                "snapshotHash": snapshot_hash,
                "firstInferenceSeed": 5200 + index,
            }
        )
    clean_cases = [
        {"id": f"clean-{index}", "firstInferenceSeed": 5300 + index}
        for index in range(1, 11)
    ]
    return {
        "schema": "milestone_5_evaluation_suite_v1",
        "status": "frozen_before_model_evaluation",
        "frozenAtUtc": "2026-08-21T00:00:00Z",
        "providerProfile": {
            "provider": "lmstudio-chat",
            "model": "google/gemma-4-e4b",
            "temperature": 0.1,
            "hostedInferenceAllowed": False,
        },
        "romProfile": {
            "title": "POKEMON RED",
            "sizeBytes": 1_048_576,
            "sha256": "5CA7BA01642A3B27B0CC0B5349B52792795B62D3ED977E98A09390659AF96B7B",
        },
        "capsuleA": {
            "ruleset": "research/rulesets/standard-run-v1.json",
            "caseCount": 5,
            "requiredSuccesses": 4,
            "cases": capsule_cases,
        },
        "cleanBootBoulder": {
            "ruleset": "research/rulesets/stream-nuzlocke-v1.json",
            "bootstrapStatePath": "research/golden-states/local/boot_smoke.state",
            "caseCount": 10,
            "requiredSuccesses": 7,
            "freshStart": True,
            "cases": clean_cases,
        },
        "crossSuiteGates": {
            "maxExecutedIllegalActions": 0,
            "maxDestructiveActions": 0,
            "minimumUsefulFailureRate": 0.95,
            "humanGameplayInterventions": 0,
        },
    }


def successful_report(tmp_path: Path, *, lane: str) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    state = tmp_path / f"{lane}.state"
    screenshot = tmp_path / f"{lane}.png"
    state.write_bytes(b"state")
    screenshot.write_bytes(b"png")
    if lane == "capsuleA":
        observations = [
            {
                "action": 1,
                "chapterId": "chapter_6_capsule_a_exit_forest",
                "party": [{"speciesId": 84, "hp": 10}],
                "position": {"map_id": 0x33, "x": 1, "y": 0},
            }
        ]
        final_party = [{"species_name": "Pikachu", "hp": 10}]
        badges: list[str] = []
        fresh_start = False
    else:
        observations = [
            {
                "action": 1,
                "chapterId": "chapter_7_boulder_badge_claimed",
                "party": [{"speciesId": 177, "hp": 20}],
                "position": {"map_id": 0x02, "x": 18, "y": 17},
                "badges": ["Boulder Badge"],
            }
        ]
        final_party = [{"species_name": "Squirtle", "hp": 20}]
        badges = ["Boulder Badge"]
        fresh_start = True
    return {
        "schema": "director_segment_run_v1",
        "freshStart": fresh_start,
        "finish": {"status": "completed", "success": True},
        "history": [],
        "progressObservations": observations,
        "finalState": str(state),
        "finalScreenshot": str(screenshot),
        "finalSnapshot": {
            "mode": "overworld",
            "party": final_party,
            "badges": badges,
            "position": observations[-1]["position"],
        },
        "nuzlocke": {
            "gameOver": False,
            "badges": badges,
            "ruleset": {"enabled": lane == "cleanBootBoulder"},
        },
        "checkpoint": {
            "verdict": "healthy_needs_review",
            "summary": "Success reached.",
            "evidence": ["success=true"],
        },
    }


def write_completed_case(
    results_root: Path,
    *,
    case_id: str,
    lane: str,
    seed: int,
    tested_commit: str = "a" * 40,
) -> None:
    case_root = results_root / case_id
    lineage = case_root / "supervisor" / case_id
    report = successful_report(case_root, lane=lane)
    report.update(
        {
            "runId": "segment-000001-a1",
            "firstInferenceSeed": seed,
            "provider": {
                "provider": "lmstudio-chat",
                "model": "google/gemma-4-e4b",
            },
        }
    )
    write_json(lineage / "segments" / "segment-000001-a1" / "report.json", report)
    write_json(lineage / "state.json", {"state": "completed"})
    write_json(
        lineage / "final-checkpoint.json",
        {
            "machineReason": "chapter_success",
            "stable": True,
            "reason": "chapter_success",
        },
    )
    write_json(
        case_root / "case-metadata.json",
        {
            "schema": "milestone_5_case_metadata_v1",
            "caseId": case_id,
            "lane": lane,
            "testedCommit": tested_commit,
            "firstInferenceSeed": seed,
            "humanGameplayInterventions": 0,
            "provider": "lmstudio-chat",
            "model": "google/gemma-4-e4b",
            "temperature": 0.1,
            "romSha256": "5CA7BA01642A3B27B0CC0B5349B52792795B62D3ED977E98A09390659AF96B7B",
        },
    )


def test_frozen_suite_validates_state_and_snapshot_hashes(tmp_path: Path) -> None:
    suite = frozen_suite(tmp_path)

    assert validate_frozen_suite(suite, tmp_path) == []

    first = suite["capsuleA"]["cases"][0]
    (tmp_path / first["statePath"]).write_bytes(b"tampered")
    assert "state SHA-256 mismatch" in " ".join(
        validate_frozen_suite(suite, tmp_path)
    )


def test_success_predicates_require_target_exit_and_clean_boot_badge(
    tmp_path: Path,
) -> None:
    capsule_report = successful_report(tmp_path, lane="capsuleA")
    clean_report = successful_report(tmp_path, lane="cleanBootBoulder")

    capsule_passed, capsule_evidence = capsule_a_success([capsule_report])
    clean_passed, clean_evidence = clean_boot_boulder_success([clean_report])

    assert capsule_passed is True
    assert "north_exit_after_pikachu=true" in capsule_evidence
    assert clean_passed is True
    assert "boulder_badge=true" in clean_evidence


def test_action_audit_does_not_count_pre_input_guard_block_as_executed() -> None:
    report = {
        "nuzlocke": {"ruleset": {"enabled": True}},
        "history": [
            {
                "action": 1,
                "skillId": "handle_nickname_prompt",
                "result": {
                    "actionStarted": False,
                    "policyDecision": {
                        "classification": "hard_rule_violation",
                        "code": "nickname_required",
                    },
                },
            },
            {
                "action": 2,
                "skillId": "reset_game",
                "result": {
                    "actionStarted": True,
                    "policyDecision": {
                        "classification": "hard_rule_violation",
                        "code": "reset_forbidden",
                    },
                },
            },
        ],
    }

    illegal, destructive, literal_count = action_audit([report])

    assert [item["action"] for item in illegal] == [2]
    assert [item["action"] for item in destructive] == [2]
    assert literal_count == 0


def test_retry_attempt_replaces_discarded_attempt_in_success_lineage() -> None:
    first = {"runId": "segment-000001-a1", "history": [{"action": 1}]}
    retry = {"runId": "segment-000001-a2", "history": [{"action": 1}]}
    second = {"runId": "segment-000002-a1", "history": [{"action": 2}]}

    accepted = accepted_lineage_reports([first, retry, second])

    assert [report["runId"] for report in accepted] == [
        "segment-000001-a2",
        "segment-000002-a1",
    ]


def test_failure_usefulness_requires_category_state_screenshot_and_evidence(
    tmp_path: Path,
) -> None:
    state = tmp_path / "failed.state"
    screenshot = tmp_path / "failed.png"
    state.write_bytes(b"state")
    screenshot.write_bytes(b"png")
    report = {
        "finish": {"failureCategory": "skill_gap"},
        "checkpoint": {
            "verdict": "skill_gap",
            "summary": "Missing semantic coverage.",
            "evidence": ["skill=missing"],
        },
        "finalState": str(state),
        "finalScreenshot": str(screenshot),
    }

    assert failure_is_useful(
        final_report=report,
        final_checkpoint={},
        project_root=tmp_path,
    )
    screenshot.unlink()
    assert not failure_is_useful(
        final_report=report,
        final_checkpoint={},
        project_root=tmp_path,
    )


def test_complete_green_matrix_passes_only_with_branch_evidence(tmp_path: Path) -> None:
    suite = frozen_suite(tmp_path)
    results = tmp_path / "results"
    for case in suite["capsuleA"]["cases"]:
        write_completed_case(
            results,
            case_id=case["id"],
            lane="capsuleA",
            seed=case["firstInferenceSeed"],
        )
    for case in suite["cleanBootBoulder"]["cases"]:
        write_completed_case(
            results,
            case_id=case["id"],
            lane="cleanBootBoulder",
            seed=case["firstInferenceSeed"],
        )

    without_branches = evaluate_suite(
        suite,
        results_root=results,
        project_root=tmp_path,
    )
    with_branches = evaluate_suite(
        suite,
        results_root=results,
        project_root=tmp_path,
        deterministic_branches={"passed": True, "caseCount": 8},
    )
    assert without_branches["passed"] is False
    assert with_branches["passed"] is True, with_branches
    assert with_branches["lanes"]["capsuleA"]["successRate"] == 1.0
    assert with_branches["lanes"]["cleanBootBoulder"]["successRate"] == 1.0


def branch_artifacts(tmp_path: Path, case_id: str) -> dict[str, str]:
    paths: dict[str, str] = {}
    for key, suffix in (
        ("before_state_file", "before.state"),
        ("before_screenshot_file", "before.png"),
        ("after_state_file", "after.state"),
        ("after_screenshot_file", "after.png"),
    ):
        path = tmp_path / case_id / suffix
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(key.encode())
        paths[key] = str(path)
    return paths


def skill_branch_report(
    tmp_path: Path,
    case_id: str,
    *,
    skill_id: str,
    evidence: list[str],
    before: dict | None = None,
    after: dict | None = None,
) -> dict:
    return {
        "schema": "skill_run_report_v1",
        "skill_id": skill_id,
        "result": {
            "status": "succeeded",
            "evidence": evidence,
        },
        "before_snapshot": before or {"mode": "battle", "party": []},
        "after_snapshot": after or {"mode": "battle", "party": []},
        **branch_artifacts(tmp_path, case_id),
    }


def segment_branch_report(tmp_path: Path, case_id: str) -> dict:
    state = tmp_path / case_id / "final.state"
    screenshot = tmp_path / case_id / "final.png"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_bytes(b"state")
    screenshot.write_bytes(b"png")
    return {
        "schema": "director_segment_run_v1",
        "finalState": str(state),
        "finalScreenshot": str(screenshot),
    }


def test_deterministic_branch_evaluator_checks_real_outcomes_and_hashes(
    tmp_path: Path,
) -> None:
    squirtle = {"slot": 1, "species_name": "Squirtle", "level": 9, "hp": 29}
    old_moves = [
        {"move_id": 43},
        {"move_id": 33},
        {"move_id": 10},
        {"move_id": 45},
    ]
    new_moves = [
        {"move_id": 43},
        {"move_id": 33},
        {"move_id": 10},
        {"move_id": 30},
    ]
    reports = {
        "trainer_switch_keep": skill_branch_report(
            tmp_path,
            "trainer-keep",
            skill_id="handle_trainer_switch_prompt",
            evidence=[
                "choice=keep",
                "before_active_party_slot=1",
                "after_active_party_slot=1",
            ],
        ),
        "trainer_switch_switch": skill_branch_report(
            tmp_path,
            "trainer-switch",
            skill_id="handle_trainer_switch_prompt",
            evidence=[
                "choice=switch",
                "before_active_party_slot=1",
                "after_active_party_slot=2",
                "target_party_slot=2",
            ],
        ),
        "move_learning_skip": skill_branch_report(
            tmp_path,
            "move-skip",
            skill_id="handle_move_learning_prompt",
            evidence=["choice=skip"],
            before={"mode": "battle", "party": [{**squirtle, "moves": old_moves}]},
            after={"mode": "battle", "party": [{**squirtle, "moves": old_moves}]},
        ),
        "move_learning_replace": skill_branch_report(
            tmp_path,
            "move-replace",
            skill_id="handle_move_learning_prompt",
            evidence=["choice=replace"],
            before={"mode": "battle", "party": [{**squirtle, "moves": old_moves}]},
            after={"mode": "battle", "party": [{**squirtle, "moves": new_moves}]},
        ),
        "evolution_and_level_up": skill_branch_report(
            tmp_path,
            "evolution",
            skill_id="resolve_battle_outcome_dialogue_bundle",
            evidence=[],
            before={
                "mode": "battle",
                "party": [
                    {"slot": 1, "species_name": "Caterpie", "level": 6, "hp": 24}
                ],
            },
            after={
                "mode": "overworld",
                "party": [
                    {"slot": 1, "species_name": "Metapod", "level": 7, "hp": 25}
                ],
            },
        ),
        "forced_switch": skill_branch_report(
            tmp_path,
            "forced-switch",
            skill_id="switch_party_member",
            evidence=["after_active_party_slot=2", "after_active_species=Squirtle"],
            before={
                "mode": "battle",
                "party": [
                    {"slot": 1, "species_name": "Spearow", "hp": 0},
                    {"slot": 2, "species_name": "Squirtle", "hp": 29},
                ],
            },
        ),
        "sparse_battle_dialogue": skill_branch_report(
            tmp_path,
            "sparse-dialogue",
            skill_id="advance_battle_dialogue",
            evidence=["before_battle_type_raw=2", "battle_type_raw=0"],
            before={"mode": "battle", "party": []},
            after={"mode": "overworld", "party": []},
        ),
    }

    blackout = segment_branch_report(tmp_path, "blackout")
    blackout.update(
        {
            "finish": {
                "status": "game_over",
                "failureCategory": "nuzlocke_blackout",
            },
            "nuzlocke": {"gameOver": True},
            "finalSnapshot": {"party": [{"hp": 0}, {"hp": 0}]},
            "history": [],
            "ticks": [],
            "requests": [],
            "usage": {"totalTokens": None},
        }
    )
    reports["blackout_before_inference"] = blackout

    post_catch = segment_branch_report(tmp_path, "post-catch")
    nested_path = tmp_path / "post-catch" / "pokedex-report.json"
    write_json(
        nested_path,
        {
            "execution": {
                "timeline": [
                    {"summary": "Post-catch Pokedex registration page is visible."}
                ]
            }
        },
    )
    post_catch.update(
        {
            "history": [
                {"skillId": "attempt_catch", "result": {"status": "succeeded"}},
                {
                    "skillId": "resolve_battle_outcome_dialogue_bundle",
                    "result": {"report_path": str(nested_path)},
                },
                {
                    "skillId": "handle_nickname_prompt",
                    "args": {"choice": "accept"},
                    "result": {"status": "succeeded"},
                },
                {
                    "skillId": "enter_nickname_text",
                    "result": {"status": "succeeded"},
                },
            ],
            "finalSnapshot": {
                "party": [{"species_name": "Pikachu", "nickname": "SPARK"}]
            },
            "nuzlocke": {"gameOver": False, "deaths": []},
        }
    )
    reports["post_catch_pokedex_nickname"] = post_catch

    brock = segment_branch_report(tmp_path, "brock")
    brock.update(
        {
            "status": "completed",
            "finish": {"status": "completed", "success": True},
            "nuzlocke": {"gameOver": False, "badges": ["Boulder Badge"]},
        }
    )
    reports["brock_badge_completion"] = brock

    cases = []
    for predicate, report in reports.items():
        report_path = tmp_path / predicate / "report.json"
        write_json(report_path, report)
        cases.append(
            {
                "id": predicate.replace("_", "-"),
                "predicate": predicate,
                "reportPath": str(report_path),
                "reportSha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema": "milestone_5_deterministic_branches_v1",
        "caseCount": len(cases),
        "cases": cases,
    }

    summary = evaluate_deterministic_branches(manifest, project_root=tmp_path)
    assert summary["passed"] is True, summary
    assert summary["passedCount"] == 10

    manifest["cases"][0]["reportSha256"] = "0" * 64
    tampered = evaluate_deterministic_branches(manifest, project_root=tmp_path)
    assert tampered["passed"] is False
    assert "report SHA-256 mismatch" in tampered["cases"][0]["issues"]
