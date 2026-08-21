from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts import chapter_segment_support as support  # noqa: E402

from pokemon_player.chapter_direction import current_chapter_goal  # noqa: E402
from pokemon_player.director_contracts import (  # noqa: E402
    DirectorRequest,
    DirectorTickResult,
    JsonObject,
    ToolCall,
)
from pokemon_player.director_player import promoted_signals, skill_availability  # noqa: E402
from pokemon_player.director_provider_factory import canonical_provider_id, make_provider  # noqa: E402
from pokemon_player.director_reporting import build_director_report  # noqa: E402
from pokemon_player.director_runtime import DirectorRuntime  # noqa: E402
from pokemon_player.durable_io import atomic_write_json, require_safe_component  # noqa: E402
from pokemon_player.operations import OperationsPaths, OperationsRunControl, OperationsStore  # noqa: E402
from pokemon_player.nuzlocke_ledger import NuzlockeLedger  # noqa: E402
from pokemon_player.nuzlocke_policy import (  # noqa: E402
    director_rules_context,
    execute_guarded_skill,
    filter_skill_availability,
    public_lineage_context,
)
from pokemon_player.nuzlocke_reconciliation import reconcile_snapshot  # noqa: E402
from pokemon_player.nuzlocke_rules import load_ruleset  # noqa: E402
from pokemon_player.nuzlocke_runtime import apply_configured_battle_style  # noqa: E402
from pokemon_player.pyboy_lab import load_state, open_emulator, save_state, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.run_interrogation import interrogate_run_report  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict  # noqa: E402


DEFAULT_GOAL = (
    "Progress through Pokemon Red's early-game chapters from the current seed, including "
    "the prologue if starting from a clean boot. At every action, follow the current "
    "chapterDirection objective and choose one enabled semantic skill that serves it."
)
DEFAULT_LOCAL_MODEL = "google/gemma-4-e4b"
DEFAULT_OPERATIONS_DIR = ROOT / "research" / "artifacts" / "operations"
DEFAULT_RULESET = ROOT / "research" / "rulesets" / "stream-nuzlocke-v1.json"


def build_parser(*, forced_provider: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a provider-neutral unattended Pokemon Red chapter segment."
    )
    parser.add_argument("--rom", default=str(support.DEFAULT_ROM))
    parser.add_argument("--state-in", default=str(support.DEFAULT_STATE))
    parser.add_argument("--fresh-start", action="store_true")
    parser.add_argument("--fresh-start-boot-frames", type=int, default=1800)
    if forced_provider is None:
        parser.add_argument(
            "--provider",
            choices=("lmstudio-chat", "openai-responses", "replay"),
            default="lmstudio-chat",
        )
    else:
        parser.set_defaults(provider=forced_provider)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--replay-path", default=None)
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument(
        "--run-root",
        default=None,
        help="Optional artifact root; defaults to research/artifacts/chapter-segment-runs.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional deterministic run id used by the durable segment supervisor.",
    )
    parser.add_argument("--max-actions", type=int, default=100)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--request-timeout-seconds", type=int, default=180)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--no-image", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--video-output-dir", default=str(support.DEFAULT_VIDEO_OUTPUT_DIR))
    parser.add_argument("--video-fps", type=int, default=2)
    parser.add_argument(
        "--operations-dir",
        default=str(DEFAULT_OPERATIONS_DIR),
        help="Durable local pause/stop control and active-run heartbeat directory.",
    )
    parser.add_argument(
        "--no-operations-control",
        action="store_true",
        help="Disable Operations controls for isolated diagnostics.",
    )
    parser.add_argument(
        "--ruleset",
        default=str(DEFAULT_RULESET),
        help="Versioned run rules. Use standard-run-v1.json to disable Nuzlocke enforcement.",
    )
    parser.add_argument(
        "--nuzlocke-ledger",
        default=None,
        help="Durable lineage ledger path; defaults inside this isolated run directory.",
    )
    parser.add_argument(
        "--lineage-id",
        default=None,
        help="Durable lineage id supplied by the segment supervisor.",
    )
    return parser


def operator_finish(signal: str) -> JsonObject:
    labels = {
        "stop_after_action": "Operator requested a stop after the completed action.",
        "emergency_stop": (
            "Operator requested an emergency stop at the next safe action boundary."
        ),
    }
    if signal not in labels:
        raise ValueError(f"Unsupported operator stop signal: {signal}")
    return {
        "status": "checkpoint",
        "success": False,
        "summary": labels[signal],
        "failureCategory": None,
        "stopReason": f"operator_{signal}",
    }


def progress_observation(
    *,
    action: int,
    state_hash: str,
    chapter: JsonObject,
    snapshot_dict: JsonObject,
) -> JsonObject:
    party = snapshot_dict.get("party") if isinstance(snapshot_dict.get("party"), list) else []
    inventory = (
        snapshot_dict.get("inventory")
        if isinstance(snapshot_dict.get("inventory"), list)
        else []
    )
    return {
        "action": action,
        "stateHash": state_hash,
        "chapterId": chapter.get("chapterId"),
        "chapterSuccess": bool(chapter.get("success")),
        "mode": snapshot_dict.get("mode"),
        "position": snapshot_dict.get("position"),
        "money": snapshot_dict.get("money"),
        "badges": snapshot_dict.get("badge_names") or [],
        "party": [
            {
                "speciesId": member.get("species_id"),
                "level": member.get("level"),
                "hp": member.get("hp"),
                "status": member.get("status"),
            }
            for member in party
            if isinstance(member, dict)
        ],
        "inventory": [
            {
                "itemId": item.get("item_id"),
                "quantity": item.get("quantity"),
            }
            for item in inventory
            if isinstance(item, dict)
        ],
    }


def main(
    argv: list[str] | None = None,
    *,
    forced_provider: str | None = None,
) -> int:
    args = build_parser(forced_provider=forced_provider).parse_args(argv)
    provider_id = canonical_provider_id(args.provider)
    model = args.model or default_model(provider_id)
    provider = make_provider(
        provider_id,
        env_path=ROOT / ".env",
        base_url=args.base_url,
        api_token=args.api_token,
        timeout_seconds=args.request_timeout_seconds,
        replay_path=Path(args.replay_path) if args.replay_path else None,
    )
    runtime = DirectorRuntime(provider, max_retries=args.max_retries)
    rom = fingerprint_rom(args.rom)
    state_in = Path(args.state_in)
    run_root = (
        Path(args.run_root)
        if args.run_root
        else ROOT / "research" / "artifacts" / "chapter-segment-runs"
    )
    run_id = require_safe_component(args.run_id, label="run id") if args.run_id else support.timestamp()
    run_dir = run_root / run_id
    existing = [item for item in run_dir.iterdir() if item.name != "manifest.json"] if run_dir.exists() else []
    if existing:
        raise FileExistsError(f"Run directory already contains segment artifacts: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    ruleset_path = Path(args.ruleset)
    if not ruleset_path.is_absolute():
        ruleset_path = ROOT / ruleset_path
    ruleset = load_ruleset(ruleset_path)
    lineage_id = require_safe_component(
        args.lineage_id or run_id,
        label="lineage id",
    )
    ledger_path = Path(args.nuzlocke_ledger) if args.nuzlocke_ledger else run_dir / "nuzlocke" / "ledger.json"
    if not ledger_path.is_absolute():
        ledger_path = ROOT / ledger_path
    nuzlocke_ledger = NuzlockeLedger(ledger_path, ruleset, lineage_id=lineage_id)
    skill_run_root = run_dir / "skill-runs"
    video_frame_dir = run_dir / "video-frames"
    video_frame_index = 1
    video_artifact: JsonObject = {"enabled": False}
    pathing_frame_warnings: list[str] = []
    history: list[JsonObject] = []
    director_requests: list[DirectorRequest] = []
    ticks: list[DirectorTickResult] = []
    chapter_timeline: list[JsonObject] = []
    progress_observations: list[JsonObject] = []
    operations_control: OperationsRunControl | None = None
    if not args.no_operations_control:
        operations_dir = Path(args.operations_dir)
        if not operations_dir.is_absolute():
            operations_dir = ROOT / operations_dir
        operations_store = OperationsStore(
            OperationsPaths(
                state_dir=operations_dir.resolve(),
                report_root=run_root.resolve(),
                dropbox_root=(
                    Path(args.video_output_dir).resolve() if args.video_output_dir else None
                ),
            )
        )
        operations_control = OperationsRunControl(operations_store, run_id)
        operations_control.begin(
            status="starting",
            actionCount=0,
            model=model,
            provider=provider_id,
            goal=args.goal,
            nuzlocke=public_lineage_context(ruleset, nuzlocke_ledger),
        )
    clean_ram_path = run_dir / "fresh-start-clean.ram"

    if args.fresh_start:
        clean_ram_path.write_bytes(bytes([0]) * 32768)
        pyboy = open_emulator(
            rom.path,
            window="SDL2" if args.render else "null",
            ram_path=clean_ram_path,
        )
        state_in = run_dir / "fresh-start-title.state"
    else:
        pyboy = open_emulator(rom.path, window="SDL2" if args.render else "null")

    finish: JsonObject | None = None
    final_screenshot: Path | None = None
    final_state: Path | None = None
    final_snapshot: JsonObject = {}
    try:
        if args.fresh_start:
            pyboy.tick(args.fresh_start_boot_frames, args.render)
            save_state(pyboy, state_in)
        else:
            load_state(pyboy, state_in)
            pyboy.tick(60, args.render)
        battle_style_configuration = apply_configured_battle_style(pyboy.memory, ruleset)
        if battle_style_configuration["changed"]:
            nuzlocke_ledger.append(
                "runtime_configuration_applied",
                {
                    "kind": "battle_style",
                    **battle_style_configuration,
                },
                evidence=("ruleset_battle_style",),
                source="non_strategic_runtime_configuration",
            )

        for action_index in range(1, args.max_actions + 1):
            if operations_control:
                signal = operations_control.boundary()
                if signal != "continue":
                    finish = operator_finish(signal)
                    break
            screenshot_path, current_state_path, snapshot_dict = support.save_current_artifacts(
                pyboy,
                run_dir,
                f"action_{action_index:03d}_before",
            )
            current_state_hash = snapshot_hash(snapshot(pyboy))
            reconcile_snapshot(
                nuzlocke_ledger,
                ruleset,
                snapshot_dict,
                checkpoint_id=f"{run_id}:action:{action_index}:before",
                snapshot_hash=current_state_hash,
                last_action=history[-1] if history else None,
            )
            if not args.no_video:
                video_frame_index = support.append_video_frame(
                    screenshot_path,
                    video_frame_dir,
                    video_frame_index,
                )
            if nuzlocke_ledger.state["gameOver"]:
                finish = {
                    "status": "game_over",
                    "success": False,
                    "summary": "The active Nuzlocke lineage ended in a blackout.",
                    "failureCategory": "nuzlocke_blackout",
                    "stopReason": "nuzlocke_game_over",
                }
                break
            signals = promoted_signals(snapshot_dict, screenshot_path)
            chapter_direction = current_chapter_goal(snapshot_dict)
            available = support.enabled_supported_skills(
                skill_availability(snapshot_dict, screenshot_path)
            )
            available, skill_policy_notes = support.apply_chapter_skill_policy(
                available,
                snapshot_dict,
                chapter_direction,
                history,
            )
            available, nuzlocke_availability_decisions = filter_skill_availability(
                ruleset,
                nuzlocke_ledger.state,
                snapshot_dict,
                available,
            )
            nuzlocke_context = director_rules_context(
                ruleset,
                nuzlocke_ledger,
                snapshot_dict,
                availability_decisions=nuzlocke_availability_decisions,
            )
            chapter_dict = chapter_direction.to_dict()
            chapter_timeline.append({"action": action_index, **chapter_dict})
            progress_observations.append(
                progress_observation(
                    action=action_index,
                    state_hash=current_state_hash,
                    chapter=chapter_dict,
                    snapshot_dict=snapshot_dict,
                )
            )
            if operations_control:
                operations_control.update(
                    status="running",
                    actionCount=len(history),
                    model=model,
                    provider=provider_id,
                    goal=args.goal,
                    chapter={
                        "id": chapter_direction.chapter_id,
                        "title": chapter_direction.title,
                        "objective": chapter_direction.objective,
                        "success": chapter_direction.success,
                    },
                    snapshot=snapshot_dict,
                    screenshotPath=str(screenshot_path),
                    lastDecision=(history[-1] if history else None),
                    lastSkillResult=(history[-1].get("result") if history else None),
                    nuzlocke=public_lineage_context(
                        ruleset,
                        nuzlocke_ledger,
                        snapshot_dict,
                    ),
                )
            if chapter_direction.success:
                finish = {
                    "status": "completed",
                    "success": True,
                    "summary": f"Reached chapter success: {chapter_direction.title}.",
                    "failureCategory": None,
                }
                break
            if not available:
                finish = {
                    "status": "failed",
                    "success": False,
                    "summary": "No supported enabled semantic skills are available.",
                    "failureCategory": "no_supported_enabled_skills",
                }
                break

            checkpoint = {
                "kind": "saved_emulator_state",
                "statePath": str(current_state_path),
                "screenshotPath": str(screenshot_path),
                "snapshotHash": current_state_hash,
                "actionStarted": False,
            }
            request = DirectorRequest(
                goal=args.goal,
                model=model,
                provider=provider_id,
                enabled_skills=tuple(available),
                context={
                    "chapterDirection": chapter_direction.to_dict(),
                    "actionIndex": action_index,
                    "maxActions": args.max_actions,
                    "snapshot": support.compact_snapshot(snapshot_dict),
                    "signals": signals,
                    "skillPolicy": skill_policy_notes,
                    "nuzlocke": nuzlocke_context,
                },
                action_history=tuple(history),
                screenshot_path=None if args.no_image else screenshot_path,
                tick=action_index,
                max_history=8,
                reasoning_effort=args.reasoning_effort,
                temperature=args.temperature,
                max_output_tokens=args.max_tokens,
                runtime_instructions=(
                    "chapterDirection is authoritative for the current local goal.",
                    "Choose actions that directly serve chapterDirection.objective.",
                    "When a hint names a navigation target, pass that exact target in args.target.",
                    "The harness, not the model, decides whether chapter success is satisfied.",
                ),
                metadata={"checkpoint": checkpoint},
            )
            director_requests.append(request)

            selected_artifact: dict[str, Any] = {}

            def execute(call: ToolCall) -> JsonObject:
                nonlocal video_frame_index
                arguments = call.arguments
                skill_id = str(arguments.get("skillId") or "")
                skill_args = (
                    arguments.get("args") if isinstance(arguments.get("args"), dict) else {}
                )
                skill_args = support.infer_missing_skill_args(
                    skill_id,
                    skill_args,
                    chapter_direction,
                    snapshot_dict,
                    history,
                )
                artifact = execute_guarded_skill(
                    ruleset,
                    nuzlocke_ledger,
                    snapshot_dict,
                    skill_id=skill_id,
                    args=skill_args,
                    action_index=action_index,
                    executor=lambda: support.execute_local_skill(
                        pyboy,
                        skill_id=skill_id,
                        args=skill_args,
                        state_in=current_state_path,
                        rom=rom,
                        run_root=skill_run_root,
                        render=args.render,
                    ),
                )
                if isinstance(artifact, dict) and artifact.get("policyDecision"):
                    result = artifact
                    selected_artifact.update(
                        {"skillId": skill_id, "args": skill_args, "result": result}
                    )
                    return result
                result = support.artifact_result_dict(artifact)
                selected_artifact.update({"skillId": skill_id, "args": skill_args, "result": result})
                after_snapshot = snapshot_to_dict(snapshot(pyboy))
                reconcile_snapshot(
                    nuzlocke_ledger,
                    ruleset,
                    after_snapshot,
                    checkpoint_id=f"{run_id}:action:{action_index}:after",
                    snapshot_hash=snapshot_hash(snapshot(pyboy)),
                    last_action={"skillId": skill_id, "args": skill_args, "result": result},
                )
                if not args.no_video:
                    video_frame_index = support.append_skill_trace_video_frames(
                        artifact,
                        rom=rom,
                        skill_id=skill_id,
                        frame_dir=video_frame_dir,
                        frame_index=video_frame_index,
                        warnings=pathing_frame_warnings,
                    )
                return {
                    "actionStarted": True,
                    "skillId": skill_id,
                    "args": skill_args,
                    "plaintextReasoning": arguments.get("plaintextReasoning"),
                    **result,
                }

            tick_result = runtime.run_tick(request, executor=execute)
            ticks.append(tick_result)
            decision = tick_result.decision
            if operations_control:
                operations_control.update(
                    status="executing_action" if tick_result.execution else "requesting_model",
                    actionCount=len(history),
                    lastDecision={
                        "action": action_index,
                        "skillId": (
                            decision.tool_call.arguments.get("skillId")
                            if decision.tool_call
                            else None
                        ),
                        "args": decision.tool_call.arguments if decision.tool_call else {},
                        "plaintextReasoning": (
                            decision.tool_call.arguments.get("plaintextReasoning")
                            if decision.tool_call
                            else decision.assistant_message
                        ),
                    },
                )
            if decision.error:
                finish = {
                    "status": "stopped",
                    "success": False,
                    "summary": (
                        f"Provider request failed safely at action {action_index}: "
                        f"{decision.error.message}"
                    ),
                    "failureCategory": decision.error.category,
                    "actionStarted": False,
                    "checkpoint": checkpoint,
                }
                break
            execution = tick_result.execution or {}
            if execution.get("status") == "error":
                error = execution.get("error")
                error = error if isinstance(error, dict) else {}
                finish = {
                    "status": "failed",
                    "success": False,
                    "summary": str(
                        execution.get("summary")
                        or "Semantic tool execution failed after invocation."
                    ),
                    "failureCategory": str(error.get("category") or "execution_error"),
                    "actionStarted": None,
                    "actionStateKnown": False,
                    "requiresCheckpointReconciliation": True,
                    "checkpoint": checkpoint,
                }
                break
            if decision.tool_call and decision.tool_call.name == "finish_run":
                arguments = decision.tool_call.arguments
                history.append(
                    {
                        "action": action_index,
                        "skillId": "finish_run",
                        "args": arguments,
                        "plaintextReasoning": arguments.get("plaintextReasoning"),
                        "result": {
                            "skill_id": "finish_run",
                            "status": "blocked",
                            "summary": (
                                "finish_run was rejected because the authoritative chapter goal "
                                "is not satisfied."
                            ),
                            "evidence": [
                                f"chapter_id={chapter_direction.chapter_id}",
                                f"chapter_success={chapter_direction.success}",
                            ],
                            "warnings": ["premature_finish_rejected"],
                        },
                    }
                )
                if operations_control:
                    operations_control.update(
                        status="running",
                        actionCount=len(history),
                        lastDecision=history[-1],
                        lastSkillResult=history[-1]["result"],
                        nuzlocke=public_lineage_context(
                            ruleset,
                            nuzlocke_ledger,
                            snapshot_to_dict(snapshot(pyboy)),
                        ),
                    )
                    signal = operations_control.boundary(after_action=True)
                    if signal != "continue":
                        finish = operator_finish(signal)
                        break
                continue
            if selected_artifact:
                history.append(
                    {
                        "action": action_index,
                        "skillId": selected_artifact["skillId"],
                        "args": selected_artifact["args"],
                        "plaintextReasoning": (
                            decision.tool_call.arguments.get("plaintextReasoning")
                            if decision.tool_call
                            else None
                        ),
                        "result": selected_artifact["result"],
                    }
                )
                if operations_control:
                    operations_control.update(
                        status="running",
                        actionCount=len(history),
                        lastDecision=history[-1],
                        lastSkillResult=history[-1]["result"],
                    )
                    signal = operations_control.boundary(after_action=True)
                    if signal != "continue":
                        finish = operator_finish(signal)
                        break
        else:
            finish = {
                "status": "checkpoint",
                "success": False,
                "summary": f"Action budget checkpoint reached after {args.max_actions} actions.",
                "failureCategory": None,
                "stopReason": "action_budget",
            }

        final_screenshot, final_state, final_snapshot = support.save_current_artifacts(
            pyboy,
            run_dir,
            "final",
        )
        reconcile_snapshot(
            nuzlocke_ledger,
            ruleset,
            final_snapshot,
            checkpoint_id=f"{run_id}:final",
            snapshot_hash=snapshot_hash(snapshot(pyboy)),
            last_action=history[-1] if history else None,
        )
        if not args.no_video:
            video_frame_index = support.append_video_frame(
                final_screenshot,
                video_frame_dir,
                video_frame_index,
            )
    finally:
        pyboy.stop(False)

    if not args.no_video:
        video_artifact = support.render_video_artifact(
            run_dir=run_dir,
            frame_dir=video_frame_dir,
            output_dir=Path(args.video_output_dir),
            run_id=run_id,
            fps=max(args.video_fps, 1),
        )
        video_artifact.setdefault("warnings", []).extend(pathing_frame_warnings)

    assert finish is not None and final_screenshot is not None and final_state is not None
    report_path = run_dir / "report.json"
    report = build_director_report(
        run_id=run_id,
        mode="chapter_segment",
        provider=provider,
        model=model,
        goal=args.goal,
        requests=director_requests,
        ticks=ticks,
        finish=finish,
        history=history,
        artifacts={
            "reportPath": str(report_path),
            "stateIn": str(state_in),
            "finalScreenshot": str(final_screenshot),
            "finalState": str(final_state),
            "video": video_artifact,
            "freshStartCleanRam": str(clean_ram_path) if args.fresh_start else None,
        },
        context={
            "freshStart": bool(args.fresh_start),
            "maxActions": args.max_actions,
            "chapterTimeline": chapter_timeline,
            "progressObservations": progress_observations,
            "nuzlocke": public_lineage_context(ruleset, nuzlocke_ledger, final_snapshot),
        },
    )
    report.update(
        {
            "stateIn": str(state_in),
            "freshStart": bool(args.fresh_start),
            "maxActions": args.max_actions,
            "chapterTimeline": chapter_timeline,
            "progressObservations": progress_observations,
            "video": video_artifact,
            "pathingFrameWarnings": pathing_frame_warnings,
            "finalScreenshot": str(final_screenshot),
            "finalState": str(final_state),
            "finalSnapshot": final_snapshot,
            "nuzlocke": public_lineage_context(ruleset, nuzlocke_ledger, final_snapshot),
        }
    )
    report["checkpoint"] = interrogate_run_report(report)
    atomic_write_json(run_dir / "checkpoint.json", report["checkpoint"])
    atomic_write_json(report_path, report)
    if operations_control:
        operations_control.update(
            status="checkpoint",
            actionCount=len(history),
            provider=provider_id,
            model=model,
            screenshotPath=str(final_screenshot),
            snapshot=final_snapshot,
            checkpoint=report["checkpoint"],
            finish=finish,
            nuzlocke=public_lineage_context(ruleset, nuzlocke_ledger, final_snapshot),
        )
    print(
        json.dumps(
            {
                "report": str(report_path),
                "provider": provider_id,
                "model": model,
                "finalScreenshot": str(final_screenshot),
                "finalState": str(final_state),
                "video": video_artifact,
                "finish": finish,
                "checkpoint": report["checkpoint"],
                "actionsTaken": len(history),
                "usage": report["usage"],
            },
            indent=2,
        )
    )
    return 0 if report["checkpoint"].get("verdict") not in {"unsafe_state", "model_error"} else 1


def default_model(provider_id: str) -> str:
    if provider_id == "lmstudio-chat":
        return DEFAULT_LOCAL_MODEL
    if provider_id == "openai-responses":
        return "gpt-5.4-nano"
    return "deterministic-replay"


if __name__ == "__main__":
    raise SystemExit(main())
