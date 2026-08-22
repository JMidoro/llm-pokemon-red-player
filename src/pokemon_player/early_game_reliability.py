from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from pokemon_player import memory_map as mm


SUITE_SCHEMA = "milestone_5_evaluation_suite_v1"
SUMMARY_SCHEMA = "milestone_5_evaluation_summary_v1"
BRANCH_MANIFEST_SCHEMA = "milestone_5_deterministic_branches_v1"
BRANCH_SUMMARY_SCHEMA = "milestone_5_deterministic_branch_summary_v1"
REQUIRED_BRANCH_PREDICATES = frozenset(
    {
        "blackout_before_inference",
        "brock_badge_completion",
        "evolution_and_level_up",
        "forced_switch",
        "move_learning_replace",
        "move_learning_skip",
        "post_catch_pokedex_nickname",
        "sparse_battle_dialogue",
        "trainer_switch_keep",
        "trainer_switch_switch",
    }
)
PIKACHU_SPECIES_IDS = frozenset(
    species_id
    for species_id, species_name in mm.SPECIES_NAMES.items()
    if species_name == "Pikachu"
)
INFRASTRUCTURE_FAILURES = frozenset(
    {
        "authentication",
        "connection",
        "provider_timeout",
        "provider_unavailable",
        "rate_limit",
        "timeout",
    }
)
DESTRUCTIVE_SKILLS = frozenset(
    {
        "emergency_reset",
        "load_state",
        "reload_state",
        "reset_game",
        "restart_game",
    }
)
SEGMENT_RUN_ID = re.compile(r"^segment-(\d+)-a(\d+)$")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_frozen_suite(suite: Mapping[str, Any], project_root: Path) -> list[str]:
    issues: list[str] = []
    if suite.get("schema") != SUITE_SCHEMA:
        issues.append(f"schema must be {SUITE_SCHEMA}")
    if suite.get("status") != "frozen_before_model_evaluation":
        issues.append("suite status must remain frozen_before_model_evaluation")
    if not str(suite.get("frozenAtUtc") or ""):
        issues.append("frozenAtUtc must be recorded")
    provider = _mapping(suite.get("providerProfile"))
    if provider.get("provider") != "lmstudio-chat":
        issues.append("Milestone 5 provider must be lmstudio-chat")
    if provider.get("hostedInferenceAllowed") is not False:
        issues.append("hostedInferenceAllowed must be false")
    if provider.get("model") != "google/gemma-4-e4b":
        issues.append("Milestone 5 model must remain google/gemma-4-e4b")
    if provider.get("temperature") != 0.1:
        issues.append("Milestone 5 temperature must remain frozen at 0.1")
    rom = _mapping(suite.get("romProfile"))
    expected_rom = {
        "title": "POKEMON RED",
        "sizeBytes": 1_048_576,
        "sha256": "5CA7BA01642A3B27B0CC0B5349B52792795B62D3ED977E98A09390659AF96B7B",
    }
    for key, expected in expected_rom.items():
        if rom.get(key) != expected:
            issues.append(f"romProfile.{key} must remain pinned to {expected}")

    seen_ids: set[str] = set()
    seen_seeds: set[int] = set()
    capsule = _mapping(suite.get("capsuleA"))
    if capsule.get("ruleset") != "research/rulesets/standard-run-v1.json":
        issues.append("capsuleA ruleset must remain standard-run-v1")
    capsule_cases = _mapping_list(capsule.get("cases"))
    _validate_case_count(capsule, capsule_cases, "capsuleA", issues)
    if int(capsule.get("requiredSuccesses") or 0) != 4:
        issues.append("capsuleA.requiredSuccesses must remain frozen at 4")
    for case in capsule_cases:
        _validate_case_identity(case, seen_ids, seen_seeds, issues)
        _validate_capsule_state(case, project_root, issues)

    clean_boot = _mapping(suite.get("cleanBootBoulder"))
    if clean_boot.get("ruleset") != "research/rulesets/stream-nuzlocke-v1.json":
        issues.append("cleanBootBoulder ruleset must remain stream-nuzlocke-v1")
    if not str(clean_boot.get("bootstrapStatePath") or ""):
        issues.append("cleanBootBoulder bootstrapStatePath must be recorded")
    clean_cases = _mapping_list(clean_boot.get("cases"))
    _validate_case_count(clean_boot, clean_cases, "cleanBootBoulder", issues)
    if int(clean_boot.get("requiredSuccesses") or 0) != 7:
        issues.append("cleanBootBoulder.requiredSuccesses must remain frozen at 7")
    if clean_boot.get("freshStart") is not True:
        issues.append("cleanBootBoulder.freshStart must be true")
    for case in clean_cases:
        _validate_case_identity(case, seen_ids, seen_seeds, issues)
    cross = _mapping(suite.get("crossSuiteGates"))
    expected_cross = {
        "maxExecutedIllegalActions": 0,
        "maxDestructiveActions": 0,
        "minimumUsefulFailureRate": 0.95,
        "humanGameplayInterventions": 0,
    }
    for key, expected in expected_cross.items():
        if cross.get(key) != expected:
            issues.append(f"crossSuiteGates.{key} must remain {expected}")
    return issues


def evaluate_case(
    *,
    lane: str,
    case: Mapping[str, Any],
    case_root: Path,
    project_root: Path,
    provider_profile: Mapping[str, Any] | None = None,
    rom_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    case_id = str(case.get("id") or "")
    lineage_root = case_root / "supervisor" / "lineages" / case_id
    attempt_reports = load_segment_reports(lineage_root)
    reports = accepted_lineage_reports(attempt_reports)
    metadata_path = case_root / "case-metadata.json"
    metadata = load_json(metadata_path) if metadata_path.is_file() else {}
    final_checkpoint_path = lineage_root / "final-checkpoint.json"
    final_checkpoint = (
        load_json(final_checkpoint_path) if final_checkpoint_path.is_file() else {}
    )
    supervisor_state_path = lineage_root / "state.json"
    supervisor_state = (
        load_json(supervisor_state_path) if supervisor_state_path.is_file() else {}
    )
    evidence_issues = _case_evidence_issues(
        lane=lane,
        case=case,
        metadata=metadata,
        reports=attempt_reports,
        provider_profile=provider_profile,
        rom_profile=rom_profile,
    )

    if not attempt_reports:
        return {
            "id": case_id,
            "lane": lane,
            "status": "incomplete",
            "success": False,
            "usefulFailure": False,
            "summary": "No completed segment report exists for this frozen case.",
            "reportCount": 0,
            "attemptReportCount": 0,
            "executedIllegalActions": [],
            "destructiveActions": [],
            "literalButtonActions": 0,
            "humanGameplayInterventions": metadata.get("humanGameplayInterventions"),
        }

    final_report = reports[-1]
    provider_failure = _provider_failure(reports)
    running = str(supervisor_state.get("state") or "") in {
        "idle",
        "starting",
        "running",
        "checkpointing",
    }
    if evidence_issues:
        status = "invalid_evidence"
        success = False
        success_evidence = evidence_issues
    elif running and not final_checkpoint:
        status = "running"
        success = False
        success_evidence: list[str] = []
    elif provider_failure:
        status = "infrastructure_abort"
        success = False
        success_evidence = [f"provider_failure={provider_failure}"]
    else:
        status = "completed"
        if lane == "capsuleA":
            success, success_evidence = capsule_a_success(reports, project_root)
        elif lane == "cleanBootBoulder":
            success, success_evidence = clean_boot_boulder_success(
                reports, project_root
            )
        else:
            raise ValueError(f"Unsupported Milestone 5 lane: {lane}")

    illegal_actions, destructive_actions, literal_count = action_audit(
        attempt_reports
    )
    human_interventions = metadata.get("humanGameplayInterventions")
    useful_failure = False
    if status == "completed" and not success:
        useful_failure = failure_is_useful(
            final_report=final_report,
            final_checkpoint=final_checkpoint,
            project_root=project_root,
        )
    elif status == "infrastructure_abort":
        useful_failure = failure_is_useful(
            final_report=final_report,
            final_checkpoint=final_checkpoint,
            project_root=project_root,
        )

    return {
        "id": case_id,
        "lane": lane,
        "status": status,
        "success": success,
        "usefulFailure": useful_failure,
        "summary": (
            "Frozen case success predicate passed."
            if success
            else "Frozen case success predicate did not pass."
        ),
        "evidence": success_evidence,
        "evidenceIssues": evidence_issues,
        "reportCount": len(reports),
        "attemptReportCount": len(attempt_reports),
        "supervisorReason": final_checkpoint.get("machineReason")
        or final_checkpoint.get("reason"),
        "testedCommit": metadata.get("testedCommit"),
        "firstInferenceSeed": metadata.get("firstInferenceSeed"),
        "executedIllegalActions": illegal_actions,
        "destructiveActions": destructive_actions,
        "literalButtonActions": literal_count,
        "humanGameplayInterventions": human_interventions,
    }


def evaluate_suite(
    suite: Mapping[str, Any],
    *,
    results_root: Path,
    project_root: Path,
    deterministic_branches: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    issues = validate_frozen_suite(suite, project_root)
    cases: list[dict[str, Any]] = []
    for lane in ("capsuleA", "cleanBootBoulder"):
        lane_spec = _mapping(suite.get(lane))
        for case in _mapping_list(lane_spec.get("cases")):
            case_id = str(case.get("id") or "")
            cases.append(
                evaluate_case(
                    lane=lane,
                    case=case,
                    case_root=results_root / case_id,
                    project_root=project_root,
                    provider_profile=_mapping(suite.get("providerProfile")),
                    rom_profile=_mapping(suite.get("romProfile")),
                )
            )

    lane_summaries: dict[str, Any] = {}
    for lane in ("capsuleA", "cleanBootBoulder"):
        lane_spec = _mapping(suite.get(lane))
        lane_cases = [item for item in cases if item["lane"] == lane]
        successes = sum(1 for item in lane_cases if item["success"])
        required = int(lane_spec.get("requiredSuccesses") or 0)
        complete = all(item["status"] == "completed" for item in lane_cases)
        lane_summaries[lane] = {
            "successes": successes,
            "caseCount": len(lane_cases),
            "requiredSuccesses": required,
            "successRate": successes / max(len(lane_cases), 1),
            "allCasesCompleted": complete,
            "passed": complete and successes >= required,
        }

    gameplay_failures = [
        item
        for item in cases
        if item["status"] == "completed" and not item["success"]
    ]
    useful_failures = sum(1 for item in gameplay_failures if item["usefulFailure"])
    useful_rate = (
        useful_failures / len(gameplay_failures)
        if gameplay_failures
        else 1.0
    )
    executed_illegal = sum(len(item["executedIllegalActions"]) for item in cases)
    destructive = sum(len(item["destructiveActions"]) for item in cases)
    literal_actions = sum(int(item["literalButtonActions"]) for item in cases)
    human_values = [item.get("humanGameplayInterventions") for item in cases]
    human_known = all(isinstance(value, int) for value in human_values)
    human_total = sum(int(value) for value in human_values if isinstance(value, int))
    tested_commits = {
        str(item["testedCommit"])
        for item in cases
        if item.get("testedCommit")
    }
    branch_passed = bool(
        deterministic_branches
        and deterministic_branches.get("passed") is True
    )
    cross_spec = _mapping(suite.get("crossSuiteGates"))
    cross_gates = {
        "executedIllegalActions": executed_illegal,
        "destructiveActions": destructive,
        "literalButtonActions": literal_actions,
        "usefulGameplayFailures": useful_failures,
        "gameplayFailures": len(gameplay_failures),
        "usefulFailureRate": useful_rate,
        "humanGameplayInterventions": human_total if human_known else None,
        "singleTestedCommit": len(tested_commits) == 1,
        "deterministicBranchesPassed": branch_passed,
    }
    cross_passed = (
        executed_illegal <= int(cross_spec.get("maxExecutedIllegalActions") or 0)
        and destructive <= int(cross_spec.get("maxDestructiveActions") or 0)
        and useful_rate >= float(cross_spec.get("minimumUsefulFailureRate") or 0.95)
        and literal_actions == 0
        and human_known
        and human_total == int(cross_spec.get("humanGameplayInterventions") or 0)
        and len(tested_commits) == 1
        and branch_passed
    )
    all_complete = all(item["status"] == "completed" for item in cases)
    passed = (
        not issues
        and all_complete
        and all(summary["passed"] for summary in lane_summaries.values())
        and cross_passed
    )
    return {
        "schema": SUMMARY_SCHEMA,
        "passed": passed,
        "suiteIssues": issues,
        "lanes": lane_summaries,
        "crossSuite": {**cross_gates, "passed": cross_passed},
        "deterministicBranches": deterministic_branches or {"passed": False},
        "testedCommits": sorted(tested_commits),
        "cases": cases,
    }


def evaluate_deterministic_branches(
    manifest: Mapping[str, Any], *, project_root: Path
) -> dict[str, Any]:
    issues: list[str] = []
    if manifest.get("schema") != BRANCH_MANIFEST_SCHEMA:
        issues.append(f"schema must be {BRANCH_MANIFEST_SCHEMA}")
    cases = _mapping_list(manifest.get("cases"))
    if int(manifest.get("caseCount") or -1) != len(cases):
        issues.append("caseCount does not match cases")

    ids: set[str] = set()
    predicates: set[str] = set()
    results: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("id") or "")
        predicate = str(case.get("predicate") or "")
        case_issues: list[str] = []
        evidence: list[str] = []
        if not case_id:
            case_issues.append("case id is missing")
        elif case_id in ids:
            case_issues.append(f"duplicate case id: {case_id}")
        ids.add(case_id)
        if not predicate:
            case_issues.append("predicate is missing")
        elif predicate in predicates:
            case_issues.append(f"duplicate predicate: {predicate}")
        predicates.add(predicate)

        report_path = _project_path(project_root, case.get("reportPath"))
        report: dict[str, Any] = {}
        actual_hash: str | None = None
        if report_path is None or not report_path.is_file():
            case_issues.append("report is missing")
        else:
            actual_hash = sha256_file(report_path)
            expected_hash = str(case.get("reportSha256") or "").lower()
            if actual_hash != expected_hash:
                case_issues.append("report SHA-256 mismatch")
            try:
                report = load_json(report_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                case_issues.append(f"report could not be loaded: {exc}")

        for supporting in _mapping_list(case.get("supportingReports")):
            supporting_path = _project_path(project_root, supporting.get("path"))
            if supporting_path is None or not supporting_path.is_file():
                case_issues.append("supporting report is missing")
                continue
            if sha256_file(supporting_path) != str(
                supporting.get("sha256") or ""
            ).lower():
                case_issues.append("supporting report SHA-256 mismatch")

        if report:
            case_issues.extend(_branch_artifact_issues(report, project_root))
            predicate_passed, predicate_evidence = _evaluate_branch_predicate(
                predicate, report, project_root
            )
            evidence.extend(predicate_evidence)
            if not predicate_passed:
                case_issues.append(f"predicate failed: {predicate}")

        results.append(
            {
                "id": case_id,
                "predicate": predicate,
                "passed": not case_issues,
                "reportPath": str(case.get("reportPath") or ""),
                "reportSha256": actual_hash,
                "evidence": evidence,
                "issues": case_issues,
            }
        )

    missing = sorted(REQUIRED_BRANCH_PREDICATES - predicates)
    extra = sorted(predicates - REQUIRED_BRANCH_PREDICATES)
    if missing:
        issues.append(f"missing required predicates: {','.join(missing)}")
    if extra:
        issues.append(f"unsupported predicates: {','.join(extra)}")
    passed_count = sum(1 for case in results if case["passed"])
    passed = not issues and passed_count == len(results) and bool(results)
    return {
        "schema": BRANCH_SUMMARY_SCHEMA,
        "passed": passed,
        "caseCount": len(results),
        "passedCount": passed_count,
        "issues": issues,
        "cases": results,
    }


def _case_evidence_issues(
    *,
    lane: str,
    case: Mapping[str, Any],
    metadata: Mapping[str, Any],
    reports: Iterable[Mapping[str, Any]],
    provider_profile: Mapping[str, Any] | None,
    rom_profile: Mapping[str, Any] | None,
) -> list[str]:
    issues: list[str] = []
    case_id = str(case.get("id") or "")
    expected_seed = case.get("firstInferenceSeed")
    expected_provider = _mapping(provider_profile).get("provider")
    expected_model = _mapping(provider_profile).get("model")
    expected_temperature = _mapping(provider_profile).get("temperature")
    expected_rom_sha256 = _mapping(rom_profile).get("sha256")

    expected_metadata = {
        "schema": "milestone_5_case_metadata_v1",
        "caseId": case_id,
        "lane": lane,
        "firstInferenceSeed": expected_seed,
        "provider": expected_provider,
        "model": expected_model,
        "temperature": expected_temperature,
        "humanGameplayInterventions": 0,
        "romSha256": expected_rom_sha256,
    }
    for key, expected in expected_metadata.items():
        if expected is not None and metadata.get(key) != expected:
            issues.append(
                f"metadata.{key}={metadata.get(key)!r}; expected {expected!r}"
            )
    tested_commit = str(metadata.get("testedCommit") or "")
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", tested_commit):
        issues.append("metadata.testedCommit is not a full commit hash")

    grouped: dict[int, list[tuple[int, Mapping[str, Any]]]] = {}
    unsequenced: list[Mapping[str, Any]] = []
    for report in reports:
        identity = _segment_report_identity(report)
        if identity is None:
            unsequenced.append(report)
            continue
        sequence, attempt = identity
        grouped.setdefault(sequence, []).append((attempt, report))
    if unsequenced:
        issues.append("one or more reports lack a durable segment runId")

    next_seed = expected_seed if isinstance(expected_seed, int) else None
    for sequence in sorted(grouped):
        attempts = sorted(grouped[sequence], key=lambda item: item[0])
        for attempt, report in attempts:
            actual_seed = report.get("firstInferenceSeed")
            if next_seed is not None and actual_seed != next_seed:
                issues.append(
                    f"segment-{sequence:06d}-a{attempt} firstInferenceSeed="
                    f"{actual_seed!r}; expected {next_seed}"
                )
            report_provider = _mapping(report.get("provider"))
            if expected_provider and report_provider.get("provider") != expected_provider:
                issues.append(
                    f"segment-{sequence:06d}-a{attempt} provider mismatch"
                )
            if expected_model and report_provider.get("model") != expected_model:
                issues.append(f"segment-{sequence:06d}-a{attempt} model mismatch")
        accepted = attempts[-1][1]
        history = accepted.get("history")
        if next_seed is not None:
            next_seed += len(history) if isinstance(history, list) else 0
    return issues


def _segment_report_identity(report: Mapping[str, Any]) -> tuple[int, int] | None:
    match = SEGMENT_RUN_ID.fullmatch(str(report.get("runId") or ""))
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def load_segment_reports(lineage_root: Path) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    segments = lineage_root / "segments"
    if not segments.is_dir():
        return reports
    for report_path in sorted(segments.glob("segment-*/report.json")):
        try:
            reports.append(load_json(report_path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return reports


def accepted_lineage_reports(
    reports: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Select the final attempt for each durable supervisor sequence."""

    selected: dict[int, tuple[int, dict[str, Any]]] = {}
    unsequenced: list[dict[str, Any]] = []
    for report in reports:
        copied = dict(report)
        identity = _segment_report_identity(copied)
        if identity is None:
            unsequenced.append(copied)
            continue
        sequence, attempt = identity
        current = selected.get(sequence)
        if current is None or attempt > current[0]:
            selected[sequence] = (attempt, copied)
    ordered = [selected[key][1] for key in sorted(selected)]
    return ordered + unsequenced


def capsule_a_success(
    reports: Iterable[Mapping[str, Any]], project_root: Path | None = None
) -> tuple[bool, list[str]]:
    target_seen = False
    exit_after_target = False
    stable = False
    game_over = False
    for report in reports:
        for observation in _ordered_observations(report):
            if _party_has_pikachu(observation.get("party")):
                target_seen = True
            chapter_id = str(observation.get("chapterId") or "")
            if target_seen and (
                _is_forest_north_exit(observation.get("position"))
                or chapter_id.startswith("chapter_7")
            ):
                exit_after_target = True
        final = _mapping(report.get("finalSnapshot"))
        if _party_has_pikachu(final.get("party")):
            target_seen = True
        if target_seen and _is_forest_north_exit(final.get("position")):
            exit_after_target = True
        stable = _report_artifacts_exist(report, project_root)
        game_over = game_over or bool(_mapping(report.get("nuzlocke")).get("gameOver"))
    evidence = [
        f"pikachu_observed={str(target_seen).lower()}",
        f"north_exit_after_pikachu={str(exit_after_target).lower()}",
        f"final_artifacts_stable={str(stable).lower()}",
        f"game_over={str(game_over).lower()}",
    ]
    return target_seen and exit_after_target and stable and not game_over, evidence


def clean_boot_boulder_success(
    reports: Iterable[Mapping[str, Any]],
    project_root: Path | None = None,
) -> tuple[bool, list[str]]:
    report_list = list(reports)
    badge_seen = False
    fresh_start = bool(report_list and report_list[0].get("freshStart") is True)
    game_over = False
    for report in report_list:
        final = _mapping(report.get("finalSnapshot"))
        badge_seen = badge_seen or _has_boulder_badge(final.get("badges"))
        badge_seen = badge_seen or _has_boulder_badge(
            _mapping(report.get("nuzlocke")).get("badges")
        )
        for observation in _ordered_observations(report):
            badge_seen = badge_seen or _has_boulder_badge(observation.get("badges"))
        game_over = game_over or bool(_mapping(report.get("nuzlocke")).get("gameOver"))
    stable = bool(
        report_list and _report_artifacts_exist(report_list[-1], project_root)
    )
    evidence = [
        f"fresh_start={str(fresh_start).lower()}",
        f"boulder_badge={str(badge_seen).lower()}",
        f"final_artifacts_stable={str(stable).lower()}",
        f"game_over={str(game_over).lower()}",
    ]
    return fresh_start and badge_seen and stable and not game_over, evidence


def action_audit(
    reports: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    illegal: list[dict[str, Any]] = []
    destructive: list[dict[str, Any]] = []
    literal_count = 0
    for segment_index, report in enumerate(reports, start=1):
        rules_enabled = bool(
            _mapping(_mapping(report.get("nuzlocke")).get("ruleset")).get("enabled")
        )
        for item in _mapping_list(report.get("history")):
            skill_id = str(item.get("skillId") or "")
            result = _mapping(item.get("result"))
            if skill_id == "literal_button_press":
                literal_count += 1
            policy = _mapping(result.get("policyDecision"))
            action_started = result.get("actionStarted")
            if (
                rules_enabled
                and policy.get("classification") == "hard_rule_violation"
                and action_started is not False
            ):
                illegal.append(
                    {
                        "segment": segment_index,
                        "action": item.get("action"),
                        "skillId": skill_id,
                        "code": policy.get("code"),
                        "actionStarted": action_started,
                    }
                )
            if skill_id in DESTRUCTIVE_SKILLS and action_started is not False:
                destructive.append(
                    {
                        "segment": segment_index,
                        "action": item.get("action"),
                        "skillId": skill_id,
                    }
                )
    return illegal, destructive, literal_count


def failure_is_useful(
    *,
    final_report: Mapping[str, Any],
    final_checkpoint: Mapping[str, Any],
    project_root: Path,
) -> bool:
    finish = _mapping(final_report.get("finish"))
    checkpoint = _mapping(final_report.get("checkpoint"))
    category = (
        finish.get("failureCategory")
        or final_checkpoint.get("machineReason")
        or checkpoint.get("verdict")
    )
    evidence = checkpoint.get("evidence")
    has_evidence = bool(
        (isinstance(evidence, list) and evidence)
        or checkpoint.get("summary")
        or final_checkpoint.get("reason")
    )
    state = _resolve_report_artifact(final_report, "finalState", project_root)
    screenshot = _resolve_report_artifact(final_report, "finalScreenshot", project_root)
    return bool(
        category
        and has_evidence
        and state is not None
        and state.is_file()
        and screenshot is not None
        and screenshot.is_file()
    )


def _branch_artifact_issues(
    report: Mapping[str, Any], project_root: Path
) -> list[str]:
    issues: list[str] = []
    if report.get("schema") == "skill_run_report_v1":
        keys = (
            "before_state_file",
            "before_screenshot_file",
            "after_state_file",
            "after_screenshot_file",
        )
    elif report.get("schema") == "director_segment_run_v1":
        keys = ("finalState", "finalScreenshot")
    else:
        return ["unsupported evidence report schema"]
    for key in keys:
        if _project_path(project_root, report.get(key)) is None:
            issues.append(f"{key} is missing")
            continue
        path = _project_path(project_root, report.get(key))
        if path is None or not path.is_file():
            issues.append(f"{key} artifact is missing")
    return issues


def _evaluate_branch_predicate(
    predicate: str, report: Mapping[str, Any], project_root: Path
) -> tuple[bool, list[str]]:
    evaluators = {
        "blackout_before_inference": _branch_blackout_before_inference,
        "brock_badge_completion": _branch_brock_badge_completion,
        "evolution_and_level_up": _branch_evolution_and_level_up,
        "forced_switch": _branch_forced_switch,
        "move_learning_replace": _branch_move_learning_replace,
        "move_learning_skip": _branch_move_learning_skip,
        "post_catch_pokedex_nickname": _branch_post_catch_pokedex_nickname,
        "sparse_battle_dialogue": _branch_sparse_battle_dialogue,
        "trainer_switch_keep": _branch_trainer_switch_keep,
        "trainer_switch_switch": _branch_trainer_switch_switch,
    }
    evaluator = evaluators.get(predicate)
    if evaluator is None:
        return False, [f"unsupported_predicate={predicate}"]
    return evaluator(report, project_root)


def _branch_trainer_switch_keep(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    evidence = _result_evidence(report)
    passed = (
        _skill_succeeded(report, "handle_trainer_switch_prompt")
        and evidence.get("choice") == "keep"
        and evidence.get("before_active_party_slot") == "1"
        and evidence.get("after_active_party_slot") == "1"
    )
    return passed, _predicate_evidence(
        skill_succeeded=_skill_succeeded(report, "handle_trainer_switch_prompt"),
        choice=evidence.get("choice"),
        before_active=evidence.get("before_active_party_slot"),
        after_active=evidence.get("after_active_party_slot"),
    )


def _branch_trainer_switch_switch(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    evidence = _result_evidence(report)
    passed = (
        _skill_succeeded(report, "handle_trainer_switch_prompt")
        and evidence.get("choice") == "switch"
        and evidence.get("before_active_party_slot") == "1"
        and evidence.get("after_active_party_slot") == "2"
        and evidence.get("target_party_slot") == "2"
    )
    return passed, _predicate_evidence(
        skill_succeeded=_skill_succeeded(report, "handle_trainer_switch_prompt"),
        choice=evidence.get("choice"),
        before_active=evidence.get("before_active_party_slot"),
        after_active=evidence.get("after_active_party_slot"),
        target=evidence.get("target_party_slot"),
    )


def _branch_move_learning_skip(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    before = _party_moves(report, "before_snapshot", 1)
    after = _party_moves(report, "after_snapshot", 1)
    evidence = _result_evidence(report)
    passed = (
        _skill_succeeded(report, "handle_move_learning_prompt")
        and evidence.get("choice") == "skip"
        and before == after
        and len(before) == 4
    )
    return passed, _predicate_evidence(
        skill_succeeded=_skill_succeeded(report, "handle_move_learning_prompt"),
        choice=evidence.get("choice"),
        before_moves=before,
        after_moves=after,
    )


def _branch_move_learning_replace(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    before = _party_moves(report, "before_snapshot", 1)
    after = _party_moves(report, "after_snapshot", 1)
    evidence = _result_evidence(report)
    passed = (
        _skill_succeeded(report, "handle_move_learning_prompt")
        and evidence.get("choice") == "replace"
        and 45 in before
        and 45 not in after
        and 30 in after
        and len(before) == len(after) == 4
    )
    return passed, _predicate_evidence(
        skill_succeeded=_skill_succeeded(report, "handle_move_learning_prompt"),
        choice=evidence.get("choice"),
        before_moves=before,
        after_moves=after,
    )


def _branch_evolution_and_level_up(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    before = _party_member(report, "before_snapshot", 1)
    after = _party_member(report, "after_snapshot", 1)
    passed = (
        _skill_succeeded(report, "resolve_battle_outcome_dialogue_bundle")
        and str(before.get("species_name")) == "Caterpie"
        and int(before.get("level") or 0) == 6
        and str(after.get("species_name")) == "Metapod"
        and int(after.get("level") or 0) == 7
        and _mapping(report.get("before_snapshot")).get("mode") == "battle"
        and _mapping(report.get("after_snapshot")).get("mode") == "overworld"
    )
    return passed, _predicate_evidence(
        skill_succeeded=_skill_succeeded(
            report, "resolve_battle_outcome_dialogue_bundle"
        ),
        before_species=before.get("species_name"),
        before_level=before.get("level"),
        after_species=after.get("species_name"),
        after_level=after.get("level"),
    )


def _branch_forced_switch(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    before_one = _party_member(report, "before_snapshot", 1)
    before_two = _party_member(report, "before_snapshot", 2)
    evidence = _result_evidence(report)
    passed = (
        _skill_succeeded(report, "switch_party_member")
        and str(before_one.get("species_name")) == "Spearow"
        and int(before_one.get("hp") or 0) == 0
        and str(before_two.get("species_name")) == "Squirtle"
        and int(before_two.get("hp") or 0) > 0
        and evidence.get("after_active_party_slot") == "2"
        and evidence.get("after_active_species") == "Squirtle"
    )
    return passed, _predicate_evidence(
        skill_succeeded=_skill_succeeded(report, "switch_party_member"),
        fainted_active=before_one.get("species_name"),
        fainted_hp=before_one.get("hp"),
        replacement=before_two.get("species_name"),
        after_active=evidence.get("after_active_party_slot"),
    )


def _branch_blackout_before_inference(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    finish = _mapping(report.get("finish"))
    nuzlocke = _mapping(report.get("nuzlocke"))
    party = _mapping_list(_mapping(report.get("finalSnapshot")).get("party"))
    usage = _mapping(report.get("usage"))
    token_total = sum(
        int(value)
        for key, value in usage.items()
        if key.lower().endswith("tokens") and isinstance(value, (int, float))
    )
    passed = (
        report.get("schema") == "director_segment_run_v1"
        and finish.get("status") == "game_over"
        and finish.get("failureCategory") == "nuzlocke_blackout"
        and nuzlocke.get("gameOver") is True
        and bool(party)
        and all(int(member.get("hp") or 0) == 0 for member in party)
        and len(_mapping_list(report.get("history"))) == 0
        and len(_mapping_list(report.get("ticks"))) == 0
        and len(report.get("requests") or []) == 0
        and token_total == 0
    )
    return passed, _predicate_evidence(
        finish_status=finish.get("status"),
        failure_category=finish.get("failureCategory"),
        game_over=nuzlocke.get("gameOver"),
        party_all_fainted=bool(party)
        and all(int(member.get("hp") or 0) == 0 for member in party),
        history_count=len(_mapping_list(report.get("history"))),
        request_count=len(report.get("requests") or []),
        token_total=token_total,
    )


def _branch_post_catch_pokedex_nickname(
    report: Mapping[str, Any], project_root: Path
) -> tuple[bool, list[str]]:
    history = _mapping_list(report.get("history"))
    catch_succeeded = any(
        item.get("skillId") == "attempt_catch"
        and _mapping(item.get("result")).get("status") == "succeeded"
        for item in history
    )
    nickname_accepted = any(
        item.get("skillId") == "handle_nickname_prompt"
        and _mapping(item.get("args")).get("choice") == "accept"
        and _mapping(item.get("result")).get("status") == "succeeded"
        for item in history
    )
    nickname_entered = any(
        item.get("skillId") == "enter_nickname_text"
        and _mapping(item.get("result")).get("status") == "succeeded"
        for item in history
    )
    pikachu = next(
        (
            member
            for member in _mapping_list(
                _mapping(report.get("finalSnapshot")).get("party")
            )
            if str(member.get("species_name")) == "Pikachu"
        ),
        {},
    )
    deaths = _mapping_list(_mapping(report.get("nuzlocke")).get("deaths"))
    species_zero_death = any(
        "species 0" in str(item.get("speciesName") or "").lower()
        or "species0" in str(item.get("pokemonId") or "").lower()
        for item in deaths
    )
    pokedex_seen = False
    for item in history:
        if item.get("skillId") != "resolve_battle_outcome_dialogue_bundle":
            continue
        nested = _project_path(
            project_root, _mapping(item.get("result")).get("report_path")
        )
        if nested is None or not nested.is_file():
            continue
        nested_report = load_json(nested)
        for event in _mapping_list(_mapping(nested_report.get("execution")).get("timeline")):
            if "Pokedex registration" in str(event.get("summary") or ""):
                pokedex_seen = True
                break
    passed = (
        report.get("schema") == "director_segment_run_v1"
        and catch_succeeded
        and pokedex_seen
        and nickname_accepted
        and nickname_entered
        and str(pikachu.get("nickname") or "").strip() != ""
        and not species_zero_death
        and _mapping(report.get("nuzlocke")).get("gameOver") is False
    )
    return passed, _predicate_evidence(
        catch_succeeded=catch_succeeded,
        pokedex_registration_seen=pokedex_seen,
        nickname_accepted=nickname_accepted,
        nickname_entered=nickname_entered,
        final_pikachu_nickname=pikachu.get("nickname"),
        species_zero_death=species_zero_death,
    )


def _branch_brock_badge_completion(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    finish = _mapping(report.get("finish"))
    nuzlocke = _mapping(report.get("nuzlocke"))
    badges = nuzlocke.get("badges")
    passed = (
        report.get("schema") == "director_segment_run_v1"
        and report.get("status") == "completed"
        and finish.get("status") == "completed"
        and finish.get("success") is True
        and _has_boulder_badge(badges)
        and nuzlocke.get("gameOver") is False
    )
    return passed, _predicate_evidence(
        report_status=report.get("status"),
        finish_status=finish.get("status"),
        finish_success=finish.get("success"),
        boulder_badge=_has_boulder_badge(badges),
        game_over=nuzlocke.get("gameOver"),
    )


def _branch_sparse_battle_dialogue(
    report: Mapping[str, Any], _project_root: Path
) -> tuple[bool, list[str]]:
    before_mode = _mapping(report.get("before_snapshot")).get("mode")
    after_mode = _mapping(report.get("after_snapshot")).get("mode")
    evidence = _result_evidence(report)
    passed = (
        _skill_succeeded(report, "advance_battle_dialogue")
        and before_mode == "battle"
        and after_mode == "overworld"
        and evidence.get("before_battle_type_raw") == "2"
        and evidence.get("battle_type_raw") == "0"
    )
    return passed, _predicate_evidence(
        skill_succeeded=_skill_succeeded(report, "advance_battle_dialogue"),
        before_mode=before_mode,
        after_mode=after_mode,
        before_battle_type=evidence.get("before_battle_type_raw"),
        after_battle_type=evidence.get("battle_type_raw"),
    )


def _skill_succeeded(report: Mapping[str, Any], skill_id: str) -> bool:
    return (
        report.get("schema") == "skill_run_report_v1"
        and report.get("skill_id") == skill_id
        and _mapping(report.get("result")).get("status") == "succeeded"
    )


def _result_evidence(report: Mapping[str, Any]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in _mapping(report.get("result")).get("evidence") or []:
        text = str(item)
        if "=" in text:
            key, value = text.split("=", 1)
            parsed[key] = value
    return parsed


def _party_member(
    report: Mapping[str, Any], snapshot_key: str, slot: int
) -> dict[str, Any]:
    party = _mapping_list(_mapping(report.get(snapshot_key)).get("party"))
    return next(
        (member for member in party if int(member.get("slot") or 0) == slot), {}
    )


def _party_moves(
    report: Mapping[str, Any], snapshot_key: str, slot: int
) -> tuple[int, ...]:
    member = _party_member(report, snapshot_key, slot)
    return tuple(
        int(move.get("move_id") or 0) for move in _mapping_list(member.get("moves"))
    )


def _predicate_evidence(**values: Any) -> list[str]:
    return [f"{key}={value}" for key, value in values.items()]


def _project_path(project_root: Path, raw: Any) -> Path | None:
    if not raw:
        return None
    path = Path(str(raw).replace("\\", "/"))
    return path if path.is_absolute() else project_root / path


def _validate_case_count(
    spec: Mapping[str, Any],
    cases: list[dict[str, Any]],
    lane: str,
    issues: list[str],
) -> None:
    if int(spec.get("caseCount") or -1) != len(cases):
        issues.append(f"{lane}.caseCount does not match its cases")


def _validate_case_identity(
    case: Mapping[str, Any],
    seen_ids: set[str],
    seen_seeds: set[int],
    issues: list[str],
) -> None:
    case_id = str(case.get("id") or "")
    if not case_id:
        issues.append("frozen case is missing id")
    elif case_id in seen_ids:
        issues.append(f"duplicate frozen case id: {case_id}")
    seen_ids.add(case_id)
    seed = case.get("firstInferenceSeed")
    if not isinstance(seed, int):
        issues.append(f"{case_id}: firstInferenceSeed must be an integer")
    elif seed in seen_seeds:
        issues.append(f"duplicate firstInferenceSeed: {seed}")
    else:
        seen_seeds.add(seed)


def _validate_capsule_state(
    case: Mapping[str, Any], project_root: Path, issues: list[str]
) -> None:
    case_id = str(case.get("id") or "unknown")
    state = project_root / str(case.get("statePath") or "")
    if not state.is_file():
        issues.append(f"{case_id}: state file is missing")
        return
    expected_hash = str(case.get("stateSha256") or "").lower()
    if sha256_file(state) != expected_hash:
        issues.append(f"{case_id}: state SHA-256 mismatch")
    report_path = state.with_suffix(state.suffix + ".report.json")
    if not report_path.is_file():
        issues.append(f"{case_id}: generated-state report is missing")
        return
    report = load_json(report_path)
    if str(report.get("snapshot_hash") or "").lower() != str(
        case.get("snapshotHash") or ""
    ).lower():
        issues.append(f"{case_id}: snapshot hash mismatch")
    snapshot = _mapping(report.get("snapshot"))
    if _party_has_pikachu(snapshot.get("party")):
        issues.append(f"{case_id}: Pikachu is already present at start")
    party = _mapping_list(snapshot.get("party"))
    if not any(int(member.get("hp") or 0) > 0 for member in party):
        issues.append(f"{case_id}: no conscious starting party member")
    inventory = _mapping_list(snapshot.get("inventory"))
    balls = sum(
        int(item.get("quantity") or 0)
        for item in inventory
        if str(item.get("item_name") or "").lower() == "poke ball"
    )
    if balls <= 0:
        issues.append(f"{case_id}: no starting Poke Ball")


def _ordered_observations(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _mapping_list(report.get("progressObservations"))


def _party_has_pikachu(value: Any) -> bool:
    for member in _mapping_list(value):
        if str(member.get("species_name") or "").lower() == "pikachu":
            return True
        species_id = member.get("speciesId", member.get("species_id"))
        if isinstance(species_id, int) and species_id in PIKACHU_SPECIES_IDS:
            return True
    return False


def _is_forest_north_exit(value: Any) -> bool:
    position = _mapping(value)
    map_id = position.get("map_id")
    y = position.get("y")
    return map_id == 0x2F or (
        map_id == 0x33 and isinstance(y, int) and y <= 0
    )


def _has_boulder_badge(value: Any) -> bool:
    if isinstance(value, str):
        return "boulder" in value.lower()
    if not isinstance(value, list):
        return False
    return any("boulder" in str(item).lower() for item in value)


def _report_artifacts_exist(
    report: Mapping[str, Any], project_root: Path | None = None
) -> bool:
    state = report.get("finalState")
    screenshot = report.get("finalScreenshot")
    if not state or not screenshot:
        artifacts = _mapping(report.get("artifacts"))
        state = state or artifacts.get("finalState")
        screenshot = screenshot or artifacts.get("finalScreenshot")
    state_path = _artifact_path(state, project_root)
    screenshot_path = _artifact_path(screenshot, project_root)
    return bool(
        state_path
        and screenshot_path
        and state_path.is_file()
        and screenshot_path.is_file()
    )


def _artifact_path(raw: Any, project_root: Path | None) -> Path | None:
    if not raw:
        return None
    path = Path(str(raw))
    if path.is_absolute() or project_root is None:
        return path
    return project_root / path


def _resolve_report_artifact(
    report: Mapping[str, Any], key: str, project_root: Path
) -> Path | None:
    raw = report.get(key)
    if not raw:
        raw = _mapping(report.get("artifacts")).get(key)
    if not raw:
        return None
    path = Path(str(raw))
    return path if path.is_absolute() else project_root / path


def _provider_failure(reports: Iterable[Mapping[str, Any]]) -> str | None:
    for report in reports:
        finish = _mapping(report.get("finish"))
        category = str(finish.get("failureCategory") or "")
        if category in INFRASTRUCTURE_FAILURES:
            return category
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]
