from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


CHECKPOINT_SCHEMA = "checkpoint_interrogation_v1"


def interrogate_run_report(
    report: dict[str, Any],
    *,
    previous_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a compact checkpoint verdict for a local Director run report."""
    finish = report.get("finish") if isinstance(report.get("finish"), dict) else {}
    history = report.get("history") if isinstance(report.get("history"), list) else []
    final_snapshot = report.get("finalSnapshot") if isinstance(report.get("finalSnapshot"), dict) else {}
    chapter_timeline = report.get("chapterTimeline") if isinstance(report.get("chapterTimeline"), list) else []
    final_state = str(report.get("finalState") or "")
    final_screenshot = str(report.get("finalScreenshot") or "")

    evidence: list[str] = []
    review_items: list[dict[str, Any]] = []
    fallback_taken: list[str] = []
    progress = _progress_analysis(report, previous_report)

    if report.get("schema"):
        evidence.append(f"report_schema={report.get('schema')}")
    if finish.get("status"):
        evidence.append(f"finish_status={finish.get('status')}")
    if finish.get("failureCategory"):
        evidence.append(f"failure_category={finish.get('failureCategory')}")
    evidence.append(f"actions={len(history)}")

    final_chapter = _last_chapter(chapter_timeline)
    if final_chapter:
        evidence.append(f"final_chapter={final_chapter.get('chapterId')}")
        evidence.append(f"chapter_success={final_chapter.get('success')}")

    position = final_snapshot.get("position") if isinstance(final_snapshot.get("position"), dict) else {}
    if position:
        evidence.append(
            "final_position="
            + ",".join(
                str(part)
                for part in (
                    position.get("map_name") or f"map=0x{int(position.get('map_id', 0) or 0):02X}",
                    position.get("x"),
                    position.get("y"),
                )
            )
        )
    evidence.append(f"final_mode={final_snapshot.get('mode')}")
    evidence.append(f"final_battle_type={final_snapshot.get('battle_type_raw')}")

    skill_counts = Counter(str(item.get("skillId")) for item in history if isinstance(item, dict))
    if skill_counts:
        evidence.append("top_skills=" + ",".join(f"{name}:{count}" for name, count in skill_counts.most_common(5)))
    evidence.extend(
        [
            f"state_hash_unique={progress['uniqueStateHashes']}",
            f"state_hash_max_repeat={progress['maxStateHashRepeat']}",
            f"chapter_movements={progress['chapterMovements']}",
            f"position_changes={progress['positionChanges']}",
            f"resource_changes={progress['resourceChanges']}",
            f"literal_button_frequency={progress['literalButtonFrequency']:.3f}",
        ]
    )
    if progress["failureClusters"]:
        evidence.append(
            "failure_clusters="
            + ",".join(
                f"{name}:{count}"
                for name, count in list(progress["failureClusters"].items())[:5]
            )
        )

    if finish.get("success") is True:
        return _checkpoint(
            verdict="healthy_needs_review",
            confidence="high",
            continue_recommended=False,
            summary=str(finish.get("summary") or "Run reached a chapter success condition."),
            evidence=evidence + ["run_success=true"],
            review_items=[
                _review_item(
                    kind="chapter_success",
                    summary="Review successful checkpoint before using it as a promoted start.",
                    state_path=final_state,
                    screenshot_path=final_screenshot,
                )
            ],
            fallback_taken=[],
        )

    failure_category = str(finish.get("failureCategory") or "")
    if failure_category == "execution_error":
        return _checkpoint(
            verdict="unsafe_state",
            confidence="high",
            continue_recommended=False,
            summary=(
                "Semantic tool execution ended with unknown action state; reconcile from the "
                "pre-provider checkpoint before continuing."
            ),
            evidence=evidence + ["action_state_known=false"],
            review_items=[
                _review_item(
                    kind="execution_state_reconciliation",
                    summary=(
                        "Inspect the final state or reload the pre-provider checkpoint before "
                        "another Director action."
                    ),
                    state_path=final_state,
                    screenshot_path=final_screenshot,
                )
            ],
            fallback_taken=["reconcile_or_reload_pre_provider_checkpoint"],
        )
    if failure_category in {
        "local_llm_request_failed",
        "authentication",
        "connection",
        "invalid_response",
        "invalid_tool_arguments",
        "missing_tool_call",
        "multiple_tool_calls",
        "provider_error",
        "provider_unavailable",
        "rate_limit",
        "replay_exhausted",
        "text_response_without_tool",
        "timeout",
        "no_tool_call",
        "no_choices",
        "unexpected_tool",
    }:
        return _checkpoint(
            verdict="model_error",
            confidence="high",
            continue_recommended=False,
            summary=str(finish.get("summary") or "Local model/tool request failed."),
            evidence=evidence,
            review_items=[
                _review_item(
                    kind="model_error",
                    summary="Retry after a local model health check; inspect payload if repeated.",
                    state_path=final_state,
                    screenshot_path=final_screenshot,
                )
            ],
            fallback_taken=["retry_once_after_model_health_check_or_pivot"],
        )

    unsafe_reason = _unsafe_reason(final_snapshot)
    if unsafe_reason:
        return _checkpoint(
            verdict="unsafe_state",
            confidence="high",
            continue_recommended=False,
            summary=f"Final state is not safe to continue automatically: {unsafe_reason}.",
            evidence=evidence + [f"unsafe_reason={unsafe_reason}"],
            review_items=[
                _review_item(
                    kind="unsafe_state",
                    summary="Rollback to previous healthy checkpoint or patch recovery before continuing.",
                    state_path=final_state,
                    screenshot_path=final_screenshot,
                )
            ],
            fallback_taken=["rollback_or_patch_recovery"],
        )

    interpretation_reason = _state_interpretation_reason(failure_category, progress)
    if interpretation_reason:
        return _checkpoint(
            verdict="state_interpretation_gap",
            confidence="high",
            continue_recommended=False,
            summary=f"Run cannot interpret the current game state reliably: {interpretation_reason}.",
            evidence=evidence + [f"interpretation_reason={interpretation_reason}"],
            review_items=[
                _review_item(
                    kind="state_interpretation_gap",
                    summary="Preserve this evidence bundle and patch state interpretation before retrying.",
                    state_path=final_state,
                    screenshot_path=final_screenshot,
                )
            ],
            fallback_taken=["preserve_evidence_and_patch_interpretation"],
        )

    loop_reason = _loop_reason(history, progress=progress)
    if loop_reason:
        return _checkpoint(
            verdict="stalled_loop",
            confidence="medium",
            continue_recommended=False,
            summary=f"Run appears stalled or under-specified: {loop_reason}.",
            evidence=evidence + [f"loop_reason={loop_reason}"],
            review_items=[
                _review_item(
                    kind="loop_or_skill_gap",
                    summary="Patch skill gating, schema clarity, or semantic skill coverage; rerun this segment.",
                    state_path=final_state,
                    screenshot_path=final_screenshot,
                )
            ],
            fallback_taken=["patch_and_rerun_segment"],
        )

    literal_count = skill_counts.get("literal_button_press", 0)
    if literal_count >= 3 and progress["literalButtonFrequency"] >= 0.25:
        review_items.append(
            _review_item(
                kind="literal_button_overuse",
                summary="Literal button presses were used repeatedly; keep going only provisionally and convert recurring use into semantic skill coverage.",
                state_path=final_state,
                screenshot_path=final_screenshot,
            )
        )
        fallback_taken.append("continue_provisionally_and_queue_skill_gap_review")

    stop_reason = str(finish.get("stopReason") or "")
    if stop_reason in {"operator_stop_after_action", "operator_emergency_stop"}:
        return _checkpoint(
            verdict="healthy_needs_review",
            confidence="high",
            continue_recommended=False,
            summary="Run stopped at a safe operator-requested checkpoint.",
            evidence=evidence + [f"operator_stop={stop_reason}"],
            review_items=review_items,
            fallback_taken=fallback_taken,
        )

    if failure_category == "action_budget_exhausted" or finish.get("status") == "checkpoint":
        verdict = "provisional_continue" if review_items else "healthy_continue"
        confidence = "medium" if review_items else "high"
        return _checkpoint(
            verdict=verdict,
            confidence=confidence,
            continue_recommended=True,
            summary="Action budget reached an inspection checkpoint; no terminal failure was detected.",
            evidence=evidence + ["action_budget_is_checkpoint=true"],
            review_items=review_items,
            fallback_taken=fallback_taken,
        )

    if failure_category in {"no_supported_enabled_skills", "unavailable_skill"}:
        return _checkpoint(
            verdict="skill_gap",
            confidence="high",
            continue_recommended=False,
            summary=str(finish.get("summary") or "No supported skill could continue the run."),
            evidence=evidence,
            review_items=[
                _review_item(
                    kind="skill_gap",
                    summary="Add or repair semantic skill coverage before continuing this segment.",
                    state_path=final_state,
                    screenshot_path=final_screenshot,
                )
            ],
            fallback_taken=["patch_skill_surface_or_pivot"],
        )

    return _checkpoint(
        verdict="healthy_needs_review",
        confidence="low",
        continue_recommended=True,
        summary="Run ended in an unclassified non-terminal state; safe enough to continue provisionally.",
        evidence=evidence,
        review_items=[
            _review_item(
                kind="unclassified_checkpoint",
                summary="Review classifier coverage when convenient; continue only if later checkpoints remain healthy.",
                state_path=final_state,
                screenshot_path=final_screenshot,
            )
        ],
        fallback_taken=["continue_provisionally"],
    )


def _checkpoint(
    *,
    verdict: str,
    confidence: str,
    continue_recommended: bool,
    summary: str,
    evidence: list[str],
    review_items: list[dict[str, Any]],
    fallback_taken: list[str],
) -> dict[str, Any]:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "verdict": verdict,
        "confidence": confidence,
        "continueRecommended": continue_recommended,
        "summary": summary,
        "evidence": evidence,
        "reviewItems": [item for item in review_items if item],
        "fallbackTaken": fallback_taken,
    }


def _review_item(
    *,
    kind: str,
    summary: str,
    state_path: str,
    screenshot_path: str,
) -> dict[str, Any]:
    item = {"kind": kind, "summary": summary}
    if state_path:
        item["statePath"] = state_path
    if screenshot_path:
        item["screenshotPath"] = screenshot_path
    return item


def _last_chapter(chapter_timeline: list[Any]) -> dict[str, Any] | None:
    for item in reversed(chapter_timeline):
        if isinstance(item, dict):
            return item
    return None


def _unsafe_reason(snapshot: dict[str, Any]) -> str | None:
    if not snapshot:
        return "missing_final_snapshot"
    position = snapshot.get("position") if isinstance(snapshot.get("position"), dict) else {}
    if not position:
        return "missing_position"
    party = snapshot.get("party") if isinstance(snapshot.get("party"), list) else []
    real_party = [
        member
        for member in party
        if isinstance(member, dict) and int(member.get("species_id", 1) or 0) != 0
    ]
    if real_party:
        conscious = [
            member
            for member in real_party
            if int(member.get("hp", 0) or 0) > 0 and int(member.get("max_hp", 0) or 0) > 0
        ]
        if not conscious:
            return "no_conscious_party_members"
    mode = str(snapshot.get("mode", "unknown"))
    if mode in {"unknown", "title_or_boot"}:
        return f"unsupported_mode={mode}"
    return None


def _progress_analysis(
    report: dict[str, Any],
    previous_report: dict[str, Any] | None,
) -> dict[str, Any]:
    observations = (
        report.get("progressObservations")
        if isinstance(report.get("progressObservations"), list)
        else []
    )
    if not observations:
        context = report.get("context") if isinstance(report.get("context"), dict) else {}
        observations = (
            context.get("progressObservations")
            if isinstance(context.get("progressObservations"), list)
            else []
        )
    normalized = [item for item in observations if isinstance(item, dict)]
    state_hashes = [str(item.get("stateHash")) for item in normalized if item.get("stateHash")]
    if not state_hashes:
        requests = report.get("requests") if isinstance(report.get("requests"), list) else []
        state_hashes = [
            str(checkpoint.get("snapshotHash"))
            for item in requests
            if isinstance(item, dict)
            for checkpoint in [item.get("checkpoint")]
            if isinstance(checkpoint, dict) and checkpoint.get("snapshotHash")
        ]
    state_counts = Counter(state_hashes)
    chapters = [str(item.get("chapterId")) for item in normalized if item.get("chapterId")]
    positions = [_position_signature(item.get("position")) for item in normalized]
    resources = [_resource_signature(item) for item in normalized]
    history = report.get("history") if isinstance(report.get("history"), list) else []
    cluster_counts: Counter[str] = Counter()
    literal_count = 0
    for item in history:
        if not isinstance(item, dict):
            continue
        if item.get("skillId") == "literal_button_press":
            literal_count += 1
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        status = str(result.get("status") or "unknown")
        if status != "succeeded":
            cluster_counts[f"status:{status}"] += 1
        warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
        for warning in warnings:
            cluster_counts[f"warning:{str(warning)[:80]}"] += 1

    chapter_movements = _change_count(chapters)
    position_changes = _change_count(positions)
    resource_changes = _change_count(resources)
    if previous_report:
        previous_snapshot = (
            previous_report.get("finalSnapshot")
            if isinstance(previous_report.get("finalSnapshot"), dict)
            else {}
        )
        current_snapshot = (
            report.get("finalSnapshot")
            if isinstance(report.get("finalSnapshot"), dict)
            else {}
        )
        previous_chapter = _last_chapter(
            previous_report.get("chapterTimeline")
            if isinstance(previous_report.get("chapterTimeline"), list)
            else []
        )
        current_chapter = _last_chapter(
            report.get("chapterTimeline")
            if isinstance(report.get("chapterTimeline"), list)
            else []
        )
        if previous_chapter and current_chapter and (
            previous_chapter.get("chapterId") != current_chapter.get("chapterId")
            or previous_chapter.get("success") != current_chapter.get("success")
        ):
            chapter_movements += 1
        if _position_signature(previous_snapshot.get("position")) != _position_signature(
            current_snapshot.get("position")
        ):
            position_changes += 1
        if _resource_signature(previous_snapshot) != _resource_signature(current_snapshot):
            resource_changes += 1
    clustered = {
        name: count
        for name, count in cluster_counts.most_common()
        if count >= 2
    }
    return {
        "observationCount": len(normalized),
        "uniqueStateHashes": len(state_counts),
        "maxStateHashRepeat": max(state_counts.values(), default=0),
        "chapterMovements": chapter_movements,
        "positionChanges": position_changes,
        "resourceChanges": resource_changes,
        "literalButtonFrequency": literal_count / max(len(history), 1),
        "failureClusters": clustered,
    }


def _position_signature(value: Any) -> tuple[Any, Any, Any]:
    position = value if isinstance(value, dict) else {}
    return (
        position.get("map_id") or position.get("map_name"),
        position.get("x"),
        position.get("y"),
    )


def _resource_signature(value: Any) -> tuple[Any, ...]:
    snapshot = value if isinstance(value, dict) else {}
    party = snapshot.get("party") if isinstance(snapshot.get("party"), list) else []
    inventory = (
        snapshot.get("inventory") if isinstance(snapshot.get("inventory"), list) else []
    )
    party_signature = tuple(
        (
            member.get("speciesId") or member.get("species_id"),
            member.get("level"),
            member.get("hp"),
            member.get("status"),
        )
        for member in party
        if isinstance(member, dict)
    )
    inventory_signature = tuple(
        sorted(
            (
                str(item.get("itemId") or item.get("item_id") or item.get("item_name") or ""),
                item.get("quantity"),
            )
            for item in inventory
            if isinstance(item, dict)
        )
    )
    badges = snapshot.get("badges") or snapshot.get("badge_names") or []
    return (
        snapshot.get("money"),
        tuple(str(badge) for badge in badges) if isinstance(badges, list) else str(badges),
        party_signature,
        inventory_signature,
    )


def _change_count(values: list[Any]) -> int:
    return sum(1 for before, after in zip(values, values[1:]) if before != after)


def _state_interpretation_reason(
    failure_category: str,
    progress: dict[str, Any],
) -> str | None:
    if failure_category in {
        "state_interpretation_gap",
        "unknown_ui",
        "unclassified_visual_state",
        "snapshot_interpretation_failed",
    }:
        return failure_category
    tokens = ("unclassified", "interpretation", "unknown_ui", "unknown_state")
    for cluster, count in progress["failureClusters"].items():
        if count >= 2 and any(token in cluster.lower() for token in tokens):
            return f"repeated_{cluster}"
    return None


def _loop_reason(
    history: list[dict[str, Any]],
    *,
    progress: dict[str, Any] | None = None,
) -> str | None:
    if len(history) < 5:
        return None
    progress = progress or {}
    if (
        int(progress.get("maxStateHashRepeat") or 0) >= 5
        and int(progress.get("chapterMovements") or 0) == 0
        and int(progress.get("positionChanges") or 0) == 0
        and int(progress.get("resourceChanges") or 0) == 0
    ):
        return "repeated_state_hash_without_progress"
    last_five = [item for item in history[-5:] if isinstance(item, dict)]
    skill_ids = [str(item.get("skillId")) for item in last_five]

    blocked_or_failed = 0
    non_success = 0
    for item in last_five:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if result.get("status") in {"blocked", "failed"}:
            blocked_or_failed += 1
        if result.get("status") != "succeeded":
            non_success += 1
    if len(set(skill_ids)) == 1 and non_success >= 3:
        return f"last_five_same_skill_without_success={skill_ids[0]}"
    if blocked_or_failed >= 3:
        return f"blocked_or_failed_results_in_last_five={blocked_or_failed}"

    last_ten = [item for item in history[-10:] if isinstance(item, dict)]
    if sum(1 for item in last_ten if item.get("skillId") == "finish_run") >= 3:
        return "repeated_premature_finish"
    return None


def load_report(path: str | Path) -> dict[str, Any]:
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))
