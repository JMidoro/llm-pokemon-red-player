from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


CHECKPOINT_SCHEMA = "checkpoint_interrogation_v1"


def interrogate_run_report(report: dict[str, Any]) -> dict[str, Any]:
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

    loop_reason = _loop_reason(history)
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
    if literal_count >= 4:
        review_items.append(
            _review_item(
                kind="literal_button_overuse",
                summary="Literal button presses were used repeatedly; keep going only provisionally and convert recurring use into semantic skill coverage.",
                state_path=final_state,
                screenshot_path=final_screenshot,
            )
        )
        fallback_taken.append("continue_provisionally_and_queue_skill_gap_review")

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


def _loop_reason(history: list[dict[str, Any]]) -> str | None:
    if len(history) < 5:
        return None
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
