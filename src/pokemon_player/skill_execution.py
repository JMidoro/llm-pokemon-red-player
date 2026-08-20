from __future__ import annotations

import json
import heapq
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pokemon_player import memory_map as mm
from pokemon_player.battle_ui import (
    BattleActionCursor,
    forced_party_selection_prompt_visible,
    inspect_battle_ui_screenshot,
    party_menu_cursor_slot,
)
from pokemon_player.capsule_a_navigation import (
    MAP_ROUTE_2,
    MAP_ROUTE_22,
    MAP_VIRIDIAN_CITY,
    MAP_VIRIDIAN_FOREST,
    MAP_VIRIDIAN_FOREST_NORTH_GATE,
    MAP_VIRIDIAN_FOREST_SOUTH_GATE,
    MAP_VIRIDIAN_MART,
    MAP_VIRIDIAN_POKECENTER,
    GrassPatch,
    Landmark,
    Position,
    approved_grass_patch_for_map,
    approved_grass_patch_for_position,
    at_landmark,
    is_allowed_position,
    resolve_landmark,
    resolve_grass_patch,
    snapshot_position,
)
from pokemon_player.pallet_navigation import (
    MAP_REDS_HOUSE_2F,
    PALLET_MAP_IDS,
    TRANSITIONS as PALLET_TRANSITIONS,
    PalletTransition,
    default_navigation_target as default_pallet_navigation_target,
    resolve_landmark as resolve_pallet_landmark,
    snapshot_position as pallet_snapshot_position,
)
from pokemon_player.pewter_navigation import (
    MAP_PEWTER_POKECENTER,
    PEWTER_MAP_IDS,
    TRANSITIONS as PEWTER_TRANSITIONS,
    PewterTransition,
    default_navigation_target as default_pewter_navigation_target,
    resolve_landmark as resolve_pewter_landmark,
    snapshot_position as pewter_snapshot_position,
)
from pokemon_player.pyboy_lab import ButtonInput, load_state, open_emulator, save_screenshot, save_state, snapshot
from pokemon_player.rom import RomFingerprint
from pokemon_player.skill_result import SkillResult
from pokemon_player.skills.attempt_catch import attempt_catch, poke_ball_count
from pokemon_player.skills.advance_battle_dialogue import advance_battle_dialogue
from pokemon_player.skills.advance_dialogue import advance_dialogue
from pokemon_player.skills.close_menu_or_cancel import close_menu_or_cancel
from pokemon_player.skills.choose_starter import STARTER_SPECIES, choose_starter, normalize_starter
from pokemon_player.skills.complete_prologue import PrologueHandoff, complete_prologue
from pokemon_player.skills.enter_grass_search_loop import enter_grass_search_loop
from pokemon_player.skills.enter_nickname_text import SUPPORTED_NICKNAME, enter_nickname_text
from pokemon_player.skills.handle_nickname_prompt import (
    NicknameChoice,
    handle_nickname_prompt,
    screenshot_has_naming_screen,
    screenshot_has_nickname_intro_dialogue,
    screenshot_has_nickname_prompt,
)
from pokemon_player.skills.heal_at_pokecenter import heal_at_pokecenter, party_fully_healed
from pokemon_player.skills.navigate_within_viridian_forest_region import (
    navigate_within_viridian_forest_region,
)
from pokemon_player.skills.navigate_within_pallet_region import navigate_within_pallet_region
from pokemon_player.skills.navigate_within_pewter_region import navigate_within_pewter_region
from pokemon_player.skills.recover_to_overworld import (
    recover_to_overworld,
    screenshot_has_dialogue_overlay,
)
from pokemon_player.skills.resolve_battle_outcome_dialogue_bundle import (
    resolve_battle_outcome_dialogue_bundle,
)
from pokemon_player.skills.overworld_rearrange_party import overworld_rearrange_party
from pokemon_player.skills.purchase_pokemart_item import (
    affordable_quantity,
    inventory_count,
    normalize_shop_item,
    purchase_pokemart_item,
    screenshot_has_pokemart_buy_menu,
    stock_for_snapshot,
    stock_index,
    stock_item_by_name,
)
from pokemon_player.skills.run_from_wild_battle import run_from_wild_battle
from pokemon_player.skills.switch_party_member import resolve_target_member, switch_party_member
from pokemon_player.skills.use_move import active_party_member, move_slot, resolve_requested_move, use_move
from pokemon_player.skills.visual_state import inspect_ui_visual_state
from pokemon_player.skills.walk_local_direction import Direction, walk_local_direction
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict
from pokemon_player.trace import dump_trace


PRESS_EVENTS: dict[str, str] = {
    "down": "PRESS_ARROW_DOWN",
    "left": "PRESS_ARROW_LEFT",
    "right": "PRESS_ARROW_RIGHT",
    "up": "PRESS_ARROW_UP",
    "a": "PRESS_BUTTON_A",
    "b": "PRESS_BUTTON_B",
    "start": "PRESS_BUTTON_START",
    "select": "PRESS_BUTTON_SELECT",
}

RELEASE_EVENTS: dict[str, str] = {
    "down": "RELEASE_ARROW_DOWN",
    "left": "RELEASE_ARROW_LEFT",
    "right": "RELEASE_ARROW_RIGHT",
    "up": "RELEASE_ARROW_UP",
    "a": "RELEASE_BUTTON_A",
    "b": "RELEASE_BUTTON_B",
    "start": "RELEASE_BUTTON_START",
    "select": "RELEASE_BUTTON_SELECT",
}

NAVIGATION_DIRECTIONS: tuple[str, ...] = ("up", "down", "left", "right")
NAVIGATION_HOLD_FRAMES = 8
NAVIGATION_SETTLE_FRAMES = 72
NAVIGATION_EXTRA_SETTLE_FRAMES = 24
NAVIGATION_TRAINER_ENGAGEMENT_WAIT_FRAMES = 240
NAVIGATION_POST_MOVE_TRAINER_WAIT_FRAMES = 72
NAVIGATION_TRAINER_ENGAGEMENT_WAIT_CHUNK = 12


def release_all_window_inputs(pyboy: object) -> None:
    for event_name in RELEASE_EVENTS.values():
        send_window_event(pyboy, event_name)


@dataclass(frozen=True)
class SkillRunArtifact:
    run_dir: Path
    report_path: Path
    result: SkillResult


@dataclass(frozen=True)
class SkillChainArtifact:
    run_dir: Path
    report_path: Path
    result: SkillResult


@dataclass(frozen=True)
class ThrowExecutionArtifact:
    status: str
    summary: str
    trace: list[ButtonInput]
    metadata: dict[str, Any]


def execute_attempt_catch(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_wait_frames: int = 900,
    throw_executor: str = "battle-menu-controller",
    battle_menu_policy: str | Path | None = None,
    battle_menu_max_steps: int = 40,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "attempt_catch")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "attempt_catch",
        "executor": {
            "throw_executor": throw_executor,
            "battle_menu_policy": str(battle_menu_policy) if battle_menu_policy else None,
            "battle_menu_max_steps": battle_menu_max_steps,
            "render": render,
            "emulation_speed": emulation_speed,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "attempt_catch",
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }

    initial_result = attempt_catch(snapshot_to_dict(before))
    execution["initial_result"] = initial_result.to_dict()
    if initial_result.status == "blocked":
        trace: list[ButtonInput] = []
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_blocked",
                "reason": initial_result.summary,
            }
        )
    elif initial_result.status != "succeeded":
        trace = []
        after = before
        result = SkillResult(
            skill_id="attempt_catch",
            status="uncertain",
            summary="Catch execution did not start because preconditions were not cleanly satisfied.",
            evidence=initial_result.evidence,
            warnings=initial_result.warnings,
        )
        execution["timeline"].append(
            {
                "event": "precondition_uncertain",
                "reason": result.summary,
            }
        )
    else:
        throw_artifact = execute_throw_from_current_battle(
            pyboy,
            rom_path=rom.path,
            run_dir=run_dir,
            before_snapshot=snapshot_to_dict(before),
            render=render,
            executor=throw_executor,
            battle_menu_policy=battle_menu_policy,
            max_steps=battle_menu_max_steps,
        )
        trace = throw_artifact.trace
        execution["throw_execution"] = throw_artifact.metadata
        execution["timeline"].append(
            {
                "event": "throw_execution_finished",
                "status": throw_artifact.status,
                "summary": throw_artifact.summary,
            }
        )
        if throw_artifact.status != "throw_initiated":
            after = snapshot(pyboy)
            result = SkillResult(
                skill_id="attempt_catch",
                status="uncertain",
                summary="Could not initiate a ball throw from the current battle UI.",
                evidence=(
                    f"throw_executor={throw_executor}",
                    f"throw_status={throw_artifact.status}",
                    f"throw_summary={throw_artifact.summary}",
                ),
            )
            save_screenshot(pyboy, after_screenshot_path)
            save_state(pyboy, after_state_path)
            trace_path.write_text(dump_trace(trace), encoding="utf-8")
            execution["timeline"].append(
                {
                    "event": "skill_result_uncertain",
                    "reason": result.summary,
                }
            )
            execution["failure_classification"] = classify_attempt_catch_failure(
                result,
                execution=execution,
            )
            report = skill_run_report(
                rom=rom,
                state_in=state_in,
                before=before,
                after=after,
                result=result,
                trace=trace,
                before_state_path=before_state_path,
                after_state_path=after_state_path,
                before_screenshot_path=before_screenshot_path,
                after_screenshot_path=after_screenshot_path,
                trace_path=trace_path,
                execution=execution,
            )
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)
        after = snapshot(pyboy)
        save_screenshot(pyboy, after_screenshot_path)
        result = SkillResult(
            skill_id="attempt_catch",
            status="succeeded",
            summary="A Poke Ball item was selected; the catch attempt was initiated.",
            evidence=(
                f"throw_executor={throw_executor}",
                f"throw_status={throw_artifact.status}",
                f"throw_summary={throw_artifact.summary}",
            ),
        )
        execution["timeline"].append(
            {
                "event": "attempt_initiated_result",
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    execution["failure_classification"] = classify_attempt_catch_failure(
        result,
        execution=execution,
    )
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_attempt_catch_chain(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = True,
    post_load_settle_frames: int = 60,
    max_attempts: int = 5,
    max_wait_frames: int = 1800,
    throw_executor: str = "battle-menu-controller",
    battle_menu_policy: str | Path | None = None,
    battle_menu_max_steps: int = 40,
    emulation_speed: int = 0,
) -> SkillChainArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "attempt_catch_chain")
    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)

    initial = snapshot(pyboy)
    initial_snapshot = snapshot_to_dict(initial)
    save_state(pyboy, run_dir / "initial.state")
    save_screenshot(pyboy, run_dir / "initial.png")

    attempts: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = [
        {
            "event": "skill_chain_started",
            "skill_id": "attempt_catch",
            "state_in": str(state_in),
            "max_attempts": max_attempts,
        },
        {
            "event": "initial_snapshot",
            "snapshot_hash": snapshot_hash(initial),
            "screenshot_file": str(run_dir / "initial.png"),
        },
    ]
    result = SkillResult(
        skill_id="attempt_catch",
        status="uncertain",
        summary="No catch attempts were executed.",
    )

    for attempt_index in range(1, max_attempts + 1):
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        if poke_ball_count(current_dict) <= 0:
            result = SkillResult(
                skill_id="attempt_catch",
                status="blocked",
                summary="No Poke Balls remain for another catch attempt.",
                evidence=(f"attempt={attempt_index}", "poke_ball_count=0"),
            )
            timeline.append(
                {
                    "event": "skill_blocked",
                    "attempt": attempt_index,
                    "reason": result.summary,
                }
            )
            break

        attempt_dir = run_dir / f"attempt-{attempt_index:02d}"
        attempt_dir.mkdir()
        before_state = snapshot(pyboy)
        before_dict = snapshot_to_dict(before_state)
        save_state(pyboy, attempt_dir / "before.state")
        save_screenshot(pyboy, attempt_dir / "before.png")

        throw_artifact = execute_throw_from_current_battle(
            pyboy,
            rom_path=rom.path,
            run_dir=attempt_dir,
            before_snapshot=before_dict,
            render=render,
            executor=throw_executor,
            battle_menu_policy=battle_menu_policy,
            max_steps=battle_menu_max_steps,
        )
        trace = throw_artifact.trace
        timeline.append(
            {
                "event": "throw_execution_finished",
                "attempt": attempt_index,
                "status": throw_artifact.status,
                "summary": throw_artifact.summary,
            }
        )
        if throw_artifact.status != "throw_initiated":
            result = SkillResult(
                skill_id="attempt_catch",
                status="uncertain",
                summary="Could not initiate a ball throw from the current battle UI.",
                evidence=(
                    f"attempt={attempt_index}",
                    f"throw_executor={throw_executor}",
                    f"throw_status={throw_artifact.status}",
                    f"throw_summary={throw_artifact.summary}",
                ),
            )
            attempts.append(
                {
                    "attempt": attempt_index,
                    "status": result.status,
                    "summary": result.summary,
                    "trace_file": str(attempt_dir / "trace.json"),
                    "before_state_file": str(attempt_dir / "before.state"),
                    "before_screenshot_file": str(attempt_dir / "before.png"),
                    "before_snapshot_hash": snapshot_hash(before_state),
                    "throw_execution": throw_artifact.metadata,
                    "result": result.to_dict(),
                    "failure_classification": classify_attempt_catch_failure(
                        result,
                        execution={"throw_execution": throw_artifact.metadata},
                    ),
                }
            )
            (attempt_dir / "trace.json").write_text(dump_trace(trace), encoding="utf-8")
            break
        after = wait_for_attempt_catch_outcome(
            pyboy,
            before_snapshot=before_dict,
            screenshot_path=attempt_dir / "after.png",
            trace=trace,
            render=render,
            max_wait_frames=max_wait_frames,
        )
        after_dict = snapshot_to_dict(after)
        result = attempt_catch(
            after_dict,
            before_snapshot=before_dict,
            screenshot_path=attempt_dir / "after.png",
        )
        save_state(pyboy, attempt_dir / "after.state")
        (attempt_dir / "trace.json").write_text(dump_trace(trace), encoding="utf-8")
        attempts.append(
            {
                "attempt": attempt_index,
                "status": result.status,
                "summary": result.summary,
                "trace_file": str(attempt_dir / "trace.json"),
                "before_state_file": str(attempt_dir / "before.state"),
                "after_state_file": str(attempt_dir / "after.state"),
                "before_screenshot_file": str(attempt_dir / "before.png"),
                "after_screenshot_file": str(attempt_dir / "after.png"),
                "before_snapshot_hash": snapshot_hash(before_state),
                "after_snapshot_hash": snapshot_hash(after),
                "throw_execution": throw_artifact.metadata,
                "result": result.to_dict(),
                "failure_classification": classify_attempt_catch_failure(
                    result,
                    execution={"throw_execution": throw_artifact.metadata},
                ),
            }
        )
        timeline.append(
            {
                "event": "critic_result",
                "attempt": attempt_index,
                "status": result.status,
                "summary": result.summary,
            }
        )
        if result.status == "succeeded":
            break
        if result.status not in {"failed", "uncertain"}:
            break

    final = snapshot(pyboy)
    save_state(pyboy, run_dir / "final.state")
    save_screenshot(pyboy, run_dir / "final.png")
    report_path = run_dir / "report.json"
    report = {
        "schema": "skill_chain_report_v1",
        "skill_id": "attempt_catch",
        "created_utc": datetime.now(UTC).isoformat(),
        "state_in": str(state_in),
        "rom": {
            "title": rom.title,
            "path": str(rom.path),
            "sha256": rom.sha256,
            "md5": rom.md5,
            "size_bytes": rom.size_bytes,
        },
        "max_attempts": max_attempts,
        "result": result.to_dict(),
        "initial_snapshot_hash": snapshot_hash(initial),
        "final_snapshot_hash": snapshot_hash(final),
        "initial_snapshot": initial_snapshot,
        "final_snapshot": snapshot_to_dict(final),
        "executor": {
            "throw_executor": throw_executor,
            "battle_menu_policy": str(battle_menu_policy) if battle_menu_policy else None,
            "battle_menu_max_steps": battle_menu_max_steps,
            "render": render,
            "emulation_speed": emulation_speed,
        },
        "timeline": timeline,
        "attempts": attempts,
        "failure_classification": classify_attempt_catch_failure(
            result,
            execution={"attempts": attempts},
        ),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillChainArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_recover_to_overworld(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_inputs: int = 12,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "recover_to_overworld")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    working_screenshot_path = run_dir / "recovery.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)

    trace: list[ButtonInput] = []
    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "recover_to_overworld",
        "executor": {
            "max_inputs": max_inputs,
            "render": render,
            "emulation_speed": emulation_speed,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "recover_to_overworld",
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = recover_to_overworld(
        before_dict,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status == "blocked":
        after = before
        result = initial_result
        execution["timeline"].append({"event": "skill_blocked", "reason": result.summary})
    elif is_stable_overworld(before_dict):
        after = before
        result = initial_result
        execution["timeline"].append({"event": "skill_noop", "reason": result.summary})
    else:
        after, result = run_recover_to_overworld_inputs(
            pyboy,
            before_snapshot=before_dict,
            screenshot_path=working_screenshot_path,
            trace=trace,
            render=render,
            max_inputs=max_inputs,
        )
        execution["timeline"].append(
            {
                "event": "recovery_inputs_finished",
                "status": result.status,
                "summary": result.summary,
                "inputs": len(trace),
            }
        )

    save_state(pyboy, after_state_path)
    save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_advance_dialogue(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = False,
    post_load_settle_frames: int = 60,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "advance_dialogue")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "advance_dialogue",
        "executor": {
            "button": "a",
            "render": render,
            "emulation_speed": emulation_speed,
            "max_inputs": 1,
            "stop_condition": "single bounded A press",
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "advance_dialogue",
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = advance_dialogue(before_dict, screenshot_path=before_screenshot_path)
    execution["initial_result"] = initial_result.to_dict()

    trace: list[ButtonInput] = []
    result = initial_result
    if initial_result.status != "succeeded":
        after = before
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": initial_result.status,
                "reason": initial_result.summary,
            }
        )
    else:
        step = ButtonInput("a", hold_frames=8, settle_frames=90)
        trace.append(step)
        run_timed_trace(pyboy, [step], render=render)
        after = snapshot(pyboy)
        save_screenshot(pyboy, after_screenshot_path)
        result = SkillResult(
            skill_id="advance_dialogue",
            status="succeeded",
            summary="Sent one A press to advance dialogue/text.",
            evidence=("inputs_sent=1",),
            warnings=tuple(str(item) for item in snapshot_to_dict(after).get("warnings", ())),
        )
        execution["timeline"].append(
            {
                "event": "single_dialogue_advance_complete",
                "inputs_sent": len(trace),
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_advance_battle_dialogue(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_inputs: int = 16,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "advance_battle_dialogue")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    working_screenshot_path = run_dir / "battle-dialogue.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []
    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "advance_battle_dialogue",
        "executor": {
            "max_inputs": max_inputs,
            "render": render,
            "emulation_speed": emulation_speed,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "advance_battle_dialogue",
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = advance_battle_dialogue(
        before_dict,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        after = run_advance_battle_dialogue_inputs(
            pyboy,
            trace=trace,
            screenshot_path=working_screenshot_path,
            render=render,
            max_inputs=max_inputs,
        )
        save_screenshot(pyboy, after_screenshot_path)
        result = advance_battle_dialogue(
            snapshot_to_dict(after),
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
        )
        execution["timeline"].append(
            {
                "event": "critic_result",
                "status": result.status,
                "summary": result.summary,
                "inputs": len(trace),
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_choose_starter(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    starter: str = "squirtle",
    nickname: str | None = None,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_wait_frames: int = 1800,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    normalized = normalize_starter(starter)
    if normalized is None:
        raise ValueError(f"Unknown starter choice: {starter!r}.")
    target_nickname = normalize_optional_nickname(nickname)

    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "choose_starter")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "choose_starter",
        "executor": {
            "starter": normalized,
            "nickname": target_nickname,
            "expected_species": STARTER_SPECIES[normalized],
            "render": render,
            "emulation_speed": emulation_speed,
            "max_wait_frames": max_wait_frames,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "choose_starter",
                "state_in": str(state_in),
                "starter": normalized,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = choose_starter(
        before_dict,
        starter=normalized,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": initial_result.status,
                "reason": initial_result.summary,
            }
        )
    else:
        trace.extend(choose_starter_trace(normalized, nickname=target_nickname))
        run_timed_trace(pyboy, trace, render=render)
        after = wait_for_starter_party_species(
            pyboy,
            expected_species=STARTER_SPECIES[normalized],
            max_wait_frames=max_wait_frames,
            render=render,
        )
        if target_nickname:
            keyboard_trace = nickname_keyboard_trace(pyboy, target_nickname)
            trace.extend(keyboard_trace)
            run_timed_trace(pyboy, keyboard_trace, render=render)
            after = wait_for_party_nickname(
                pyboy,
                nickname=target_nickname,
                max_wait_frames=max_wait_frames,
                render=render,
            )
        save_screenshot(pyboy, after_screenshot_path)
        result = choose_starter(
            snapshot_to_dict(after),
            before_snapshot=before_dict,
            starter=normalized,
            screenshot_path=after_screenshot_path,
        )
        if result.status == "succeeded" and target_nickname:
            nickname_result = enter_nickname_text(
                snapshot_to_dict(after),
                before_snapshot=before_dict,
                screenshot_path=after_screenshot_path,
                nickname=target_nickname,
            )
            if nickname_result.status == "succeeded":
                result = SkillResult(
                    skill_id="choose_starter",
                    status="succeeded",
                    summary=f"{STARTER_SPECIES[normalized]} was added to the party with nickname {target_nickname}.",
                    evidence=(*result.evidence, *nickname_result.evidence),
                    warnings=(*result.warnings, *nickname_result.warnings),
                )
            else:
                result = SkillResult(
                    skill_id="choose_starter",
                    status="uncertain",
                    summary=f"{STARTER_SPECIES[normalized]} was selected, but nickname {target_nickname} was not confirmed.",
                    evidence=(*result.evidence, *nickname_result.evidence),
                    warnings=(*result.warnings, *nickname_result.warnings),
                )
        execution["timeline"].append(
            {
                "event": "critic_result",
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_resolve_battle_outcome_dialogue_bundle(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = False,
    post_load_settle_frames: int = 60,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    return execute_single_button_skill(
        pyboy,
        skill_id="resolve_battle_outcome_dialogue_bundle",
        runner=resolve_battle_outcome_dialogue_bundle,
        button="a",
        state_in=state_in,
        rom=rom,
        run_root=run_root,
        render=render,
        post_load_settle_frames=post_load_settle_frames,
        emulation_speed=emulation_speed,
    )


def execute_complete_prologue(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    player_name: str = "RED",
    rival_name: str = "BLUE",
    handoff: PrologueHandoff = "pallet_outside",
    render: bool = False,
    post_load_settle_frames: int = 1,
    max_intro_presses: int = 120,
    max_handoff_inputs: int = 120,
    max_segment_expansions: int = 1600,
    emulation_speed: int = 0,
    planner_window: str = "null",
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "complete_prologue")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"
    player_keyboard_path = run_dir / "player_name_keyboard.png"
    rival_keyboard_path = run_dir / "rival_name_keyboard.png"
    red_house_state_path = run_dir / "red_house_2f.state"
    red_house_screenshot_path = run_dir / "red_house_2f.png"
    handoff_screenshot_path = run_dir / "handoff-route.png"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []
    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "complete_prologue",
        "executor": {
            "player_name": player_name,
            "rival_name": rival_name,
            "handoff": handoff,
            "render": render,
            "emulation_speed": emulation_speed,
            "max_intro_presses": max_intro_presses,
            "max_handoff_inputs": max_handoff_inputs,
            "max_segment_expansions": max_segment_expansions,
            "planner_window": planner_window,
        },
        "artifacts": {
            "player_name_keyboard": str(player_keyboard_path),
            "rival_name_keyboard": str(rival_keyboard_path),
            "red_house_2f_state": str(red_house_state_path),
            "red_house_2f_screenshot": str(red_house_screenshot_path),
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "complete_prologue",
                "state_in": str(state_in),
                "player_name": player_name,
                "rival_name": rival_name,
                "handoff": handoff,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = complete_prologue(
        before_dict,
        screenshot_path=before_screenshot_path,
        player_name=player_name,
        rival_name=rival_name,
        handoff=handoff,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        if not screenshot_has_naming_screen(before_screenshot_path):
            append_and_run_button(pyboy, trace, "start", render=render, settle_frames=240)
            append_and_run_button(pyboy, trace, "a", render=render, settle_frames=240)
            execution["timeline"].append({"event": "new_game_selected", "inputs": len(trace)})

        player_wait = wait_for_prologue_naming_screen(
            pyboy,
            trace=trace,
            screenshot_path=player_keyboard_path,
            render=render,
            max_presses=max_intro_presses,
        )
        execution["timeline"].append({"event": "player_name_keyboard_wait", **player_wait})
        if not player_wait["found"]:
            after = snapshot(pyboy)
            result = SkillResult(
                skill_id="complete_prologue",
                status="uncertain",
                summary="Player name keyboard did not appear before the prologue input budget was exhausted.",
                evidence=(f"inputs={len(trace)}",),
                warnings=tuple(str(item) for item in snapshot_to_dict(after).get("warnings", ())),
            )
        else:
            player_trace = nickname_keyboard_trace(pyboy, player_name.strip().upper())
            trace.extend(player_trace)
            run_timed_trace(pyboy, player_trace, render=render)
            execution["timeline"].append(
                {
                    "event": "player_name_entered",
                    "name": player_name.strip().upper(),
                    "inputs": len(player_trace),
                }
            )

            rival_wait = wait_for_prologue_naming_screen(
                pyboy,
                trace=trace,
                screenshot_path=rival_keyboard_path,
                render=render,
                max_presses=max_intro_presses,
            )
            execution["timeline"].append({"event": "rival_name_keyboard_wait", **rival_wait})
            if not rival_wait["found"]:
                after = snapshot(pyboy)
                result = SkillResult(
                    skill_id="complete_prologue",
                    status="uncertain",
                    summary="Rival name keyboard did not appear before the prologue input budget was exhausted.",
                    evidence=(f"inputs={len(trace)}",),
                    warnings=tuple(str(item) for item in snapshot_to_dict(after).get("warnings", ())),
                )
            else:
                rival_trace = nickname_keyboard_trace(pyboy, rival_name.strip().upper())
                trace.extend(rival_trace)
                run_timed_trace(pyboy, rival_trace, render=render)
                execution["timeline"].append(
                    {
                        "event": "rival_name_entered",
                        "name": rival_name.strip().upper(),
                        "inputs": len(rival_trace),
                    }
                )

                red_house = wait_for_red_house_2f_control(
                    pyboy,
                    trace=trace,
                    screenshot_path=red_house_screenshot_path,
                    render=render,
                    max_presses=max_intro_presses,
                )
                execution["timeline"].append({"event": "red_house_2f_wait", **red_house})
                if not red_house["found"]:
                    after = snapshot(pyboy)
                    result = SkillResult(
                        skill_id="complete_prologue",
                        status="uncertain",
                        summary="Prologue did not reach stable Red's House 2F control before the input budget was exhausted.",
                        evidence=(f"inputs={len(trace)}",),
                        warnings=tuple(str(item) for item in snapshot_to_dict(after).get("warnings", ())),
                    )
                else:
                    save_state(pyboy, red_house_state_path)
                    if handoff == "pallet_outside":
                        handoff_plan = execute_prologue_handoff_navigation(
                            pyboy,
                            rom=rom,
                            trace=trace,
                            screenshot_path=handoff_screenshot_path,
                            render=render,
                            max_inputs=max_handoff_inputs,
                            max_segment_expansions=max_segment_expansions,
                            planner_window=planner_window,
                        )
                        execution["timeline"].append({"event": "handoff_navigation", **handoff_plan})
                    after = snapshot(pyboy)
                    after_dict = snapshot_to_dict(after)
                    save_screenshot(pyboy, after_screenshot_path)
                    result = complete_prologue(
                        after_dict,
                        before_snapshot=before_dict,
                        screenshot_path=after_screenshot_path,
                        player_name=player_name,
                        rival_name=rival_name,
                        handoff=handoff,
                    )
                    execution["timeline"].append(
                        {
                            "event": "critic_result",
                            "status": result.status,
                            "summary": result.summary,
                        }
                    )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def wait_for_prologue_naming_screen(
    pyboy: object,
    *,
    trace: list[ButtonInput],
    screenshot_path: Path,
    render: bool,
    max_presses: int,
) -> dict[str, Any]:
    for press_count in range(max_presses + 1):
        save_screenshot(pyboy, screenshot_path)
        if screenshot_has_naming_screen(screenshot_path):
            return {"found": True, "presses": press_count, "screenshot_file": str(screenshot_path)}
        if press_count >= max_presses:
            break
        append_and_run_button(pyboy, trace, "a", render=render, settle_frames=120)
    return {"found": False, "presses": max_presses, "screenshot_file": str(screenshot_path)}


def wait_for_red_house_2f_control(
    pyboy: object,
    *,
    trace: list[ButtonInput],
    screenshot_path: Path,
    render: bool,
    max_presses: int,
) -> dict[str, Any]:
    for press_count in range(max_presses + 1):
        save_screenshot(pyboy, screenshot_path)
        current = snapshot_to_dict(snapshot(pyboy))
        position = current.get("position") if isinstance(current.get("position"), dict) else {}
        visual = inspect_ui_visual_state(screenshot_path)
        if (
            current.get("mode") == "overworld"
            and position.get("map_id") == MAP_REDS_HOUSE_2F
            and not visual.bottom_text_box
        ):
            return {
                "found": True,
                "presses": press_count,
                "position": position,
                "screenshot_file": str(screenshot_path),
            }
        if press_count >= max_presses:
            break
        append_and_run_button(pyboy, trace, "a", render=render, settle_frames=150)
    current = snapshot_to_dict(snapshot(pyboy))
    return {
        "found": False,
        "presses": max_presses,
        "position": current.get("position"),
        "screenshot_file": str(screenshot_path),
    }


def execute_prologue_handoff_navigation(
    pyboy: object,
    *,
    rom: RomFingerprint,
    trace: list[ButtonInput],
    screenshot_path: Path,
    render: bool,
    max_inputs: int,
    max_segment_expansions: int,
    planner_window: str,
) -> dict[str, Any]:
    landmark = resolve_pallet_landmark("pallet_home_1f_exit")
    if landmark is None:
        return {"status": "failed", "summary": "Pallet home exit landmark is unavailable."}
    start_state_bytes = pyboy_state_bytes(pyboy)
    planner_pyboy = open_emulator(rom.path, window=planner_window)
    try:
        configure_skill_emulation(planner_pyboy, 0)
        load_pyboy_state_bytes(planner_pyboy, start_state_bytes)
        plan = plan_pallet_navigation_path(
            planner_pyboy,
            target_landmark=landmark,
            max_inputs=max_inputs,
            max_segment_expansions=max_segment_expansions,
            render=planner_window == "SDL2",
        )
    finally:
        planner_pyboy.stop(False)
    if plan["status"] not in {
        "planned",
        "planned_wild_battle",
        "planned_trainer_battle",
        "planned_trainer_engagement",
    }:
        return {
            "status": plan["status"],
            "summary": plan["summary"],
            "inputs": len(plan.get("buttons", [])),
            "segments": plan.get("segments", []),
        }
    for button in [str(item) for item in plan["buttons"]]:
        append_and_run_navigation_button(pyboy, trace, button, render=render)
    save_screenshot(pyboy, screenshot_path)
    return {
        "status": plan["status"],
        "summary": plan["summary"],
        "inputs": len(plan.get("buttons", [])),
        "segments": plan.get("segments", []),
        "screenshot_file": str(screenshot_path),
    }


def execute_handle_nickname_prompt(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    choice: NicknameChoice = "decline",
    render: bool = False,
    post_load_settle_frames: int = 60,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    if choice not in {"accept", "decline"}:
        raise ValueError(f"Unsupported nickname prompt choice: {choice!r}.")

    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "handle_nickname_prompt")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    working_screenshot_path = run_dir / "working.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []
    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "handle_nickname_prompt",
        "executor": {
            "choice": choice,
            "render": render,
            "emulation_speed": emulation_speed,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "handle_nickname_prompt",
                "state_in": str(state_in),
                "choice": choice,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = handle_nickname_prompt(
        before_dict,
        screenshot_path=before_screenshot_path,
        choice=choice,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        save_screenshot(pyboy, working_screenshot_path)
        for _ in range(4):
            if screenshot_has_nickname_prompt(working_screenshot_path) or screenshot_has_naming_screen(
                working_screenshot_path
            ):
                break
            if not screenshot_has_nickname_intro_dialogue(working_screenshot_path):
                break
            append_and_run_button(pyboy, trace, "a", render=render, settle_frames=48)
            save_screenshot(pyboy, working_screenshot_path)
            execution["timeline"].append(
                {
                    "event": "nickname_intro_advanced",
                    "inputs": len(trace),
                    "screenshot_file": str(working_screenshot_path),
                }
            )

        if screenshot_has_nickname_prompt(working_screenshot_path):
            if choice == "accept":
                append_and_run_button(pyboy, trace, "a", render=render, settle_frames=60)
            else:
                append_and_run_button(pyboy, trace, "down", render=render, settle_frames=18)
                append_and_run_button(pyboy, trace, "a", render=render, settle_frames=90)
            execution["timeline"].append(
                {
                    "event": "nickname_prompt_choice_sent",
                    "choice": choice,
                    "inputs": len(trace),
                }
            )
        elif screenshot_has_naming_screen(working_screenshot_path):
            execution["timeline"].append(
                {
                    "event": "naming_screen_already_active",
                    "choice": choice,
                    "inputs": len(trace),
                }
            )
        else:
            execution["timeline"].append(
                {
                    "event": "nickname_prompt_not_found_after_intro",
                    "choice": choice,
                    "inputs": len(trace),
                }
            )

        after = snapshot(pyboy)
        save_screenshot(pyboy, after_screenshot_path)
        result = handle_nickname_prompt(
            snapshot_to_dict(after),
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
            choice=choice,
        )
        execution["timeline"].append(
            {
                "event": "critic_result",
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_enter_nickname_text(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    nickname: str,
    render: bool = False,
    post_load_settle_frames: int = 60,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    target = nickname.strip().upper()
    if not target:
        raise ValueError("enter_nickname_text requires a nickname.")
    configure_skill_emulation(pyboy, emulation_speed)
    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    trace = nickname_keyboard_trace(pyboy, target)
    return execute_trace_skill(
        pyboy,
        skill_id="enter_nickname_text",
        runner=enter_nickname_text,
        trace=trace,
        state_in=state_in,
        rom=rom,
        run_root=run_root,
        render=render,
        post_load_settle_frames=post_load_settle_frames,
        emulation_speed=emulation_speed,
        runner_kwargs={"nickname": target},
        state_already_loaded=True,
    )


def execute_heal_at_pokecenter(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_inputs: int = 24,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "heal_at_pokecenter")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    working_screenshot_path = run_dir / "heal-working.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []
    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "heal_at_pokecenter",
        "executor": {
            "max_inputs": max_inputs,
            "render": render,
            "emulation_speed": emulation_speed,
            "counter_tile": "map=0x29,x=3,y=3",
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "heal_at_pokecenter",
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = heal_at_pokecenter(before_dict, screenshot_path=before_screenshot_path)
    execution["initial_result"] = initial_result.to_dict()
    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        after = run_pokecenter_heal_inputs(
            pyboy,
            before_snapshot=before_dict,
            screenshot_path=working_screenshot_path,
            trace=trace,
            render=render,
            max_inputs=max_inputs,
        )
        save_screenshot(pyboy, after_screenshot_path)
        result = heal_at_pokecenter(
            snapshot_to_dict(after),
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
        )
        execution["timeline"].append(
            {
                "event": "heal_inputs_finished",
                "inputs": len(trace),
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_purchase_pokemart_item(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    item: str = "Poke Ball",
    quantity: int = 1,
    render: bool = False,
    post_load_settle_frames: int = 60,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "purchase_pokemart_item")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    normalized_item = normalize_shop_item(item)
    requested_quantity = max(int(quantity or 1), 1)
    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []
    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "purchase_pokemart_item",
        "executor": {
            "item": normalized_item,
            "quantity": requested_quantity,
            "render": render,
            "emulation_speed": emulation_speed,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "purchase_pokemart_item",
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = purchase_pokemart_item(
        before_dict,
        item=normalized_item,
        quantity=requested_quantity,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        stock = stock_for_snapshot(before_dict)
        target_index = stock_index(stock, normalized_item)
        stock_item = stock_item_by_name(stock, normalized_item)
        money = int(before_dict.get("money", 0) or 0)
        buy_count = requested_quantity
        if stock_item is not None:
            buy_count = affordable_quantity(money, stock_item.price, requested_quantity)
        if target_index is None:
            buy_count = 0
        working_screenshot_path = run_dir / "purchase-working.png"
        purchased = 0
        for purchase_index in range(buy_count):
            if target_index is None:
                break
            select_cyclic_menu_index(
                pyboy,
                trace,
                target_index=target_index,
                item_count=len(stock),
                render=render,
                settle_frames=18,
            )
            count_before_purchase = inventory_count(snapshot_to_dict(snapshot(pyboy)), normalized_item)
            count_after_purchase = press_until_inventory_count_increases(
                pyboy,
                trace,
                item_name=normalized_item,
                before_count=count_before_purchase,
                screenshot_path=working_screenshot_path,
                render=render,
                max_presses=8,
            )
            if count_after_purchase <= count_before_purchase:
                execution["timeline"].append(
                    {
                        "event": "purchase_cycle_stopped",
                        "purchase_index": purchase_index + 1,
                        "item": normalized_item,
                        "reason": "Inventory count did not increase after confirming purchase.",
                    }
                )
                break
            purchased += count_after_purchase - count_before_purchase
            wait_for_pokemart_buy_menu(
                pyboy,
                trace,
                screenshot_path=working_screenshot_path,
                render=render,
                max_presses=8,
            )
            execution["timeline"].append(
                {
                    "event": "purchase_cycle_sent",
                    "purchase_index": purchase_index + 1,
                    "item": normalized_item,
                    "inventory_count": count_after_purchase,
                }
            )
        after = snapshot(pyboy)
        save_screenshot(pyboy, after_screenshot_path)
        result = purchase_pokemart_item(
            snapshot_to_dict(after),
            item=normalized_item,
            quantity=requested_quantity,
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
        )
        execution["timeline"].append(
            {
                "event": "purchase_inputs_finished",
                "requested_quantity": requested_quantity,
                "attempted_quantity": buy_count,
                "observed_purchased_quantity": purchased,
                "inputs": len(trace),
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_close_menu_or_cancel(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = False,
    post_load_settle_frames: int = 60,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "close_menu_or_cancel")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    initial_result = close_menu_or_cancel(before_dict, screenshot_path=before_screenshot_path)
    visual = inspect_ui_visual_state(before_screenshot_path)
    position = snapshot_position(before_dict)
    trace: list[ButtonInput] = []
    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "close_menu_or_cancel",
        "executor": {
            "render": render,
            "emulation_speed": emulation_speed,
            "strategy": "battle_action_menu_recovery"
            if before_dict.get("mode") == "battle" or before_dict.get("battle_type_raw") not in {None, 0}
            else (
                "viridian_mart_shop_escape"
                if position and position.map_id == 0x2A and visual.bottom_text_box and visual.upper_menu
                else "single_b"
            ),
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "close_menu_or_cancel",
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
        "initial_result": initial_result.to_dict(),
    }

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        if execution["executor"]["strategy"] == "battle_action_menu_recovery":
            status = recover_to_battle_action_menu_safely(
                pyboy,
                trace=trace,
                screenshot_path=after_screenshot_path,
                render=render,
            )
            execution["timeline"].append(
                {
                    "event": "battle_cancel_recovery_trace_sent",
                    "status": status,
                    "inputs": len(trace),
                }
            )
        else:
            buttons = (
                ["b", "b", "b", "b", "b", "b", "down", "down", "a"]
                if execution["executor"]["strategy"] == "viridian_mart_shop_escape"
                else ["b"]
            )
            for button in buttons:
                step = ButtonInput(button, hold_frames=8, settle_frames=60)
                trace.append(step)
                run_timed_trace(pyboy, [step], render=render)
            execution["timeline"].append(
                {
                    "event": "cancel_trace_sent",
                    "buttons": buttons,
                    "inputs": len(trace),
                }
            )
        after = snapshot(pyboy)
        save_screenshot(pyboy, after_screenshot_path)
        result = close_menu_or_cancel(
            snapshot_to_dict(after),
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
        )
        execution["timeline"].append(
            {
                "event": "critic_result",
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_walk_local_direction(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    direction: Direction = "left",
    render: bool = False,
    post_load_settle_frames: int = 60,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    return execute_single_button_skill(
        pyboy,
        skill_id="walk_local_direction",
        runner=walk_local_direction,
        button=direction,
        state_in=state_in,
        rom=rom,
        run_root=run_root,
        render=render,
        post_load_settle_frames=post_load_settle_frames,
        emulation_speed=emulation_speed,
        runner_kwargs={"direction": direction},
    )


def execute_navigate_within_viridian_forest_region(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    target: str | None = "forest_grass",
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_inputs: int = 260,
    max_segment_expansions: int = 3000,
    emulation_speed: int = 0,
    planner_window: str = "null",
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "navigate_within_viridian_forest_region")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    start_state_bytes = pyboy_state_bytes(pyboy)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "navigate_within_viridian_forest_region",
        "executor": {
            "target": target,
            "render": render,
            "emulation_speed": emulation_speed,
            "max_inputs": max_inputs,
            "max_segment_expansions": max_segment_expansions,
            "planner_window": planner_window,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "navigate_within_viridian_forest_region",
                "state_in": str(state_in),
                "target": target,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }

    initial_result = navigate_within_viridian_forest_region(
        before_dict,
        target=target,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()
    landmark = resolve_landmark(target)
    before_position = snapshot_position(before_dict)

    if initial_result.status != "succeeded" or landmark is None:
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    elif at_landmark(before_position, landmark):
        after = before
        result = initial_result
        execution["timeline"].append({"event": "skill_noop", "reason": result.summary})
    else:
        executable_plan_statuses = {
            "planned",
            "planned_wild_battle",
            "planned_trainer_battle",
            "planned_trainer_engagement",
        }
        execution_state_bytes = start_state_bytes
        execution["navigation_plans"] = []
        after = before
        result = initial_result

        for attempt_index in range(8):
            remaining_inputs = max(max_inputs - len(trace), 0)
            if remaining_inputs <= 0:
                after = snapshot(pyboy)
                result = SkillResult(
                    skill_id="navigate_within_viridian_forest_region",
                    status="uncertain",
                    summary="Navigation input budget was exhausted during execution.",
                    evidence=(f"target={target}", f"inputs_used={len(trace)}"),
                )
                execution["timeline"].append(
                    {
                        "event": "navigation_budget_exhausted",
                        "inputs": len(trace),
                    }
                )
                break

            planner_pyboy = open_emulator(rom.path, window=planner_window)
            try:
                configure_skill_emulation(planner_pyboy, 0)
                load_pyboy_state_bytes(planner_pyboy, execution_state_bytes)
                plan = plan_capsule_a_navigation_path(
                    planner_pyboy,
                    target_landmark=landmark,
                    max_inputs=remaining_inputs,
                    max_segment_expansions=max_segment_expansions,
                    render=planner_window == "SDL2",
                )
            finally:
                planner_pyboy.stop(False)
            if attempt_index == 0:
                execution["navigation_plan"] = plan
            execution["navigation_plans"].append(plan)
            execution["timeline"].append(
                {
                    "event": "navigation_plan_finished",
                    "attempt": attempt_index + 1,
                    "status": plan["status"],
                    "summary": plan["summary"],
                    "inputs": len(plan.get("buttons", [])),
                    "segments": plan.get("segments", []),
                    "remaining_inputs": remaining_inputs,
                }
            )
            if plan["status"] not in executable_plan_statuses:
                after = snapshot(pyboy)
                result = SkillResult(
                    skill_id="navigate_within_viridian_forest_region",
                    status="uncertain",
                    summary=str(plan["summary"]),
                    evidence=(
                        f"target={target}",
                        f"plan_status={plan['status']}",
                        f"inputs_planned={len(plan.get('buttons', []))}",
                    ),
                )
                break

            load_pyboy_state_bytes(pyboy, execution_state_bytes)
            plan_buttons = [str(button) for button in plan["buttons"]]
            interrupted = False
            for index, button in enumerate(plan_buttons):
                append_and_run_navigation_button(pyboy, trace, str(button), render=render)
                current = snapshot_to_dict(snapshot(pyboy))
                if wild_battle_active(current):
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "wild_battle_started",
                            "inputs": len(trace),
                            "position": snapshot_position(current).format()
                            if snapshot_position(current)
                            else "unknown",
                        }
                    )
                    interrupted = True
                    break
                if trainer_battle_active(current):
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "trainer_battle_started",
                            "inputs": len(trace),
                            "position": snapshot_position(current).format()
                            if snapshot_position(current)
                            else "unknown",
                        }
                    )
                    interrupted = True
                    break
                if trainer_engagement_dialogue_active(current):
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "trainer_engagement_dialogue",
                            "inputs": len(trace),
                            "position": snapshot_position(current).format()
                            if snapshot_position(current)
                            else "unknown",
                        }
                    )
                    interrupted = True
                    break
                if current.get("battle_type_raw") not in {None, 0} or current.get("mode") == "battle":
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "battle_started",
                            "inputs": len(trace),
                        }
                    )
                    interrupted = True
                    break
                if current.get("mode") != "overworld":
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "left_overworld_mode",
                            "inputs": len(trace),
                            "mode": current.get("mode"),
                        }
                    )
                    interrupted = True
                    break
                if (
                    plan["status"] in {"planned_trainer_battle", "planned_trainer_engagement"}
                    and index == len(plan_buttons) - 1
                ):
                    engagement = wait_for_navigation_trainer_engagement(
                        pyboy,
                        render=render,
                        max_frames=NAVIGATION_TRAINER_ENGAGEMENT_WAIT_FRAMES,
                    )
                    if engagement is not None:
                        execution["timeline"].append(
                            {
                                "event": "navigation_interrupted",
                                "reason": engagement["reason"],
                                "inputs": len(trace),
                                "wait_frames": engagement["wait_frames"],
                                "position": engagement.get("position", "unknown"),
                            }
                        )
                        interrupted = True
                    break
            after = snapshot(pyboy)
            save_screenshot(pyboy, after_screenshot_path)
            result = navigate_within_viridian_forest_region(
                snapshot_to_dict(after),
                target=target,
                before_snapshot=before_dict,
                screenshot_path=after_screenshot_path,
            )
            execution["timeline"].append(
                {
                    "event": "critic_result",
                    "status": result.status,
                    "summary": result.summary,
                    "inputs": len(trace),
                }
            )
            if result.status == "succeeded" or interrupted:
                break
            after_dict = snapshot_to_dict(after)
            if (
                plan["status"] == "planned_wild_battle"
                and navigation_snapshot_is_routeable(after_dict)
                and plan_buttons
                and len(trace) < max_inputs
            ):
                position = snapshot_position(after_dict)
                execution["timeline"].append(
                    {
                        "event": "predicted_wild_battle_not_materialized",
                        "attempt": attempt_index + 1,
                        "position": position.format() if position else "unknown",
                        "inputs": len(trace),
                    }
                )
                execution_state_bytes = pyboy_state_bytes(pyboy)
                continue
            break

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_navigate_within_pallet_region(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    target: str | None = None,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_inputs: int = 180,
    max_segment_expansions: int = 1600,
    emulation_speed: int = 0,
    planner_window: str = "null",
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "navigate_within_pallet_region")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    if target is None:
        target = default_pallet_navigation_target(before_dict)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    start_state_bytes = pyboy_state_bytes(pyboy)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "navigate_within_pallet_region",
        "executor": {
            "target": target,
            "render": render,
            "emulation_speed": emulation_speed,
            "max_inputs": max_inputs,
            "max_segment_expansions": max_segment_expansions,
            "planner_window": planner_window,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "navigate_within_pallet_region",
                "state_in": str(state_in),
                "target": target,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }

    initial_result = navigate_within_pallet_region(
        before_dict,
        target=target,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()
    landmark = resolve_pallet_landmark(target)
    before_position = pallet_snapshot_position(before_dict)

    if initial_result.status != "succeeded" or landmark is None:
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    elif before_position == landmark.position:
        after = before
        result = initial_result
        execution["timeline"].append({"event": "skill_noop", "reason": result.summary})
    else:
        planner_pyboy = open_emulator(rom.path, window=planner_window)
        try:
            configure_skill_emulation(planner_pyboy, 0)
            load_pyboy_state_bytes(planner_pyboy, start_state_bytes)
            plan = plan_pallet_navigation_path(
                planner_pyboy,
                target_landmark=landmark,
                max_inputs=max_inputs,
                max_segment_expansions=max_segment_expansions,
                render=planner_window == "SDL2",
            )
        finally:
            planner_pyboy.stop(False)
        execution["navigation_plan"] = plan
        execution["timeline"].append(
            {
                "event": "navigation_plan_finished",
                "status": plan["status"],
                "summary": plan["summary"],
                "inputs": len(plan.get("buttons", [])),
                "segments": plan.get("segments", []),
            }
        )
        executable_plan_statuses = {
            "planned",
            "planned_wild_battle",
            "planned_trainer_battle",
            "planned_trainer_engagement",
        }
        if plan["status"] not in executable_plan_statuses:
            after = snapshot(pyboy)
            result = SkillResult(
                skill_id="navigate_within_pallet_region",
                status="uncertain",
                summary=str(plan["summary"]),
                evidence=(
                    f"target={target}",
                    f"plan_status={plan['status']}",
                    f"inputs_planned={len(plan.get('buttons', []))}",
                ),
            )
        else:
            load_pyboy_state_bytes(pyboy, start_state_bytes)
            for button in [str(item) for item in plan["buttons"]]:
                append_and_run_navigation_button(pyboy, trace, button, render=render)
                current = snapshot_to_dict(snapshot(pyboy))
                if wild_battle_active(current):
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "wild_battle_started",
                            "inputs": len(trace),
                            "position": pallet_snapshot_position(current).format()
                            if pallet_snapshot_position(current)
                            else "unknown",
                        }
                    )
                    break
                if trainer_battle_active(current):
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "trainer_battle_started",
                            "inputs": len(trace),
                            "position": pallet_snapshot_position(current).format()
                            if pallet_snapshot_position(current)
                            else "unknown",
                        }
                    )
                    break
                if current.get("battle_type_raw") not in {None, 0} or current.get("mode") == "battle":
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "battle_started",
                            "inputs": len(trace),
                        }
                    )
                    break
                if current.get("mode") not in {"overworld", "dialogue", "menu_or_dialogue_uncertain"}:
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "left_routeable_mode",
                            "inputs": len(trace),
                            "mode": current.get("mode"),
                        }
                    )
                    break
            after = snapshot(pyboy)
            save_screenshot(pyboy, after_screenshot_path)
            after_dict = snapshot_to_dict(after)
            result = navigate_within_pallet_region(
                after_dict,
                target=target,
                before_snapshot=before_dict,
                screenshot_path=after_screenshot_path,
            )
            if result.status != "succeeded" and oak_lab_exit_story_progress(
                before_dict,
                after_dict,
                target=target,
            ):
                result = SkillResult(
                    skill_id="navigate_within_pallet_region",
                    status="succeeded",
                    summary="Oak's Lab exit route triggered rival/story progression before reaching the physical exit.",
                    evidence=(
                        "target=oaks_lab_exit",
                        "story_progress=oak_lab_exit_intercept",
                    ),
                    warnings=result.warnings,
                )
            if result.status != "succeeded" and oak_lab_exit_completed(
                before_dict,
                after_dict,
                target=target,
            ):
                result = SkillResult(
                    skill_id="navigate_within_pallet_region",
                    status="succeeded",
                    summary="Oak's Lab exit route completed and placed the player in Pallet Town.",
                    evidence=(
                        "target=oaks_lab_exit",
                        "story_progress=oak_lab_exit_completed",
                    ),
                    warnings=result.warnings,
                )
            execution["timeline"].append(
                {
                    "event": "critic_result",
                    "status": result.status,
                    "summary": result.summary,
                    "inputs": len(trace),
                }
            )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_navigate_within_pewter_region(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    target: str | None = None,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_inputs: int = 260,
    max_segment_expansions: int = 3000,
    emulation_speed: int = 0,
    planner_window: str = "null",
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "navigate_within_pewter_region")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    if target is None:
        target = default_pewter_navigation_target(before_dict)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    start_state_bytes = pyboy_state_bytes(pyboy)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "navigate_within_pewter_region",
        "executor": {
            "target": target,
            "render": render,
            "emulation_speed": emulation_speed,
            "max_inputs": max_inputs,
            "max_segment_expansions": max_segment_expansions,
            "planner_window": planner_window,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "navigate_within_pewter_region",
                "state_in": str(state_in),
                "target": target,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }

    initial_result = navigate_within_pewter_region(
        before_dict,
        target=target,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()
    landmark = resolve_pewter_landmark(target)
    before_position = pewter_snapshot_position(before_dict)

    if initial_result.status != "succeeded" or landmark is None:
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    elif before_position == landmark.position:
        after = before
        result = initial_result
        execution["timeline"].append({"event": "skill_noop", "reason": result.summary})
    else:
        executable_plan_statuses = {
            "planned",
            "planned_wild_battle",
            "planned_trainer_battle",
            "planned_trainer_engagement",
        }
        execution_state_bytes = start_state_bytes
        execution["navigation_plans"] = []
        after = before
        result = initial_result

        for attempt_index in range(8):
            remaining_inputs = max(max_inputs - len(trace), 0)
            if remaining_inputs <= 0:
                after = snapshot(pyboy)
                result = SkillResult(
                    skill_id="navigate_within_pewter_region",
                    status="uncertain",
                    summary="Pewter navigation input budget was exhausted during execution.",
                    evidence=(f"target={target}", f"inputs_used={len(trace)}"),
                )
                execution["timeline"].append(
                    {
                        "event": "navigation_budget_exhausted",
                        "inputs": len(trace),
                    }
                )
                break

            planner_pyboy = open_emulator(rom.path, window=planner_window)
            try:
                configure_skill_emulation(planner_pyboy, 0)
                load_pyboy_state_bytes(planner_pyboy, execution_state_bytes)
                plan = plan_pewter_navigation_path(
                    planner_pyboy,
                    target_landmark=landmark,
                    max_inputs=remaining_inputs,
                    max_segment_expansions=max_segment_expansions,
                    render=planner_window == "SDL2",
                )
            finally:
                planner_pyboy.stop(False)
            if attempt_index == 0:
                execution["navigation_plan"] = plan
            execution["navigation_plans"].append(plan)
            execution["timeline"].append(
                {
                    "event": "navigation_plan_finished",
                    "attempt": attempt_index + 1,
                    "status": plan["status"],
                    "summary": plan["summary"],
                    "inputs": len(plan.get("buttons", [])),
                    "segments": plan.get("segments", []),
                    "remaining_inputs": remaining_inputs,
                }
            )
            if plan["status"] not in executable_plan_statuses:
                after = snapshot(pyboy)
                result = SkillResult(
                    skill_id="navigate_within_pewter_region",
                    status="uncertain",
                    summary=str(plan["summary"]),
                    evidence=(
                        f"target={target}",
                        f"plan_status={plan['status']}",
                        f"inputs_planned={len(plan.get('buttons', []))}",
                    ),
                )
                break

            load_pyboy_state_bytes(pyboy, execution_state_bytes)
            plan_buttons = [str(item) for item in plan["buttons"]]
            interrupted = False
            for index, button in enumerate(plan_buttons):
                append_and_run_navigation_button(pyboy, trace, button, render=render)
                current = snapshot_to_dict(snapshot(pyboy))
                if wild_battle_active(current):
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "wild_battle_started",
                            "inputs": len(trace),
                            "position": pewter_snapshot_position(current).format()
                            if pewter_snapshot_position(current)
                            else "unknown",
                        }
                    )
                    interrupted = True
                    break
                if trainer_battle_active(current):
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "trainer_battle_started",
                            "inputs": len(trace),
                            "position": pewter_snapshot_position(current).format()
                            if pewter_snapshot_position(current)
                            else "unknown",
                        }
                    )
                    interrupted = True
                    break
                if trainer_engagement_dialogue_active(current):
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "trainer_engagement_dialogue",
                            "inputs": len(trace),
                            "position": pewter_snapshot_position(current).format()
                            if pewter_snapshot_position(current)
                            else "unknown",
                        }
                    )
                    interrupted = True
                    break
                if current.get("battle_type_raw") not in {None, 0} or current.get("mode") == "battle":
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "battle_started",
                            "inputs": len(trace),
                        }
                    )
                    interrupted = True
                    break
                if current.get("mode") not in {"overworld", "dialogue", "menu_or_dialogue_uncertain"}:
                    execution["timeline"].append(
                        {
                            "event": "navigation_interrupted",
                            "reason": "left_routeable_mode",
                            "inputs": len(trace),
                            "mode": current.get("mode"),
                        }
                    )
                    interrupted = True
                    break
                if (
                    plan["status"] in {"planned_trainer_battle", "planned_trainer_engagement"}
                    and index == len(plan_buttons) - 1
                ):
                    engagement = wait_for_navigation_trainer_engagement(
                        pyboy,
                        render=render,
                        max_frames=NAVIGATION_TRAINER_ENGAGEMENT_WAIT_FRAMES,
                    )
                    if engagement is not None:
                        execution["timeline"].append(
                            {
                                "event": "navigation_interrupted",
                                "reason": engagement["reason"],
                                "inputs": len(trace),
                                "wait_frames": engagement["wait_frames"],
                                "position": engagement.get("position", "unknown"),
                            }
                        )
                        interrupted = True
                    break
            after = snapshot(pyboy)
            save_screenshot(pyboy, after_screenshot_path)
            after_dict = snapshot_to_dict(after)
            result = navigate_within_pewter_region(
                after_dict,
                target=target,
                before_snapshot=before_dict,
                screenshot_path=after_screenshot_path,
            )
            execution["timeline"].append(
                {
                    "event": "critic_result",
                    "status": result.status,
                    "summary": result.summary,
                    "inputs": len(trace),
                }
            )
            if result.status == "succeeded" or interrupted:
                break
            if (
                plan["status"] == "planned_wild_battle"
                and pewter_navigation_snapshot_is_routeable(after_dict)
                and plan_buttons
                and len(trace) < max_inputs
            ):
                position = pewter_snapshot_position(after_dict)
                execution["timeline"].append(
                    {
                        "event": "predicted_wild_battle_not_materialized",
                        "attempt": attempt_index + 1,
                        "position": position.format() if position else "unknown",
                        "inputs": len(trace),
                    }
                )
                execution_state_bytes = pyboy_state_bytes(pyboy)
                continue
            break

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_enter_grass_search_loop(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    patch: str | None = "forest_grass",
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_steps: int = 160,
    max_entry_expansions: int = 80,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "enter_grass_search_loop")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "enter_grass_search_loop",
        "executor": {
            "patch": patch,
            "render": render,
            "emulation_speed": emulation_speed,
            "max_steps": max_steps,
            "max_entry_expansions": max_entry_expansions,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "enter_grass_search_loop",
                "state_in": str(state_in),
                "patch": patch,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }

    initial_result = enter_grass_search_loop(
        before_dict,
        patch=patch,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()
    target_patch = resolve_execution_grass_patch(patch, before_dict)

    if initial_result.status != "succeeded" or target_patch is None:
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    elif before_dict.get("mode") == "battle" and before_dict.get("battle_type_raw") == 1:
        after = before
        result = initial_result
        execution["timeline"].append({"event": "skill_noop", "reason": result.summary})
    else:
        entry_plan = maybe_enter_approved_grass_patch(
            pyboy,
            target_patch=target_patch,
            trace=trace,
            render=render,
            max_entry_expansions=max_entry_expansions,
        )
        execution["entry_plan"] = entry_plan
        execution["timeline"].append(
            {
                "event": "entry_plan_finished",
                "status": entry_plan["status"],
                "summary": entry_plan["summary"],
                "inputs": entry_plan.get("inputs", 0),
            }
        )

        if entry_plan["status"] != "entered":
            after = snapshot(pyboy)
            result = SkillResult(
                skill_id="enter_grass_search_loop",
                status="uncertain",
                summary=str(entry_plan["summary"]),
                evidence=(
                    f"patch={patch}",
                    f"entry_status={entry_plan['status']}",
                    f"inputs={len(trace)}",
                ),
            )
        else:
            search_metadata = run_grass_search_inputs(
                pyboy,
                target_patch=target_patch,
                trace=trace,
                render=render,
                max_steps=max_steps,
            )
            execution["search"] = search_metadata
            execution["timeline"].append(
                {
                    "event": "grass_search_finished",
                    "status": search_metadata["status"],
                    "summary": search_metadata["summary"],
                    "search_steps": search_metadata["search_steps"],
                    "inputs": len(trace),
                }
            )
            after = snapshot(pyboy)
            save_screenshot(pyboy, after_screenshot_path)
            result = enter_grass_search_loop(
                snapshot_to_dict(after),
                before_snapshot=before_dict,
                patch=patch,
                screenshot_path=after_screenshot_path,
            )
            execution["timeline"].append(
                {
                    "event": "critic_result",
                    "status": result.status,
                    "summary": result.summary,
                    "inputs": len(trace),
                }
            )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_use_move(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    requested_move: str | int,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_wait_frames: int = 900,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "use_move")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    working_screenshot_path = run_dir / "battle-route.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "use_move",
        "executor": {
            "requested_move": requested_move,
            "render": render,
            "emulation_speed": emulation_speed,
            "max_wait_frames": max_wait_frames,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "use_move",
                "state_in": str(state_in),
                "requested_move": requested_move,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = use_move(
        before_dict,
        requested_move=requested_move,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        route_status = select_requested_move_from_battle_menu(
            pyboy,
            before_snapshot=before_dict,
            requested_move=requested_move,
            screenshot_path=working_screenshot_path,
            trace=trace,
            render=render,
        )
        execution["timeline"].append(route_status)
        if route_status["status"] != "move_selected":
            after = snapshot(pyboy)
            result = SkillResult(
                skill_id="use_move",
                status="uncertain",
                summary=str(route_status["summary"]),
                evidence=(
                    f"requested_move={requested_move}",
                    f"route_status={route_status['status']}",
                    f"inputs={len(trace)}",
                ),
            )
        else:
            after = wait_for_use_move_outcome(
                pyboy,
                before_snapshot=before_dict,
                requested_move=requested_move,
                screenshot_path=after_screenshot_path,
                trace=trace,
                render=render,
                max_wait_frames=max_wait_frames,
            )
            result = use_move(
                snapshot_to_dict(after),
                before_snapshot=before_dict,
                requested_move=requested_move,
                screenshot_path=after_screenshot_path,
            )
            execution["timeline"].append(
                {
                    "event": "critic_result",
                    "status": result.status,
                    "summary": result.summary,
                }
            )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_run_from_wild_battle(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_wait_frames: int = 900,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "run_from_wild_battle")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    working_screenshot_path = run_dir / "battle-route.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "run_from_wild_battle",
        "executor": {
            "render": render,
            "emulation_speed": emulation_speed,
            "max_wait_frames": max_wait_frames,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "run_from_wild_battle",
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = run_from_wild_battle(before_dict, screenshot_path=before_screenshot_path)
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        route_status = select_run_from_battle_menu(
            pyboy,
            screenshot_path=working_screenshot_path,
            trace=trace,
            render=render,
        )
        execution["timeline"].append(route_status)
        after = wait_for_run_from_wild_battle_outcome(
            pyboy,
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
            trace=trace,
            render=render,
            max_wait_frames=max_wait_frames,
        )
        save_screenshot(pyboy, after_screenshot_path)
        result = run_from_wild_battle(
            snapshot_to_dict(after),
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
        )
        execution["timeline"].append(
            {
                "event": "critic_result",
                "status": result.status,
                "summary": result.summary,
                "inputs": len(trace),
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_switch_party_member(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    target: str | int,
    render: bool = False,
    post_load_settle_frames: int = 60,
    max_wait_frames: int = 900,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "switch_party_member")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    working_screenshot_path = run_dir / "battle-route.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "switch_party_member",
        "executor": {
            "target": target,
            "render": render,
            "emulation_speed": emulation_speed,
            "max_wait_frames": max_wait_frames,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "switch_party_member",
                "state_in": str(state_in),
                "target": target,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = switch_party_member(
        before_dict,
        target=target,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        route_status = select_party_switch_from_battle_menu(
            pyboy,
            before_snapshot=before_dict,
            target=target,
            screenshot_path=working_screenshot_path,
            trace=trace,
            render=render,
        )
        execution["timeline"].append(route_status)
        if route_status["status"] != "switch_selected":
            after = snapshot(pyboy)
            result = SkillResult(
                skill_id="switch_party_member",
                status="uncertain",
                summary=str(route_status["summary"]),
                evidence=(
                    f"target={target}",
                    f"route_status={route_status['status']}",
                    f"inputs={len(trace)}",
                ),
            )
        else:
            after = wait_for_switch_party_outcome(
                pyboy,
                before_snapshot=before_dict,
                target=target,
                screenshot_path=after_screenshot_path,
                trace=trace,
                render=render,
                max_wait_frames=max_wait_frames,
            )
            result = switch_party_member(
                snapshot_to_dict(after),
                before_snapshot=before_dict,
                target=target,
                screenshot_path=after_screenshot_path,
            )
            execution["timeline"].append(
                {
                    "event": "critic_result",
                    "status": result.status,
                    "summary": result.summary,
                }
            )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_overworld_rearrange_party(
    pyboy: object,
    *,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    target: str | int,
    destination_slot: int,
    render: bool = False,
    post_load_settle_frames: int = 60,
    emulation_speed: int = 0,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, "overworld_rearrange_party")
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": "overworld_rearrange_party",
        "executor": {
            "target": target,
            "destination_slot": destination_slot,
            "render": render,
            "emulation_speed": emulation_speed,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": "overworld_rearrange_party",
                "state_in": str(state_in),
                "target": target,
                "destination_slot": destination_slot,
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = overworld_rearrange_party(
        before_dict,
        target=target,
        destination_slot=destination_slot,
        screenshot_path=before_screenshot_path,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": result.status,
                "reason": result.summary,
            }
        )
    elif "noop=true" in initial_result.evidence:
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_noop",
                "status": result.status,
                "reason": result.summary,
            }
        )
    else:
        route_status = select_overworld_party_reorder(
            pyboy,
            before_snapshot=before_dict,
            target=target,
            destination_slot=destination_slot,
            trace=trace,
            render=render,
        )
        execution["timeline"].append(route_status)
        after = snapshot(pyboy)
        save_screenshot(pyboy, after_screenshot_path)
        if route_status["status"] != "reorder_selected":
            result = SkillResult(
                skill_id="overworld_rearrange_party",
                status="uncertain",
                summary=str(route_status["summary"]),
                evidence=(
                    f"target={target}",
                    f"destination_slot={destination_slot}",
                    f"route_status={route_status['status']}",
                    f"inputs={len(trace)}",
                ),
            )
        else:
            result = overworld_rearrange_party(
                snapshot_to_dict(after),
                before_snapshot=before_dict,
                target=target,
                destination_slot=destination_slot,
                screenshot_path=after_screenshot_path,
            )
            execution["timeline"].append(
                {
                    "event": "critic_result",
                    "status": result.status,
                    "summary": result.summary,
                }
            )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_single_button_skill(
    pyboy: object,
    *,
    skill_id: str,
    runner: Callable[..., SkillResult],
    button: str,
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool,
    post_load_settle_frames: int,
    emulation_speed: int,
    runner_kwargs: dict[str, Any] | None = None,
) -> SkillRunArtifact:
    if button not in PRESS_EVENTS:
        raise ValueError(f"Unsupported button {button!r}.")

    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, skill_id)
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"
    kwargs = runner_kwargs or {}

    load_state(pyboy, state_in)
    pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)
    trace: list[ButtonInput] = []

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": skill_id,
        "executor": {
            "button": button,
            "render": render,
            "emulation_speed": emulation_speed,
            **kwargs,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": skill_id,
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = runner(
        before_dict,
        screenshot_path=before_screenshot_path,
        **kwargs,
    )
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": initial_result.status,
                "reason": initial_result.summary,
            }
        )
    else:
        step = ButtonInput(button, hold_frames=8, settle_frames=36)
        trace.append(step)
        run_timed_trace(pyboy, [step], render=render)
        after = snapshot(pyboy)
        save_screenshot(pyboy, after_screenshot_path)
        result = runner(
            snapshot_to_dict(after),
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
            **kwargs,
        )
        execution["timeline"].append(
            {
                "event": "button_sent",
                "button": button,
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


def execute_trace_skill(
    pyboy: object,
    *,
    skill_id: str,
    runner: Callable[..., SkillResult],
    trace: list[ButtonInput],
    state_in: str | Path,
    rom: RomFingerprint,
    run_root: str | Path,
    render: bool,
    post_load_settle_frames: int,
    emulation_speed: int,
    runner_kwargs: dict[str, Any] | None = None,
    state_already_loaded: bool = False,
) -> SkillRunArtifact:
    configure_skill_emulation(pyboy, emulation_speed)
    run_dir = make_run_dir(run_root, skill_id)
    before_state_path = run_dir / "before.state"
    after_state_path = run_dir / "after.state"
    before_screenshot_path = run_dir / "before.png"
    after_screenshot_path = run_dir / "after.png"
    trace_path = run_dir / "trace.json"
    report_path = run_dir / "report.json"
    kwargs = runner_kwargs or {}

    if not state_already_loaded:
        load_state(pyboy, state_in)
        pyboy.tick(post_load_settle_frames, render)
    before = snapshot(pyboy)
    before_dict = snapshot_to_dict(before)
    save_state(pyboy, before_state_path)
    save_screenshot(pyboy, before_screenshot_path)

    execution: dict[str, Any] = {
        "schema": "skill_execution_v1",
        "skill_id": skill_id,
        "executor": {
            "trace_length": len(trace),
            "render": render,
            "emulation_speed": emulation_speed,
            **kwargs,
        },
        "timeline": [
            {
                "event": "skill_call_started",
                "skill_id": skill_id,
                "state_in": str(state_in),
            },
            {
                "event": "initial_snapshot",
                "snapshot_hash": snapshot_hash(before),
                "screenshot_file": str(before_screenshot_path),
            },
        ],
    }
    initial_result = runner(before_dict, screenshot_path=before_screenshot_path, **kwargs)
    execution["initial_result"] = initial_result.to_dict()

    if initial_result.status != "succeeded":
        after = before
        result = initial_result
        executed_trace: list[ButtonInput] = []
        execution["timeline"].append(
            {
                "event": "skill_not_executed",
                "status": initial_result.status,
                "reason": initial_result.summary,
            }
        )
    else:
        executed_trace = list(trace)
        run_timed_trace(pyboy, executed_trace, render=render)
        after = snapshot(pyboy)
        save_screenshot(pyboy, after_screenshot_path)
        result = runner(
            snapshot_to_dict(after),
            before_snapshot=before_dict,
            screenshot_path=after_screenshot_path,
            **kwargs,
        )
        execution["timeline"].append(
            {
                "event": "trace_sent",
                "inputs": len(executed_trace),
                "status": result.status,
                "summary": result.summary,
            }
        )

    save_state(pyboy, after_state_path)
    if not after_screenshot_path.exists():
        save_screenshot(pyboy, after_screenshot_path)
    trace_path.write_text(dump_trace(executed_trace), encoding="utf-8")
    execution["final_result"] = result.to_dict()
    report = skill_run_report(
        rom=rom,
        state_in=state_in,
        before=before,
        after=after,
        result=result,
        trace=executed_trace,
        before_state_path=before_state_path,
        after_state_path=after_state_path,
        before_screenshot_path=before_screenshot_path,
        after_screenshot_path=after_screenshot_path,
        trace_path=trace_path,
        execution=execution,
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return SkillRunArtifact(run_dir=run_dir, report_path=report_path, result=result)


NICKNAME_ROWS: dict[int, tuple[int, ...]] = {
    1: (1, 3, 5, 7, 9, 11, 13, 15, 17),
    2: (1, 3, 5, 7, 9, 11, 13, 15, 17),
    3: (1, 3, 5, 7, 9, 11, 13, 15, 17),
    4: (1, 3, 5, 7, 9, 11, 13, 15, 17),
    5: (1, 3, 5, 7, 9, 11, 13, 15, 17),
}
NICKNAME_ROW_ORDER = (1, 2, 3, 4, 5)
NICKNAME_LETTER_POSITIONS: dict[str, tuple[int, int]] = {
    **{char: (1 + index * 2, 1) for index, char in enumerate("ABCDEFGHI")},
    **{char: (1 + index * 2, 2) for index, char in enumerate("JKLMNOPQR")},
    **{char: (1 + index * 2, 3) for index, char in enumerate("STUVWXYZ")},
}
NICKNAME_END_POSITION = (17, 5)


def nickname_keyboard_trace(pyboy: object, nickname: str) -> list[ButtonInput]:
    current = nickname_cursor_position(pyboy)
    trace: list[ButtonInput] = []
    for char in nickname:
        target = NICKNAME_LETTER_POSITIONS.get(char)
        if target is None:
            raise ValueError(f"Unsupported nickname character {char!r}; v0 supports uppercase A-Z only.")
        route = nickname_route(current, target)
        trace.extend(ButtonInput(button, hold_frames=8, settle_frames=18) for button in route)
        trace.append(ButtonInput("a", hold_frames=8, settle_frames=24))
        current = target
    route = nickname_route(current, NICKNAME_END_POSITION)
    trace.extend(ButtonInput(button, hold_frames=8, settle_frames=18) for button in route)
    trace.append(ButtonInput("a", hold_frames=8, settle_frames=72))
    return trace


def nickname_cursor_position(pyboy: object) -> tuple[int, int]:
    memory = getattr(pyboy, "memory")
    column = int(memory[mm.NAMING_CURSOR_COLUMN])
    row = int(memory[mm.NAMING_CURSOR_ROW])
    current = (column, row)
    if current not in nickname_nodes():
        raise ValueError(f"Unsupported naming cursor position: column={column}, row={row}.")
    return current


def nickname_route(start: tuple[int, int], target: tuple[int, int]) -> list[str]:
    if start == target:
        return []
    nodes = nickname_nodes()
    queue: list[tuple[int, int]] = [start]
    previous: dict[tuple[int, int], tuple[tuple[int, int], str] | None] = {start: None}
    while queue:
        current = queue.pop(0)
        for button, neighbor in nickname_neighbors(current).items():
            if neighbor not in nodes or neighbor in previous:
                continue
            previous[neighbor] = (current, button)
            if neighbor == target:
                return unwind_nickname_route(previous, target)
            queue.append(neighbor)
    raise ValueError(f"No naming keyboard route from {start} to {target}.")


def unwind_nickname_route(
    previous: dict[tuple[int, int], tuple[tuple[int, int], str] | None],
    target: tuple[int, int],
) -> list[str]:
    buttons: list[str] = []
    current = target
    while previous[current] is not None:
        parent, button = previous[current]  # type: ignore[misc]
        buttons.append(button)
        current = parent
    return list(reversed(buttons))


def nickname_neighbors(position: tuple[int, int]) -> dict[str, tuple[int, int]]:
    column, row = position
    row_columns = NICKNAME_ROWS[row]
    index = row_columns.index(column)
    left = row_columns[index - 1] if index > 0 else row_columns[-1]
    right = row_columns[index + 1] if index + 1 < len(row_columns) else row_columns[0]
    row_index = NICKNAME_ROW_ORDER.index(row)
    neighbors = {
        "left": (left, row),
        "right": (right, row),
    }
    if row_index > 0:
        up_row = NICKNAME_ROW_ORDER[row_index - 1]
        neighbors["up"] = (nearest_nickname_column(column, up_row), up_row)
    if row_index + 1 < len(NICKNAME_ROW_ORDER):
        down_row = NICKNAME_ROW_ORDER[row_index + 1]
        neighbors["down"] = (nearest_nickname_column(column, down_row), down_row)
    return neighbors


def nearest_nickname_column(column: int, row: int) -> int:
    columns = NICKNAME_ROWS[row]
    return min(columns, key=lambda item: abs(item - column))


def nickname_nodes() -> set[tuple[int, int]]:
    return {(column, row) for row, columns in NICKNAME_ROWS.items() for column in columns}


def run_recover_to_overworld_inputs(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
    max_inputs: int,
) -> tuple[Any, SkillResult]:
    for _ in range(max_inputs):
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        save_screenshot(pyboy, screenshot_path)
        if current_dict.get("battle_type_raw") not in {None, 0} or current_dict.get("mode") == "battle":
            return current, recover_to_overworld(
                current_dict,
                before_snapshot=before_snapshot,
                screenshot_path=screenshot_path,
            )
        if is_stable_overworld(current_dict):
            return current, recover_to_overworld(
                current_dict,
                before_snapshot=before_snapshot,
                screenshot_path=screenshot_path,
            )

        button = recovery_button_for(current_dict, screenshot_path)
        if button is None:
            return current, SkillResult(
                skill_id="recover_to_overworld",
                status="uncertain",
                summary="Recovery stopped because the current UI did not map to a safe input.",
                evidence=(
                    f"mode={current_dict.get('mode', 'unknown')}",
                    f"battle_type_raw={current_dict.get('battle_type_raw')}",
                    f"inputs={len(trace)}",
                ),
                warnings=tuple(str(item) for item in current_dict.get("warnings", ())),
            )
        step = ButtonInput(button, hold_frames=8, settle_frames=30)
        trace.append(step)
        run_timed_trace(pyboy, [step], render=render)

    final = snapshot(pyboy)
    final_dict = snapshot_to_dict(final)
    save_screenshot(pyboy, screenshot_path)
    if is_stable_overworld(final_dict):
        return final, recover_to_overworld(
            final_dict,
            before_snapshot=before_snapshot,
            screenshot_path=screenshot_path,
        )
    return final, SkillResult(
        skill_id="recover_to_overworld",
        status="failed",
        summary="Recovery input budget was exhausted before reaching stable overworld.",
        evidence=(
            f"mode={final_dict.get('mode', 'unknown')}",
            f"battle_type_raw={final_dict.get('battle_type_raw')}",
            f"inputs={len(trace)}",
        ),
        warnings=tuple(str(item) for item in final_dict.get("warnings", ())),
    )


def is_stable_overworld(snapshot_dict: dict[str, Any]) -> bool:
    return snapshot_dict.get("mode") == "overworld" and snapshot_dict.get("battle_type_raw") == 0


def recovery_button_for(snapshot_dict: dict[str, Any], screenshot_path: Path) -> str | None:
    mode = str(snapshot_dict.get("mode", "unknown"))
    if mode == "dialogue":
        return "a"
    if mode == "menu":
        return "b"
    if mode == "menu_or_dialogue_uncertain":
        return "a" if screenshot_has_dialogue_overlay(screenshot_path) else "b"
    return None


def select_requested_move_from_battle_menu(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    requested_move: str | int,
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
) -> dict[str, Any]:
    try:
        requested = resolve_requested_move(requested_move)
    except ValueError as exc:
        return {"event": "move_route_failed", "status": "unknown_move", "summary": str(exc)}

    active = active_party_member(before_snapshot)
    target = move_slot(active, requested)
    if target is None:
        return {
            "event": "move_route_failed",
            "status": "move_missing",
            "summary": f"Active battler does not know {requested.name}.",
        }

    save_screenshot(pyboy, screenshot_path)
    ui = inspect_battle_ui_screenshot(screenshot_path)
    if ui.kind != "move_menu":
        action_status = recover_to_battle_action_menu_safely(
            pyboy,
            trace=trace,
            screenshot_path=screenshot_path,
            render=render,
        )
        if action_status != "action_menu":
            return {
                "event": "move_route_failed",
                "status": f"recovery_{action_status}",
                "summary": "Could not recover to the battle action menu before selecting Fight.",
            }

        save_screenshot(pyboy, screenshot_path)
        ui = inspect_battle_ui_screenshot(screenshot_path)
        for button in path_to_fight(ui.cursor):
            append_and_run_button(pyboy, trace, button, render=render)
        append_and_run_button(pyboy, trace, "a", render=render, settle_frames=36)
        if not wait_for_battle_ui_kind(pyboy, "move_menu", screenshot_path=screenshot_path, render=render):
            return {
                "event": "move_route_failed",
                "status": "move_menu_not_visible",
                "summary": "Fight was selected, but the move menu did not become visible.",
            }

    save_screenshot(pyboy, screenshot_path)
    ui = inspect_battle_ui_screenshot(screenshot_path)
    current_slot = move_cursor_slot(ui.cursor) or 1
    for button in path_to_battle_move_slot(ui.cursor, target.slot):
        append_and_run_button(pyboy, trace, button, render=render, settle_frames=18)
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=36)
    return {
        "event": "move_selected",
        "status": "move_selected",
        "summary": f"Selected {requested.name} from move slot {target.slot}.",
        "requested_move": requested.name,
        "move_slot": target.slot,
        "inputs": len(trace),
    }


def select_run_from_battle_menu(
    pyboy: object,
    *,
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
) -> dict[str, Any]:
    action_status = recover_to_battle_action_menu_safely(
        pyboy,
        trace=trace,
        screenshot_path=screenshot_path,
        render=render,
    )
    if action_status != "action_menu":
        return {
            "event": "run_route_failed",
            "status": f"recovery_{action_status}",
            "summary": "Could not recover to the battle action menu before selecting Run.",
        }

    save_screenshot(pyboy, screenshot_path)
    ui = inspect_battle_ui_screenshot(screenshot_path)
    for button in path_to_run(ui.cursor):
        append_and_run_button(pyboy, trace, button, render=render)
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=36)
    return {
        "event": "run_selected",
        "status": "run_selected",
        "summary": "Selected Run from the wild battle action menu.",
        "inputs": len(trace),
    }


def select_party_switch_from_battle_menu(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    target: str | int,
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
) -> dict[str, Any]:
    target_member = resolve_target_member(before_snapshot, target)
    if target_member is None:
        return {
            "event": "switch_route_failed",
            "status": "target_missing",
            "summary": f"Target party member {target!r} was not found.",
        }
    target_slot = int(target_member.get("slot", 0))
    active_slot = int(before_snapshot.get("active_party_slot", 1) or 1)
    active = before_snapshot.get("active_party_member") if isinstance(before_snapshot.get("active_party_member"), dict) else {}
    active_hp = int(active.get("hp", 0) or 0)
    save_screenshot(pyboy, screenshot_path)
    ui = inspect_battle_ui_screenshot(screenshot_path)
    if ui.kind == "party_menu":
        current_slot = party_menu_cursor_slot(screenshot_path) or active_slot
        for button in path_between_vertical_slots(current_slot, target_slot):
            append_and_run_button(pyboy, trace, button, render=render, settle_frames=60)
        append_and_run_button(pyboy, trace, "a", render=render, settle_frames=120)
        forced_prompt = forced_party_selection_prompt_visible(screenshot_path)
        if not forced_prompt:
            append_and_run_button(pyboy, trace, "a", render=render, settle_frames=48)
        return {
            "event": "switch_selected",
            "status": "switch_selected",
            "summary": (
                f"Selected forced replacement party slot {target_slot} from visible party prompt."
                if forced_prompt
                else f"Selected party slot {target_slot} from visible party menu."
            ),
            "target_party_slot": target_slot,
            "starting_party_slot": current_slot,
            "forced_replacement": forced_prompt,
            "inputs": len(trace),
        }
    if active_hp <= 0 and target_slot != active_slot and int(target_member.get("hp", 0) or 0) > 0:
        for button in path_between_vertical_slots(active_slot, target_slot):
            append_and_run_button(pyboy, trace, button, render=render, settle_frames=60)
        append_and_run_button(pyboy, trace, "a", render=render, settle_frames=120)
        return {
            "event": "switch_selected",
            "status": "switch_selected",
            "summary": f"Selected forced replacement party slot {target_slot}.",
            "target_party_slot": target_slot,
            "forced_replacement": True,
            "inputs": len(trace),
        }

    action_status = recover_to_battle_action_menu_safely(
        pyboy,
        trace=trace,
        screenshot_path=screenshot_path,
        render=render,
    )
    if action_status != "action_menu":
        return {
            "event": "switch_route_failed",
            "status": f"recovery_{action_status}",
            "summary": "Could not recover to the battle action menu before selecting PKMN.",
        }

    save_screenshot(pyboy, screenshot_path)
    ui = inspect_battle_ui_screenshot(screenshot_path)
    for button in path_to_pkmn(ui.cursor):
        append_and_run_button(pyboy, trace, button, render=render)
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=40)
    if not wait_for_battle_ui_kind(pyboy, "party_menu", screenshot_path=screenshot_path, render=render):
        return {
            "event": "switch_route_failed",
            "status": "party_menu_not_visible",
            "summary": "PKMN was selected, but the party menu did not become visible.",
        }

    for button in path_between_vertical_slots(active_slot, target_slot):
        append_and_run_button(pyboy, trace, button, render=render, settle_frames=18)
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=32)
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=48)
    return {
        "event": "switch_selected",
        "status": "switch_selected",
        "summary": f"Selected party slot {target_slot} for switch.",
        "target_party_slot": target_slot,
        "inputs": len(trace),
    }


def select_overworld_party_reorder(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    target: str | int,
    destination_slot: int,
    trace: list[ButtonInput],
    render: bool,
) -> dict[str, Any]:
    target_member = resolve_target_member(before_snapshot, target)
    if target_member is None:
        return {
            "event": "overworld_reorder_route_failed",
            "status": "target_missing",
            "summary": f"Target party member {target!r} was not found.",
        }
    source_slot = int(target_member.get("slot", 0) or 0)
    if source_slot == destination_slot:
        return {
            "event": "overworld_reorder_route_noop",
            "status": "reorder_selected",
            "summary": f"Party member is already in slot {destination_slot}.",
            "source_slot": source_slot,
            "destination_slot": destination_slot,
            "inputs": len(trace),
        }

    # Gen 1 overworld menu route: Start, Pokemon, member, Switch, destination, back out.
    append_and_run_button(pyboy, trace, "start", render=render, settle_frames=36)
    start_menu_initial = current_menu_item(pyboy)
    select_cyclic_menu_index(
        pyboy,
        trace,
        target_index=1,
        item_count=7,
        render=render,
        settle_frames=18,
    )
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=48)

    party_source_initial = current_menu_item(pyboy)
    select_linear_menu_index(
        pyboy,
        trace,
        target_index=source_slot - 1,
        render=render,
        settle_frames=18,
    )
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=32)
    submenu_initial = current_menu_item(pyboy)
    select_cyclic_menu_index(
        pyboy,
        trace,
        target_index=1,
        item_count=3,
        render=render,
        settle_frames=18,
    )
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=32)

    destination_initial = current_menu_item(pyboy)
    select_linear_menu_index(
        pyboy,
        trace,
        target_index=destination_slot - 1,
        render=render,
        settle_frames=18,
    )
    append_and_run_button(pyboy, trace, "a", render=render, settle_frames=48)
    append_and_run_button(pyboy, trace, "b", render=render, settle_frames=32)
    append_and_run_button(pyboy, trace, "b", render=render, settle_frames=40)
    return {
        "event": "overworld_reorder_selected",
        "status": "reorder_selected",
        "summary": f"Selected party slot {source_slot} and destination slot {destination_slot}.",
        "source_slot": source_slot,
        "destination_slot": destination_slot,
        "start_menu_initial": start_menu_initial,
        "party_source_initial": party_source_initial,
        "submenu_initial": submenu_initial,
        "destination_initial": destination_initial,
        "inputs": len(trace),
    }


def wait_for_use_move_outcome(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    requested_move: str | int,
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
    max_wait_frames: int,
) -> Any:
    last_snapshot = snapshot(pyboy)
    last_dialogue_advance_frame = -10_000
    for frame in range(max_wait_frames):
        pyboy.tick(1, render)
        if frame % 15 != 0:
            continue
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        save_screenshot(pyboy, screenshot_path)
        result = use_move(
            current_dict,
            before_snapshot=before_snapshot,
            requested_move=requested_move,
            screenshot_path=screenshot_path,
        )
        if result.status == "succeeded":
            return current
        if "screenshot=battle_dialogue" in result.evidence and frame - last_dialogue_advance_frame >= 60:
            append_and_run_button(pyboy, trace, "a", render=render, settle_frames=24)
            last_dialogue_advance_frame = frame
        last_snapshot = current
    return last_snapshot


def wait_for_run_from_wild_battle_outcome(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
    max_wait_frames: int,
) -> Any:
    last_snapshot = snapshot(pyboy)
    last_dialogue_advance_frame = -10_000
    for frame in range(max_wait_frames):
        pyboy.tick(1, render)
        if frame % 15 != 0:
            continue
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        save_screenshot(pyboy, screenshot_path)
        ui = inspect_battle_ui_screenshot(screenshot_path)
        result = run_from_wild_battle(
            current_dict,
            before_snapshot=before_snapshot,
            screenshot_path=screenshot_path,
        )
        if result.status == "succeeded":
            return current
        if ui.kind == "dialogue":
            if frame - last_dialogue_advance_frame >= 60:
                append_and_run_button(pyboy, trace, "a", render=render, settle_frames=24)
                last_dialogue_advance_frame = frame
            last_snapshot = current
            continue
        if result.status == "failed":
            return current
        last_snapshot = current
    return last_snapshot


def wait_for_switch_party_outcome(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    target: str | int,
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
    max_wait_frames: int,
) -> Any:
    last_snapshot = snapshot(pyboy)
    last_dialogue_advance_frame = -10_000
    for frame in range(max_wait_frames):
        pyboy.tick(1, render)
        if frame % 15 != 0:
            continue
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        save_screenshot(pyboy, screenshot_path)
        result = switch_party_member(
            current_dict,
            before_snapshot=before_snapshot,
            target=target,
            screenshot_path=screenshot_path,
        )
        if result.status == "succeeded":
            return current
        if "screenshot=battle_dialogue" in result.evidence and frame - last_dialogue_advance_frame >= 60:
            append_and_run_button(pyboy, trace, "a", render=render, settle_frames=24)
            last_dialogue_advance_frame = frame
        last_snapshot = current
    return last_snapshot


def recover_to_battle_action_menu_safely(
    pyboy: object,
    *,
    trace: list[ButtonInput],
    screenshot_path: Path,
    render: bool,
    max_presses: int = 20,
) -> str:
    for _ in range(max_presses):
        save_screenshot(pyboy, screenshot_path)
        ui = inspect_battle_ui_screenshot(screenshot_path)
        if ui.kind == "action_menu":
            return "action_menu"
        if ui.kind in {"item_menu", "move_menu", "party_menu"}:
            append_and_run_button(pyboy, trace, "b", render=render, settle_frames=24)
            continue
        if ui.kind == "dialogue":
            append_and_run_button(pyboy, trace, "a", render=render, settle_frames=36)
            continue
        append_and_run_button(pyboy, trace, "b", render=render, settle_frames=24)
    save_screenshot(pyboy, screenshot_path)
    return inspect_battle_ui_screenshot(screenshot_path).kind


def append_and_run_button(
    pyboy: object,
    trace: list[ButtonInput],
    button: str,
    *,
    render: bool,
    hold_frames: int = 8,
    settle_frames: int = 24,
) -> None:
    step = ButtonInput(button, hold_frames=hold_frames, settle_frames=settle_frames)
    trace.append(step)
    run_timed_trace(pyboy, [step], render=render)


def press_until_inventory_count_increases(
    pyboy: object,
    trace: list[ButtonInput],
    *,
    item_name: str,
    before_count: int,
    screenshot_path: Path,
    render: bool,
    max_presses: int,
) -> int:
    current_count = before_count
    for _ in range(max_presses):
        append_and_run_button(pyboy, trace, "a", render=render, settle_frames=120)
        current = snapshot_to_dict(snapshot(pyboy))
        current_count = inventory_count(current, item_name)
        save_screenshot(pyboy, screenshot_path)
        if current_count > before_count:
            return current_count
    return current_count


def wait_for_pokemart_buy_menu(
    pyboy: object,
    trace: list[ButtonInput],
    *,
    screenshot_path: Path,
    render: bool,
    max_presses: int,
) -> bool:
    for _ in range(max_presses):
        save_screenshot(pyboy, screenshot_path)
        if screenshot_has_pokemart_buy_menu(screenshot_path):
            return True
        append_and_run_button(pyboy, trace, "a", render=render, settle_frames=120)
    save_screenshot(pyboy, screenshot_path)
    return screenshot_has_pokemart_buy_menu(screenshot_path)


def path_to_fight(cursor: BattleActionCursor) -> tuple[str, ...]:
    if cursor == "fight":
        return ()
    if cursor == "item":
        return ("up",)
    if cursor == "pkmn":
        return ("left",)
    if cursor == "run":
        return ("up", "left")
    return ()


def path_to_pkmn(cursor: BattleActionCursor) -> tuple[str, ...]:
    if cursor == "pkmn":
        return ()
    if cursor == "fight":
        return ("right",)
    if cursor == "item":
        return ("up", "right")
    if cursor == "run":
        return ("up",)
    return ("right",)


def path_to_run(cursor: BattleActionCursor) -> tuple[str, ...]:
    if cursor == "run":
        return ()
    if cursor == "item":
        return ("right",)
    if cursor == "pkmn":
        return ("down",)
    if cursor == "fight":
        return ("right", "down")
    return ("right", "down")


def move_cursor_slot(cursor: BattleActionCursor) -> int | None:
    if cursor.startswith("move_"):
        return int(cursor.removeprefix("move_"))
    return None


def path_to_battle_move_slot(cursor: BattleActionCursor, target_slot: int) -> tuple[str, ...]:
    current_slot = move_cursor_slot(cursor) or 1
    return path_between_vertical_slots(current_slot, target_slot)


def path_between_vertical_slots(current_slot: int, target_slot: int) -> tuple[str, ...]:
    if target_slot > current_slot:
        return tuple("down" for _ in range(target_slot - current_slot))
    if target_slot < current_slot:
        return tuple("up" for _ in range(current_slot - target_slot))
    return ()


def current_menu_item(pyboy: object) -> int:
    return int(pyboy.memory[mm.CURRENT_MENU_ITEM])


def select_cyclic_menu_index(
    pyboy: object,
    trace: list[ButtonInput],
    *,
    target_index: int,
    item_count: int,
    render: bool,
    settle_frames: int,
) -> None:
    current = current_menu_item(pyboy)
    for button in cyclic_menu_path(current, target_index, item_count):
        append_and_run_button(pyboy, trace, button, render=render, settle_frames=settle_frames)


def select_linear_menu_index(
    pyboy: object,
    trace: list[ButtonInput],
    *,
    target_index: int,
    render: bool,
    settle_frames: int,
) -> None:
    current = current_menu_item(pyboy)
    for button in path_between_vertical_slots(current, target_index):
        append_and_run_button(pyboy, trace, button, render=render, settle_frames=settle_frames)


def cyclic_menu_path(current_index: int, target_index: int, item_count: int) -> tuple[str, ...]:
    if item_count <= 0:
        return ()
    current = current_index % item_count
    target = target_index % item_count
    down_steps = (target - current) % item_count
    up_steps = (current - target) % item_count
    if down_steps <= up_steps:
        return tuple("down" for _ in range(down_steps))
    return tuple("up" for _ in range(up_steps))


def plan_capsule_a_navigation_path(
    pyboy: object,
    *,
    target_landmark: Landmark,
    max_inputs: int,
    max_segment_expansions: int,
    render: bool,
) -> dict[str, Any]:
    buttons: list[str] = []
    segments: list[dict[str, Any]] = []
    for _ in range(20):
        current = snapshot_to_dict(snapshot(pyboy))
        current_position = snapshot_position(current)
        if at_landmark(current_position, target_landmark):
            return {
                "status": "planned",
                "summary": f"Planned {len(buttons)} inputs to {target_landmark.label}.",
                "buttons": buttons,
                "segments": segments,
            }
        if not navigation_snapshot_is_routeable(current):
            return {
                "status": "not_routeable",
                "summary": "Navigation planning stopped because the current planning state is not stable overworld in the Capsule A region.",
                "buttons": buttons,
                "segments": segments,
                "position": current_position.format() if current_position else "unknown",
                "mode": current.get("mode"),
                "battle_type_raw": current.get("battle_type_raw"),
            }
        if current_position is None:
            return {
                "status": "missing_position",
                "summary": "Navigation planning stopped because the current position could not be read.",
                "buttons": buttons,
                "segments": segments,
            }
        if len(buttons) >= max_inputs:
            return {
                "status": "input_budget_exhausted",
                "summary": "Navigation input budget was exhausted before reaching the target.",
                "buttons": buttons,
                "segments": segments,
            }

        segment_target, transition_button = next_navigation_segment(
            current_position,
            target_landmark.position,
        )
        if segment_target is None:
            return {
                "status": "no_segment_route",
                "summary": "No Capsule A route segment is defined between the current map and target map.",
                "buttons": buttons,
                "segments": segments,
                "position": current_position.format(),
                "target_position": target_landmark.position.format(),
            }

        segment: dict[str, Any] = {
            "from": current_position.format(),
            "segment_target": segment_target.format(),
            "transition_button": transition_button,
        }

        if current_position != segment_target:
            remaining_inputs = max(max_inputs - len(buttons), 0)
            local_plan = find_same_map_navigation_path(
                pyboy,
                target=segment_target,
                max_expansions=max_segment_expansions,
                max_steps=remaining_inputs,
                render=render,
            )
            segment["local_plan"] = {
                "status": local_plan["status"],
                "expansions": local_plan["expansions"],
                "inputs": len(local_plan["buttons"]),
            }
            for diagnostic_key in (
                "seen_positions",
                "halted_branches",
                "nonrouteable_branches",
                "trainer_wait_checks",
                "closest_positions",
            ):
                if diagnostic_key in local_plan:
                    segment["local_plan"][diagnostic_key] = local_plan[diagnostic_key]
            segments.append(segment)
            if local_plan["status"] in {
                "planned_wild_battle",
                "planned_trainer_battle",
                "planned_trainer_engagement",
            }:
                buttons.extend(str(button) for button in local_plan["buttons"])
                if local_plan["status"] == "planned_wild_battle":
                    segment["terminal"] = "wild_battle"
                elif local_plan["status"] == "planned_trainer_battle":
                    segment["terminal"] = "trainer_battle"
                else:
                    segment["terminal"] = "trainer_engagement"
                segment["terminal_position"] = local_plan.get("position", "unknown")
                return {
                    "status": local_plan["status"],
                    "summary": (
                        "Planned navigation to a battle waypoint before "
                        f"reaching {target_landmark.label}."
                    ),
                    "buttons": buttons,
                    "segments": segments,
                    "position": local_plan.get("position", "unknown"),
                }
            if local_plan["status"] != "planned":
                return {
                    "status": "local_plan_failed",
                    "summary": str(local_plan["summary"]),
                    "buttons": buttons,
                    "segments": segments,
                }
            for button in local_plan["buttons"]:
                run_navigation_button(pyboy, str(button), render=render)
            buttons.extend(str(button) for button in local_plan["buttons"])
            current = snapshot_to_dict(snapshot(pyboy))
            current_position = snapshot_position(current)
            if (
                wild_battle_active(current)
                or
                trainer_battle_active(current)
                or trainer_engagement_dialogue_active(current)
            ):
                if wild_battle_active(current):
                    segment["terminal"] = "wild_battle"
                elif trainer_battle_active(current):
                    segment["terminal"] = "trainer_battle"
                else:
                    segment["terminal"] = "trainer_engagement"
                segment["terminal_position"] = current_position.format() if current_position else "unknown"
                return {
                    "status": "planned_wild_battle"
                    if wild_battle_active(current)
                    else "planned_trainer_battle"
                    if trainer_battle_active(current)
                    else "planned_trainer_engagement",
                    "summary": (
                        "Planned navigation to a battle waypoint before "
                        f"reaching {target_landmark.label}."
                    ),
                    "buttons": buttons,
                    "segments": segments,
                    "position": current_position.format() if current_position else "unknown",
                }
            if not navigation_snapshot_is_routeable(current):
                return {
                    "status": "local_plan_left_routeable_state",
                    "summary": "Local route execution during planning left stable overworld.",
                    "buttons": buttons,
                    "segments": segments,
                    "position": current_position.format() if current_position else "unknown",
                }
        else:
            segments.append(segment)

        if transition_button:
            if len(buttons) >= max_inputs:
                return {
                    "status": "input_budget_exhausted",
                    "summary": "Navigation input budget was exhausted before map transition.",
                    "buttons": buttons,
                    "segments": segments,
                }
            transition_after = run_navigation_button(pyboy, transition_button, render=render)
            buttons.append(transition_button)
            segments[-1]["transition_taken"] = True
            if (
                wild_battle_active(transition_after)
                or
                trainer_battle_active(transition_after)
                or trainer_engagement_dialogue_active(transition_after)
            ):
                position = snapshot_position(transition_after)
                if wild_battle_active(transition_after):
                    segments[-1]["terminal"] = "wild_battle"
                elif trainer_battle_active(transition_after):
                    segments[-1]["terminal"] = "trainer_battle"
                else:
                    segments[-1]["terminal"] = "trainer_engagement"
                segments[-1]["terminal_position"] = position.format() if position else "unknown"
                return {
                    "status": "planned_wild_battle"
                    if wild_battle_active(transition_after)
                    else "planned_trainer_battle"
                    if trainer_battle_active(transition_after)
                    else "planned_trainer_engagement",
                    "summary": (
                        "Planned navigation to a battle waypoint before "
                        f"reaching {target_landmark.label}."
                    ),
                    "buttons": buttons,
                    "segments": segments,
                    "position": position.format() if position else "unknown",
                }

    return {
        "status": "segment_budget_exhausted",
        "summary": "Navigation segment budget was exhausted before reaching the target.",
        "buttons": buttons,
        "segments": segments,
    }


def plan_pallet_navigation_path(
    pyboy: object,
    *,
    target_landmark: Landmark,
    max_inputs: int,
    max_segment_expansions: int,
    render: bool,
) -> dict[str, Any]:
    buttons: list[str] = []
    segments: list[dict[str, Any]] = []

    for _ in range(24):
        current = snapshot_to_dict(snapshot(pyboy))
        current_position = pallet_snapshot_position(current)
        if target_landmark.id == "oaks_lab_exit" and current_position is not None:
            post_rival_exit_plan = plan_oak_lab_post_rival_exit_route(
                current_position=current_position,
                remaining_inputs=max_inputs - len(buttons),
            )
            if post_rival_exit_plan is not None:
                return {
                    "status": "planned",
                    "summary": "Planned Oak's Lab post-rival exit route through the center aisle.",
                    "buttons": [*buttons, *post_rival_exit_plan["buttons"]],
                    "segments": [*segments, *post_rival_exit_plan["segments"]],
                }
            story_plan = plan_oak_lab_exit_story_route(
                pyboy,
                current_position=current_position,
                max_segment_expansions=max_segment_expansions,
                remaining_inputs=max_inputs - len(buttons),
                render=render,
            )
            if story_plan is not None:
                story_buttons = [str(button) for button in story_plan["buttons"]]
                return {
                    "status": "planned",
                    "summary": "Planned Oak's Lab exit approach; rival/story progression may interrupt before the door.",
                    "buttons": [*buttons, *story_buttons],
                    "segments": [*segments, *story_plan["segments"]],
                }
        if target_landmark.id == "viridian_mart_counter" and current_position is not None:
            mart_counter_plan = plan_viridian_mart_counter_route(
                current_position=current_position,
                remaining_inputs=max_inputs - len(buttons),
            )
            if mart_counter_plan is not None:
                return {
                    "status": "planned",
                    "summary": "Planned Viridian Mart entrance-to-counter route.",
                    "buttons": [*buttons, *mart_counter_plan["buttons"]],
                    "segments": [*segments, *mart_counter_plan["segments"]],
                }
        if current_position == target_landmark.position:
            return {
                "status": "planned",
                "summary": f"Planned {len(buttons)} inputs to {target_landmark.label}.",
                "buttons": buttons,
                "segments": segments,
            }
        if current_position is None:
            return {
                "status": "missing_position",
                "summary": "Pallet navigation planning stopped because the current position could not be read.",
                "buttons": buttons,
                "segments": segments,
            }
        if current_position.map_id not in PALLET_MAP_IDS:
            return {
                "status": "outside_region",
                "summary": "Pallet navigation planning stopped outside the Pallet map region.",
                "buttons": buttons,
                "segments": segments,
                "position": current_position.format(),
            }
        if current.get("mode") not in {"overworld", "dialogue", "menu_or_dialogue_uncertain"}:
            return {
                "status": "not_routeable",
                "summary": "Pallet navigation planning stopped outside stable overworld/story-dialogue state.",
                "buttons": buttons,
                "segments": segments,
                "position": current_position.format(),
                "mode": current.get("mode"),
            }
        if len(buttons) >= max_inputs:
            return {
                "status": "input_budget_exhausted",
                "summary": "Pallet navigation input budget was exhausted before reaching the target.",
                "buttons": buttons,
                "segments": segments,
            }

        segment_target, transition = next_pallet_navigation_segment(current_position, target_landmark.position)
        if segment_target is None:
            return {
                "status": "no_segment_route",
                "summary": "No Pallet route segment is defined between the current map and target map.",
                "buttons": buttons,
                "segments": segments,
                "position": current_position.format(),
                "target_position": target_landmark.position.format(),
            }

        segment: dict[str, Any] = {
            "from": current_position.format(),
            "segment_target": segment_target.format(),
            "transition_button": transition.button if transition else None,
        }

        if current_position != segment_target:
            remaining_inputs = max(max_inputs - len(buttons), 0)
            local_plan = find_pallet_same_map_navigation_path(
                pyboy,
                target=segment_target,
                max_expansions=max_segment_expansions,
                max_steps=remaining_inputs,
                render=render,
            )
            segment["local_plan"] = {
                "status": local_plan["status"],
                "expansions": local_plan["expansions"],
                "inputs": len(local_plan["buttons"]),
            }
            segments.append(segment)
            if local_plan["status"] in {
                "planned_wild_battle",
                "planned_trainer_battle",
                "planned_trainer_engagement",
            }:
                buttons.extend(str(button) for button in local_plan["buttons"])
                if local_plan["status"] == "planned_wild_battle":
                    segment["terminal"] = "wild_battle"
                elif local_plan["status"] == "planned_trainer_battle":
                    segment["terminal"] = "trainer_battle"
                else:
                    segment["terminal"] = "trainer_engagement"
                segment["terminal_position"] = local_plan.get("position", "unknown")
                return {
                    "status": local_plan["status"],
                    "summary": (
                        "Planned Pallet navigation to a battle waypoint before "
                        f"reaching {target_landmark.label}."
                    ),
                    "buttons": buttons,
                    "segments": segments,
                    "position": local_plan.get("position", "unknown"),
                }
            if local_plan["status"] != "planned":
                return {
                    "status": "local_plan_failed",
                    "summary": str(local_plan["summary"]),
                    "buttons": buttons,
                    "segments": segments,
                }
            for button in local_plan["buttons"]:
                run_navigation_button(pyboy, str(button), render=render)
            buttons.extend(str(button) for button in local_plan["buttons"])
        else:
            segments.append(segment)

        if transition:
            if len(buttons) >= max_inputs:
                return {
                    "status": "input_budget_exhausted",
                    "summary": "Pallet navigation input budget was exhausted before map transition.",
                    "buttons": buttons,
                    "segments": segments,
                }
            run_navigation_button(pyboy, transition.button, render=render)
            buttons.append(transition.button)
            segments[-1]["transition_taken"] = True
            current = snapshot_to_dict(snapshot(pyboy))
            if wild_battle_active(current) or trainer_battle_active(current):
                position = pallet_snapshot_position(current)
                segments[-1]["terminal"] = "wild_battle" if wild_battle_active(current) else "trainer_battle"
                segments[-1]["terminal_position"] = position.format() if position else "unknown"
                return {
                    "status": "planned_wild_battle"
                    if wild_battle_active(current)
                    else "planned_trainer_battle",
                    "summary": (
                        "Planned Pallet navigation to a battle waypoint before "
                        f"reaching {target_landmark.label}."
                    ),
                    "buttons": buttons,
                    "segments": segments,
                    "position": position.format() if position else "unknown",
                }

    return {
        "status": "segment_budget_exhausted",
        "summary": "Pallet navigation segment budget was exhausted before reaching the target.",
        "buttons": buttons,
        "segments": segments,
    }


def plan_pewter_navigation_path(
    pyboy: object,
    *,
    target_landmark: Landmark,
    max_inputs: int,
    max_segment_expansions: int,
    render: bool,
) -> dict[str, Any]:
    buttons: list[str] = []
    segments: list[dict[str, Any]] = []

    for _ in range(24):
        current = snapshot_to_dict(snapshot(pyboy))
        current_position = pewter_snapshot_position(current)
        if current_position == target_landmark.position:
            return {
                "status": "planned",
                "summary": f"Planned {len(buttons)} inputs to {target_landmark.label}.",
                "buttons": buttons,
                "segments": segments,
            }
        if current_position is None:
            return {
                "status": "missing_position",
                "summary": "Pewter navigation planning stopped because the current position could not be read.",
                "buttons": buttons,
                "segments": segments,
            }
        if current_position.map_id not in PEWTER_MAP_IDS:
            return {
                "status": "outside_region",
                "summary": "Pewter navigation planning stopped outside the Pewter map region.",
                "buttons": buttons,
                "segments": segments,
                "position": current_position.format(),
            }
        if not pewter_navigation_snapshot_is_routeable(current):
            return {
                "status": "not_routeable",
                "summary": "Pewter navigation planning stopped outside stable overworld state.",
                "buttons": buttons,
                "segments": segments,
                "position": current_position.format(),
                "mode": current.get("mode"),
                "battle_type_raw": current.get("battle_type_raw"),
            }
        if len(buttons) >= max_inputs:
            return {
                "status": "input_budget_exhausted",
                "summary": "Pewter navigation input budget was exhausted before reaching the target.",
                "buttons": buttons,
                "segments": segments,
            }

        segment_target, transition = next_pewter_navigation_segment(
            current_position,
            target_landmark.position,
        )
        if segment_target is None:
            return {
                "status": "no_segment_route",
                "summary": "No Pewter route segment is defined between the current map and target map.",
                "buttons": buttons,
                "segments": segments,
                "position": current_position.format(),
                "target_position": target_landmark.position.format(),
            }

        segment: dict[str, Any] = {
            "from": current_position.format(),
            "segment_target": segment_target.format(),
            "transition_button": transition.button if transition else None,
        }

        if current_position != segment_target:
            remaining_inputs = max(max_inputs - len(buttons), 0)
            local_plan = find_same_map_navigation_path(
                pyboy,
                target=segment_target,
                max_expansions=max_segment_expansions,
                max_steps=remaining_inputs,
                render=render,
                position_reader=pewter_snapshot_position,
                routeable_checker=pewter_navigation_snapshot_is_routeable,
                summary_label="local Pewter",
            )
            segment["local_plan"] = {
                "status": local_plan["status"],
                "expansions": local_plan["expansions"],
                "inputs": len(local_plan["buttons"]),
            }
            for diagnostic_key in (
                "seen_positions",
                "halted_branches",
                "nonrouteable_branches",
                "trainer_wait_checks",
                "closest_positions",
            ):
                if diagnostic_key in local_plan:
                    segment["local_plan"][diagnostic_key] = local_plan[diagnostic_key]
            segments.append(segment)
            if local_plan["status"] in {
                "planned_wild_battle",
                "planned_trainer_battle",
                "planned_trainer_engagement",
            }:
                buttons.extend(str(button) for button in local_plan["buttons"])
                if local_plan["status"] == "planned_wild_battle":
                    segment["terminal"] = "wild_battle"
                elif local_plan["status"] == "planned_trainer_battle":
                    segment["terminal"] = "trainer_battle"
                else:
                    segment["terminal"] = "trainer_engagement"
                segment["terminal_position"] = local_plan.get("position", "unknown")
                return {
                    "status": local_plan["status"],
                    "summary": (
                        "Planned Pewter navigation to a battle waypoint before "
                        f"reaching {target_landmark.label}."
                    ),
                    "buttons": buttons,
                    "segments": segments,
                    "position": local_plan.get("position", "unknown"),
                }
            if local_plan["status"] != "planned":
                return {
                    "status": "local_plan_failed",
                    "summary": str(local_plan["summary"]),
                    "buttons": buttons,
                    "segments": segments,
                }
            for button in local_plan["buttons"]:
                run_navigation_button(pyboy, str(button), render=render)
            buttons.extend(str(button) for button in local_plan["buttons"])
        else:
            segments.append(segment)

        if transition:
            if len(buttons) >= max_inputs:
                return {
                    "status": "input_budget_exhausted",
                    "summary": "Pewter navigation input budget was exhausted before map transition.",
                    "buttons": buttons,
                    "segments": segments,
                }
            run_navigation_button(pyboy, transition.button, render=render)
            buttons.append(transition.button)
            segments[-1]["transition_taken"] = True
            current = snapshot_to_dict(snapshot(pyboy))
            if wild_battle_active(current) or trainer_battle_active(current) or trainer_engagement_dialogue_active(current):
                position = pewter_snapshot_position(current)
                if wild_battle_active(current):
                    segments[-1]["terminal"] = "wild_battle"
                elif trainer_battle_active(current):
                    segments[-1]["terminal"] = "trainer_battle"
                else:
                    segments[-1]["terminal"] = "trainer_engagement"
                segments[-1]["terminal_position"] = position.format() if position else "unknown"
                return {
                    "status": "planned_wild_battle"
                    if wild_battle_active(current)
                    else "planned_trainer_battle"
                    if trainer_battle_active(current)
                    else "planned_trainer_engagement",
                    "summary": (
                        "Planned Pewter navigation to a battle waypoint before "
                        f"reaching {target_landmark.label}."
                    ),
                    "buttons": buttons,
                    "segments": segments,
                    "position": position.format() if position else "unknown",
                }

    return {
        "status": "segment_budget_exhausted",
        "summary": "Pewter navigation segment budget was exhausted before reaching the target.",
        "buttons": buttons,
        "segments": segments,
    }


def plan_oak_lab_exit_story_route(
    pyboy: object,
    *,
    current_position: Position,
    max_segment_expansions: int,
    remaining_inputs: int,
    render: bool,
) -> dict[str, Any] | None:
    if current_position.map_id != 0x28 or current_position.y > 5:
        return None

    trigger = Position(0x28, 5, 6)
    local_plan = find_pallet_same_map_navigation_path(
        pyboy,
        target=trigger,
        max_expansions=max_segment_expansions,
        max_steps=max(remaining_inputs - 3, 0),
        render=render,
    )
    if local_plan["status"] != "planned":
        return None

    buttons = [*local_plan["buttons"], "down", "down", "down"]
    if len(buttons) > remaining_inputs:
        return None
    return {
        "buttons": buttons,
        "segments": [
            {
                "from": current_position.format(),
                "segment_target": trigger.format(),
                "transition_button": None,
                "story_trigger": "oak_lab_exit_intercept",
                "local_plan": {
                    "status": local_plan["status"],
                    "expansions": local_plan["expansions"],
                    "inputs": len(local_plan["buttons"]),
                },
                "script_inputs": ["down", "down", "down"],
            }
        ],
    }


def plan_oak_lab_post_rival_exit_route(
    *,
    current_position: Position,
    remaining_inputs: int,
) -> dict[str, Any] | None:
    if current_position.map_id != 0x28 or current_position.x != 5:
        return None
    if current_position.y >= 11:
        return None

    extra_unstick_inputs = 2 if current_position.y == 6 else 0
    buttons = ["down"] * (11 - current_position.y + extra_unstick_inputs)
    if not buttons or len(buttons) > remaining_inputs:
        return None
    return {
        "buttons": buttons,
        "segments": [
            {
                "from": current_position.format(),
                "segment_target": "map=0x28,x=5,y=11",
                "transition_button": None,
                "story_trigger": "oak_lab_post_rival_exit",
                "local_plan": {
                    "status": "scripted_post_rival_exit",
                    "inputs": len(buttons),
                },
            }
        ],
    }


def plan_viridian_mart_counter_route(
    *,
    current_position: Position,
    remaining_inputs: int,
) -> dict[str, Any] | None:
    if current_position != Position(0x2A, 3, 7):
        return None
    buttons = ["up", "up", "left"]
    if len(buttons) > remaining_inputs:
        return None
    return {
        "buttons": buttons,
        "segments": [
            {
                "from": current_position.format(),
                "segment_target": "map=0x2A,x=2,y=5",
                "transition_button": None,
                "story_trigger": "viridian_mart_entry_counter_settle",
                "local_plan": {
                    "status": "scripted_mart_counter_route",
                    "inputs": len(buttons),
                },
            }
        ],
    }


def oak_lab_exit_story_progress(
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    *,
    target: str | None,
) -> bool:
    if target != "oaks_lab_exit":
        return False
    before_position = pallet_snapshot_position(before_snapshot)
    after_position = pallet_snapshot_position(after_snapshot)
    if before_position is None or after_position is None:
        return False
    if before_position.map_id != 0x28 or before_position.y > 5:
        return False
    if after_snapshot.get("battle_type_raw") not in {None, 0} or after_snapshot.get("mode") == "battle":
        return True
    return after_position.map_id == 0x28 and after_position == Position(0x28, 5, 6) and after_snapshot.get("mode") in {
        "dialogue",
        "menu",
        "menu_or_dialogue_uncertain",
    }


def oak_lab_exit_completed(
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    *,
    target: str | None,
) -> bool:
    if target != "oaks_lab_exit":
        return False
    before_position = pallet_snapshot_position(before_snapshot)
    after_position = pallet_snapshot_position(after_snapshot)
    if before_position is None or after_position is None:
        return False
    return before_position.map_id == 0x28 and after_position.map_id == 0x00


def next_pallet_navigation_segment(
    current: Position,
    target: Position,
) -> tuple[Position | None, PalletTransition | None]:
    if current.map_id == 0x00 and target == Position(0x00, 10, 1) and current != target:
        return (
            Position(0x00, 10, 2),
            PalletTransition(
                Position(0x00, 10, 2),
                "up",
                0x00,
                Position(0x00, 10, 1),
            ),
        )
    if current.map_id == target.map_id:
        return target, None

    transition = first_transition_on_pallet_route(current.map_id, target.map_id)
    if transition:
        return transition.source, transition
    return None, None


def first_transition_on_pallet_route(source_map: int, destination_map: int) -> PalletTransition | None:
    if source_map == destination_map:
        return None
    queue: list[tuple[int, list[PalletTransition]]] = [(source_map, [])]
    seen = {source_map}
    while queue:
        current_map, route = queue.pop(0)
        for transition in PALLET_TRANSITIONS:
            if transition.source.map_id != current_map:
                continue
            next_map = transition.destination_map
            if next_map in seen:
                continue
            next_route = [*route, transition]
            if next_map == destination_map:
                return next_route[0]
            seen.add(next_map)
            queue.append((next_map, next_route))
    return None


def first_pallet_transition(source_map: int, destination_map: int) -> PalletTransition | None:
    for transition in PALLET_TRANSITIONS:
        if transition.source.map_id == source_map and transition.destination_map == destination_map:
            return transition
    return None


def next_pewter_navigation_segment(
    current: Position,
    target: Position,
) -> tuple[Position | None, PewterTransition | None]:
    if current.map_id == target.map_id:
        return target, None

    transition = first_transition_on_pewter_route(current.map_id, target.map_id)
    if transition:
        return transition.source, transition
    return None, None


def first_transition_on_pewter_route(source_map: int, destination_map: int) -> PewterTransition | None:
    if source_map == destination_map:
        return None
    queue: list[tuple[int, list[PewterTransition]]] = [(source_map, [])]
    seen = {source_map}
    while queue:
        current_map, route = queue.pop(0)
        for transition in PEWTER_TRANSITIONS:
            if transition.source.map_id != current_map:
                continue
            next_map = transition.destination_map
            if next_map in seen:
                continue
            next_route = [*route, transition]
            if next_map == destination_map:
                return next_route[0]
            seen.add(next_map)
            queue.append((next_map, next_route))
    return None


def find_pallet_same_map_navigation_path(
    pyboy: object,
    *,
    target: Position,
    max_expansions: int,
    max_steps: int,
    render: bool,
) -> dict[str, Any]:
    start_state = pyboy_state_bytes(pyboy)
    start_snapshot = snapshot_to_dict(snapshot(pyboy))
    start = pallet_snapshot_position(start_snapshot)
    if start is None:
        return {
            "status": "missing_position",
            "summary": "Cannot plan a local Pallet route without a current position.",
            "buttons": [],
            "expansions": 0,
        }
    if start.map_id != target.map_id:
        return {
            "status": "different_map",
            "summary": "Pallet same-map planner received a target on another map.",
            "buttons": [],
            "expansions": 0,
        }
    if start == target:
        return {
            "status": "planned",
            "summary": "Already at local Pallet segment target.",
            "buttons": [],
            "expansions": 0,
        }

    frontier: list[tuple[int, int, int, tuple[int, int, int], bytes, list[str]]] = []
    counter = 0
    heapq.heappush(
        frontier,
        (
            manhattan_distance(start, target),
            0,
            counter,
            start.as_tuple(),
            start_state,
            [],
        ),
    )
    seen = {start.as_tuple()}
    expansions = 0
    closest_positions: list[tuple[int, int, str]] = []
    wild_battle_candidates: list[dict[str, Any]] = []

    while frontier and expansions < max_expansions:
        _priority, cost, _counter, _position_key, state_bytes, path = heapq.heappop(frontier)
        expansions += 1
        if len(path) >= max_steps:
            continue

        load_pyboy_state_bytes(pyboy, state_bytes)
        current_snapshot = snapshot_to_dict(snapshot(pyboy))
        current_position = pallet_snapshot_position(current_snapshot)
        if current_position is None:
            continue
        closest_positions.append(
            (
                manhattan_distance(current_position, target),
                len(path),
                current_position.format(),
            )
        )
        if current_position == target:
            load_pyboy_state_bytes(pyboy, start_state)
            return {
                "status": "planned",
                "summary": f"Planned {len(path)} local Pallet inputs.",
                "buttons": path,
                "expansions": expansions,
            }

        for button in direction_order_toward(current_position, target):
            load_pyboy_state_bytes(pyboy, state_bytes)
            after = run_navigation_button(pyboy, button, render=render)
            after_position = pallet_snapshot_position(after)
            next_path = [*path, button]
            if wild_battle_active(after):
                record_wild_battle_candidate(
                    wild_battle_candidates,
                    buttons=next_path,
                    position=after_position,
                    target=target,
                    battle_type_raw=after.get("battle_type_raw"),
                )
                continue
            if trainer_battle_active(after):
                load_pyboy_state_bytes(pyboy, start_state)
                return {
                    "status": "planned_trainer_battle",
                    "summary": (
                        "Planned local Pallet inputs to a trainer battle waypoint before "
                        f"reaching {target.format()}."
                    ),
                    "buttons": next_path,
                    "expansions": expansions,
                    "position": after_position.format() if after_position else "unknown",
                    "battle_type_raw": after.get("battle_type_raw"),
                }
            if after_position is None or after_position.map_id != start.map_id:
                continue
            if after_position.map_id not in PALLET_MAP_IDS:
                continue
            if after.get("battle_type_raw") not in {None, 0} or after.get("mode") == "battle":
                continue
            if after.get("mode") not in {"overworld", "dialogue", "menu_or_dialogue_uncertain"}:
                continue
            if after_position == current_position:
                continue
            position_key = after_position.as_tuple()
            if position_key in seen:
                continue
            seen.add(position_key)
            counter += 1
            heapq.heappush(
                frontier,
                (
                    len(next_path) + manhattan_distance(after_position, target),
                    cost + 1,
                    counter,
                    position_key,
                    pyboy_state_bytes(pyboy),
                    next_path,
                ),
            )

    load_pyboy_state_bytes(pyboy, start_state)
    return {
        "status": "not_found",
        "summary": f"Could not find a same-map Pallet path to {target.format()} within {max_expansions} expansions.",
        "buttons": [],
        "expansions": expansions,
        "closest_positions": sorted(closest_positions)[:10],
        "wild_battle_candidates": len(wild_battle_candidates),
    }


def find_same_map_navigation_path(
    pyboy: object,
    *,
    target: Position,
    max_expansions: int,
    max_steps: int,
    render: bool,
    position_reader: Callable[[dict[str, Any]], Position | None] = snapshot_position,
    routeable_checker: Callable[[dict[str, Any]], bool] | None = None,
    summary_label: str = "local",
) -> dict[str, Any]:
    if routeable_checker is None:
        routeable_checker = navigation_snapshot_is_routeable
    start_state = pyboy_state_bytes(pyboy)
    start_snapshot = snapshot_to_dict(snapshot(pyboy))
    start = position_reader(start_snapshot)
    if start is None:
        return {
            "status": "missing_position",
            "summary": f"Cannot plan a {summary_label} route without a current position.",
            "buttons": [],
            "expansions": 0,
        }
    if start.map_id != target.map_id:
        return {
            "status": "different_map",
            "summary": "Same-map planner received a target on another map.",
            "buttons": [],
            "expansions": 0,
        }
    if start == target:
        return {
            "status": "planned",
            "summary": f"Already at {summary_label} segment target.",
            "buttons": [],
            "expansions": 0,
        }

    frontier: list[tuple[int, int, int, tuple[int, int, int], bytes, list[str]]] = []
    counter = 0
    heapq.heappush(
        frontier,
        (
            manhattan_distance(start, target),
            0,
            counter,
            start.as_tuple(),
            start_state,
            [],
        ),
    )
    seen = {start.as_tuple()}
    expansions = 0
    closest_positions: list[tuple[int, int, str]] = []
    halted_branches = 0
    nonrouteable_branches = 0
    trainer_wait_checks = 0
    wild_battle_candidates: list[dict[str, Any]] = []

    while frontier and expansions < max_expansions:
        _priority, cost, _counter, _position_key, state_bytes, path = heapq.heappop(frontier)
        expansions += 1
        if len(path) >= max_steps:
            continue

        load_pyboy_state_bytes(pyboy, state_bytes)
        current_snapshot = snapshot_to_dict(snapshot(pyboy))
        current_position = position_reader(current_snapshot)
        if current_position is None:
            continue
        closest_positions.append(
            (
                manhattan_distance(current_position, target),
                len(path),
                current_position.format(),
            )
        )
        if current_position == target:
            load_pyboy_state_bytes(pyboy, start_state)
            wild_candidate = best_wild_battle_candidate(wild_battle_candidates, target=target)
            if wild_candidate is not None:
                return planned_wild_battle_result(
                    wild_candidate,
                    target=target,
                    expansions=expansions,
                    summary_prefix=f"Planned {summary_label} inputs",
                )
            return {
                "status": "planned",
                "summary": f"Planned {len(path)} {summary_label} inputs.",
                "buttons": path,
                "expansions": expansions,
            }

        added_next_state = False
        for button in direction_order_toward(current_position, target):
            load_pyboy_state_bytes(pyboy, state_bytes)
            after = run_navigation_button(pyboy, button, render=render)
            after_position = position_reader(after)
            next_path = [*path, button]
            if wild_battle_active(after):
                record_wild_battle_candidate(
                    wild_battle_candidates,
                    buttons=next_path,
                    position=after_position,
                    target=target,
                    battle_type_raw=after.get("battle_type_raw"),
                )
                continue
            if trainer_battle_active(after):
                load_pyboy_state_bytes(pyboy, start_state)
                return {
                    "status": "planned_trainer_battle",
                    "summary": (
                        f"Planned {summary_label} inputs to a trainer battle waypoint before "
                        f"reaching {target.format()}."
                    ),
                    "buttons": next_path,
                    "expansions": expansions,
                    "position": after_position.format() if after_position else "unknown",
                    "battle_type_raw": after.get("battle_type_raw"),
                }
            if trainer_engagement_dialogue_active(after):
                load_pyboy_state_bytes(pyboy, start_state)
                return {
                    "status": "planned_trainer_engagement",
                    "summary": (
                        f"Planned {summary_label} inputs to a forced trainer engagement before "
                        f"reaching {target.format()}."
                    ),
                    "buttons": next_path,
                    "expansions": expansions,
                    "position": after_position.format() if after_position else "unknown",
                    "battle_type_raw": after.get("battle_type_raw"),
                }
            if after_position is None or after_position.map_id != start.map_id:
                continue
            if not routeable_checker(after):
                nonrouteable_branches += 1
                continue
            if after_position == current_position:
                item_pickup_branch = try_clear_blocking_item_and_move(
                    pyboy,
                    button=button,
                    start_map_id=start.map_id,
                    blocked_position=current_position,
                    render=render,
                )
                if item_pickup_branch is not None:
                    after = item_pickup_branch["snapshot"]
                    after_position = position_reader(after)
                    next_path = [*path, *item_pickup_branch["buttons"]]
                    if wild_battle_active(after):
                        record_wild_battle_candidate(
                            wild_battle_candidates,
                            buttons=next_path,
                            position=after_position,
                            target=target,
                            battle_type_raw=after.get("battle_type_raw"),
                        )
                        continue
                    if trainer_battle_active(after):
                        load_pyboy_state_bytes(pyboy, start_state)
                        return {
                            "status": "planned_trainer_battle",
                            "summary": (
                                f"Planned {summary_label} inputs to a trainer battle waypoint before "
                                f"reaching {target.format()}."
                            ),
                            "buttons": next_path,
                            "expansions": expansions,
                            "position": after_position.format() if after_position else "unknown",
                            "battle_type_raw": after.get("battle_type_raw"),
                        }
                    if trainer_engagement_dialogue_active(after):
                        load_pyboy_state_bytes(pyboy, start_state)
                        return {
                            "status": "planned_trainer_engagement",
                            "summary": (
                                f"Planned {summary_label} inputs to a forced trainer engagement before "
                                f"reaching {target.format()}."
                            ),
                            "buttons": next_path,
                            "expansions": expansions,
                            "position": after_position.format() if after_position else "unknown",
                            "battle_type_raw": after.get("battle_type_raw"),
                        }
                    if after_position is None or after_position.map_id != start.map_id:
                        continue
                    if not routeable_checker(after):
                        nonrouteable_branches += 1
                        continue
                    position_key = after_position.as_tuple()
                    if position_key in seen:
                        continue
                    seen.add(position_key)
                    if after_position == target:
                        load_pyboy_state_bytes(pyboy, start_state)
                        wild_candidate = best_wild_battle_candidate(wild_battle_candidates, target=target)
                        if wild_candidate is not None:
                            return planned_wild_battle_result(
                                wild_candidate,
                                target=target,
                                expansions=expansions,
                                summary_prefix=f"Planned {summary_label} inputs",
                            )
                        return {
                            "status": "planned",
                            "summary": f"Planned {len(next_path)} {summary_label} inputs.",
                            "buttons": next_path,
                            "expansions": expansions,
                        }
                    added_next_state = True
                    counter += 1
                    next_state = pyboy_state_bytes(pyboy)
                    priority = len(next_path) + manhattan_distance(after_position, target)
                    heapq.heappush(
                        frontier,
                        (
                            priority,
                            len(next_path),
                            counter,
                            position_key,
                            next_state,
                            next_path,
                        ),
                    )
                    continue
                halted_branches += 1
                continue
            trainer_wait_checks += 1
            engagement = wait_for_navigation_trainer_engagement(
                pyboy,
                render=render,
                max_frames=NAVIGATION_POST_MOVE_TRAINER_WAIT_FRAMES,
            )
            if engagement is not None:
                load_pyboy_state_bytes(pyboy, start_state)
                return trainer_engagement_plan_result(
                    engagement,
                    buttons=next_path,
                    expansions=expansions,
                )
            after = snapshot_to_dict(snapshot(pyboy))
            after_position = position_reader(after)
            if after_position is None or after_position.map_id != start.map_id:
                continue
            if not routeable_checker(after):
                nonrouteable_branches += 1
                continue
            position_key = after_position.as_tuple()
            if position_key in seen:
                continue
            seen.add(position_key)
            if after_position == target:
                load_pyboy_state_bytes(pyboy, start_state)
                wild_candidate = best_wild_battle_candidate(wild_battle_candidates, target=target)
                if wild_candidate is not None:
                    return planned_wild_battle_result(
                        wild_candidate,
                        target=target,
                        expansions=expansions,
                        summary_prefix=f"Planned {summary_label} inputs",
                    )
                return {
                    "status": "planned",
                    "summary": f"Planned {len(next_path)} {summary_label} inputs.",
                    "buttons": next_path,
                    "expansions": expansions,
                }
            added_next_state = True
            counter += 1
            next_state = pyboy_state_bytes(pyboy)
            priority = len(next_path) + manhattan_distance(after_position, target)
            heapq.heappush(
                frontier,
                (
                    priority,
                    len(next_path),
                    counter,
                    position_key,
                    next_state,
                    next_path,
                ),
            )

        if not added_next_state:
            load_pyboy_state_bytes(pyboy, state_bytes)
            trainer_wait_checks += 1
            engagement = wait_for_navigation_trainer_engagement(
                pyboy,
                render=render,
                max_frames=NAVIGATION_TRAINER_ENGAGEMENT_WAIT_FRAMES,
            )
            if engagement is not None:
                load_pyboy_state_bytes(pyboy, start_state)
                return trainer_engagement_plan_result(
                    engagement,
                    buttons=path,
                    expansions=expansions,
                )

    load_pyboy_state_bytes(pyboy, start_state)
    return {
        "status": "not_found",
        "summary": f"Could not find a same-map {summary_label} path to {target.format()} within {max_expansions} expansions.",
        "buttons": [],
        "expansions": expansions,
        "seen_positions": len(seen),
        "halted_branches": halted_branches,
        "nonrouteable_branches": nonrouteable_branches,
        "trainer_wait_checks": trainer_wait_checks,
        "wild_battle_candidates": len(wild_battle_candidates),
        "closest_positions": format_closest_navigation_positions(closest_positions),
    }


def try_clear_blocking_item_and_move(
    pyboy: object,
    *,
    button: str,
    start_map_id: int,
    blocked_position: Position,
    render: bool,
) -> dict[str, Any] | None:
    """Try the overworld item-ball pickup flow for a tile blocking navigation."""
    buttons = [button, "a", "a", button]
    for followup in buttons[1:]:
        after = run_navigation_button(pyboy, followup, render=render)
    after_position = snapshot_position(after)
    if wild_battle_active(after) or trainer_battle_active(after):
        return {"buttons": buttons, "snapshot": after}
    if after_position is None or after_position.map_id != start_map_id:
        return None
    if after_position == blocked_position:
        return None
    if not navigation_snapshot_is_routeable(after):
        return None
    return {"buttons": buttons, "snapshot": after}


def format_closest_navigation_positions(positions: list[tuple[int, int, str]]) -> list[dict[str, Any]]:
    closest: list[dict[str, Any]] = []
    seen_positions: set[str] = set()
    for distance, path_length, position in sorted(positions):
        if position in seen_positions:
            continue
        seen_positions.add(position)
        closest.append(
            {
                "position": position,
                "distance": distance,
                "path_length": path_length,
            }
        )
        if len(closest) >= 10:
            break
    return closest


def record_wild_battle_candidate(
    candidates: list[dict[str, Any]],
    *,
    buttons: list[str],
    position: Position | None,
    target: Position,
    battle_type_raw: Any,
) -> None:
    candidates.append(
        {
            "buttons": buttons,
            "position": position.format() if position else "unknown",
            "map_id": position.map_id if position else None,
            "battle_type_raw": battle_type_raw,
            "distance_to_target": manhattan_distance(position, target) if position else 9999,
        }
    )


def best_wild_battle_candidate(
    candidates: list[dict[str, Any]],
    *,
    target: Position | None = None,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    eligible = candidates
    if target is not None:
        # This only filters incidental wild-battle waypoints inside a single local
        # segment. Cross-map travel still happens through the segment planner and
        # explicit transitions; a Route 2 encounter just should not satisfy a
        # Route 22 local grass target.
        eligible = [candidate for candidate in candidates if candidate.get("map_id") == target.map_id]
        if not eligible:
            return None
    return min(
        eligible,
        key=lambda candidate: (
            int(candidate.get("distance_to_target", 9999)),
            len(candidate.get("buttons", [])),
        ),
    )


def planned_wild_battle_result(
    candidate: dict[str, Any],
    *,
    target: Position,
    expansions: int,
    summary_prefix: str,
) -> dict[str, Any]:
    buttons = [str(button) for button in candidate.get("buttons", [])]
    return {
        "status": "planned_wild_battle",
        "summary": f"{summary_prefix} to the wild battle waypoint closest to {target.format()}.",
        "buttons": buttons,
        "expansions": expansions,
        "position": str(candidate.get("position", "unknown")),
        "battle_type_raw": candidate.get("battle_type_raw"),
        "distance_to_target": candidate.get("distance_to_target"),
    }


def resolve_execution_grass_patch(patch: str | None, snapshot_dict: dict[str, Any]) -> GrassPatch | None:
    normalized = "" if patch is None else "_".join(str(patch).strip().lower().replace("-", "_").split())
    if normalized in {"", "auto", "current", "current_map"}:
        position = snapshot_position(snapshot_dict)
        current_patch = approved_grass_patch_for_position(position)
        if current_patch is not None:
            return current_patch
        map_id = position.map_id if position is not None else None
        return approved_grass_patch_for_map(map_id)
    return resolve_grass_patch(patch)


def maybe_enter_approved_grass_patch(
    pyboy: object,
    *,
    target_patch: GrassPatch,
    trace: list[ButtonInput],
    render: bool,
    max_entry_expansions: int,
) -> dict[str, Any]:
    current = snapshot_to_dict(snapshot(pyboy))
    position = snapshot_position(current)
    if current.get("mode") == "battle" and current.get("battle_type_raw") == 1:
        return {
            "status": "entered",
            "summary": "Wild battle already active before grass entry movement.",
            "inputs": 0,
        }
    if position is None:
        return {
            "status": "missing_position",
            "summary": "Could not read current position before entering grass.",
            "inputs": 0,
        }
    if target_patch.contains(position):
        return {
            "status": "entered",
            "summary": "Player is already inside the approved grass patch.",
            "inputs": 0,
            "position": position.format(),
        }
    if not target_patch.is_near(position):
        return {
            "status": "not_near_patch",
            "summary": "Player is not near the approved grass patch.",
            "inputs": 0,
            "position": position.format(),
            "patch_bounds": target_patch.format_bounds(),
        }

    entry_target = target_patch.nearest_position(position)
    entry_plan = find_same_map_navigation_path(
        pyboy,
        target=entry_target,
        max_expansions=max_entry_expansions,
        max_steps=target_patch.near_distance + 2,
        render=render,
    )
    if entry_plan["status"] != "planned":
        return {
            "status": "entry_plan_failed",
            "summary": str(entry_plan["summary"]),
            "inputs": 0,
            "position": position.format(),
            "patch_bounds": target_patch.format_bounds(),
            "entry_plan": entry_plan,
        }

    for button in entry_plan["buttons"]:
        append_and_run_navigation_button(pyboy, trace, str(button), render=render)
        after = snapshot_to_dict(snapshot(pyboy))
        after_position = snapshot_position(after)
        if after.get("mode") == "battle" and after.get("battle_type_raw") == 1:
            return {
                "status": "entered",
                "summary": "Wild battle started while entering the approved grass patch.",
                "inputs": len(entry_plan["buttons"]),
                "position": after_position.format() if after_position else "unknown",
            }
        if after.get("mode") != "overworld" or after.get("battle_type_raw") not in {None, 0}:
            return {
                "status": "entry_interrupted",
                "summary": "Grass entry movement left stable overworld before reaching the patch.",
                "inputs": len(entry_plan["buttons"]),
                "position": after_position.format() if after_position else "unknown",
                "mode": after.get("mode"),
                "battle_type_raw": after.get("battle_type_raw"),
            }

    final = snapshot_to_dict(snapshot(pyboy))
    final_position = snapshot_position(final)
    if target_patch.contains(final_position):
        return {
            "status": "entered",
            "summary": "Entered the approved grass patch.",
            "inputs": len(entry_plan["buttons"]),
            "position": final_position.format() if final_position else "unknown",
        }
    return {
        "status": "entry_did_not_reach_patch",
        "summary": "Entry plan finished outside the approved grass patch.",
        "inputs": len(entry_plan["buttons"]),
        "position": final_position.format() if final_position else "unknown",
    }


def run_grass_search_inputs(
    pyboy: object,
    *,
    target_patch: GrassPatch,
    trace: list[ButtonInput],
    render: bool,
    max_steps: int,
) -> dict[str, Any]:
    direction = "right"
    for search_step in range(1, max_steps + 1):
        current = snapshot_to_dict(snapshot(pyboy))
        current_position = snapshot_position(current)
        if current.get("mode") == "battle" and current.get("battle_type_raw") == 1:
            return {
                "status": "wild_battle_started",
                "summary": "Wild battle started during grass search.",
                "search_steps": search_step - 1,
                "position": current_position.format() if current_position else "unknown",
            }
        if current.get("mode") != "overworld" or current.get("battle_type_raw") not in {None, 0}:
            return {
                "status": "search_interrupted",
                "summary": "Grass search left stable overworld.",
                "search_steps": search_step - 1,
                "mode": current.get("mode"),
                "battle_type_raw": current.get("battle_type_raw"),
                "position": current_position.format() if current_position else "unknown",
            }
        if not target_patch.contains(current_position):
            return {
                "status": "left_approved_patch",
                "summary": "Grass search stopped outside the approved patch.",
                "search_steps": search_step - 1,
                "position": current_position.format() if current_position else "unknown",
                "patch_bounds": target_patch.format_bounds(),
            }

        button, direction = next_grass_search_button(current_position, target_patch, direction)
        append_and_run_navigation_button(pyboy, trace, button, render=render)
        after = snapshot_to_dict(snapshot(pyboy))
        after_position = snapshot_position(after)
        if after.get("mode") == "battle" and after.get("battle_type_raw") == 1:
            return {
                "status": "wild_battle_started",
                "summary": "Wild battle started during grass search.",
                "search_steps": search_step,
                "position": after_position.format() if after_position else "unknown",
            }
        if after_position == current_position:
            direction = "left" if direction == "right" else "right"

    final = snapshot_to_dict(snapshot(pyboy))
    final_position = snapshot_position(final)
    return {
        "status": "search_budget_exhausted",
        "summary": "Grass search input budget ended before a wild battle started.",
        "search_steps": max_steps,
        "position": final_position.format() if final_position else "unknown",
    }


def next_grass_search_button(
    position: Position | None,
    patch: GrassPatch,
    direction: str,
) -> tuple[str, str]:
    if position is None:
        return "right", "right"
    if position.x <= patch.x_min:
        return "right", "right"
    if position.x >= patch.x_max:
        return "left", "left"
    if direction not in {"left", "right"}:
        direction = "right"
    return direction, direction


def next_navigation_segment(
    current: Position,
    target: Position,
) -> tuple[Position | None, str | None]:
    if current.map_id == target.map_id:
        same_map_waypoint = next_same_map_navigation_waypoint(current, target)
        if same_map_waypoint is not None:
            return same_map_waypoint, None
        return target, None

    if current.map_id == MAP_VIRIDIAN_CITY:
        if target.map_id == MAP_VIRIDIAN_POKECENTER:
            return Position(MAP_VIRIDIAN_CITY, 23, 26), "up"
        if target.map_id == MAP_ROUTE_22:
            west_corridor = Position(MAP_VIRIDIAN_CITY, 4, 20)
            west_exit_row = Position(MAP_VIRIDIAN_CITY, 6, 9)
            if current != west_corridor and current.y > 12:
                return west_corridor, None
            if current != west_exit_row and current.x >= 4:
                return west_exit_row, None
            return Position(MAP_VIRIDIAN_CITY, 0, 14), "left"
        return Position(MAP_VIRIDIAN_CITY, 18, 0), "up"

    if current.map_id == MAP_VIRIDIAN_POKECENTER:
        return Position(MAP_VIRIDIAN_POKECENTER, 3, 7), "down"

    if current.map_id == MAP_VIRIDIAN_MART:
        return Position(MAP_VIRIDIAN_MART, 3, 7), "down"

    if current.map_id == MAP_ROUTE_22:
        if target.map_id in {MAP_VIRIDIAN_CITY, MAP_VIRIDIAN_POKECENTER, MAP_VIRIDIAN_MART, MAP_ROUTE_2, MAP_VIRIDIAN_FOREST}:
            return Position(MAP_ROUTE_22, 39, 9), "right"

    if current.map_id == MAP_ROUTE_2:
        if target.map_id in {MAP_VIRIDIAN_CITY, MAP_VIRIDIAN_POKECENTER, MAP_VIRIDIAN_MART, MAP_ROUTE_22}:
            return Position(MAP_ROUTE_2, 8, 71), "down"
        if target.map_id in {MAP_VIRIDIAN_FOREST_SOUTH_GATE, MAP_VIRIDIAN_FOREST} and current.y > 44:
            return Position(MAP_ROUTE_2, 3, 44), "up"
        if target.map_id == MAP_VIRIDIAN_FOREST_NORTH_GATE:
            return Position(MAP_ROUTE_2, 3, 11), "down"
        if target.map_id == MAP_VIRIDIAN_FOREST and target.y <= 8:
            return Position(MAP_ROUTE_2, 3, 11), "down"
        if target.map_id in {MAP_VIRIDIAN_FOREST_SOUTH_GATE, MAP_VIRIDIAN_FOREST}:
            return Position(MAP_ROUTE_2, 3, 44), "up"

    if current.map_id == MAP_VIRIDIAN_FOREST_SOUTH_GATE:
        if target.map_id in {MAP_ROUTE_2, MAP_VIRIDIAN_CITY, MAP_VIRIDIAN_POKECENTER, MAP_VIRIDIAN_MART, MAP_ROUTE_22}:
            return Position(MAP_VIRIDIAN_FOREST_SOUTH_GATE, 4, 7), "down"
        if target.map_id in {MAP_VIRIDIAN_FOREST, MAP_VIRIDIAN_FOREST_NORTH_GATE}:
            return Position(MAP_VIRIDIAN_FOREST_SOUTH_GATE, 5, 1), "up"

    if current.map_id == MAP_VIRIDIAN_FOREST:
        if target.map_id == MAP_VIRIDIAN_FOREST_NORTH_GATE:
            mid_north = Position(MAP_VIRIDIAN_FOREST, 17, 9)
            north_exit = Position(MAP_VIRIDIAN_FOREST, 1, 0)
            if current != mid_north and manhattan_distance(current, north_exit) > manhattan_distance(mid_north, north_exit):
                return mid_north, None
            return Position(MAP_VIRIDIAN_FOREST, 1, 0), "up"
        if target.map_id in {
            MAP_VIRIDIAN_FOREST_SOUTH_GATE,
            MAP_ROUTE_2,
            MAP_VIRIDIAN_CITY,
            MAP_VIRIDIAN_POKECENTER,
            MAP_VIRIDIAN_MART,
            MAP_ROUTE_22,
        }:
            return Position(MAP_VIRIDIAN_FOREST, 17, 47), "down"

    if current.map_id == MAP_VIRIDIAN_FOREST_NORTH_GATE:
        if target.map_id == MAP_VIRIDIAN_FOREST:
            return Position(MAP_VIRIDIAN_FOREST_NORTH_GATE, 4, 7), "down"
        if target.map_id in {MAP_ROUTE_2, MAP_VIRIDIAN_CITY, MAP_VIRIDIAN_POKECENTER, MAP_VIRIDIAN_MART, MAP_ROUTE_22}:
            return Position(MAP_VIRIDIAN_FOREST_NORTH_GATE, 5, 1), "up"

    return None, None


def next_same_map_navigation_waypoint(current: Position, target: Position) -> Position | None:
    if current.map_id == MAP_VIRIDIAN_CITY and target == Position(MAP_VIRIDIAN_CITY, 0, 9):
        west_corridor = Position(MAP_VIRIDIAN_CITY, 4, 20)
        west_exit_row = Position(MAP_VIRIDIAN_CITY, 6, 9)
        if current != west_corridor and current.y > 12:
            return west_corridor
        if current != west_exit_row and current.x >= 4:
            return west_exit_row
    if current.map_id == MAP_VIRIDIAN_FOREST and target.map_id == MAP_VIRIDIAN_FOREST and target.y <= 8:
        mid_north = Position(MAP_VIRIDIAN_FOREST, 17, 9)
        if current != mid_north and manhattan_distance(current, target) > manhattan_distance(mid_north, target):
            return mid_north
    return None


def navigation_snapshot_is_routeable(snapshot_dict: dict[str, Any]) -> bool:
    position = snapshot_position(snapshot_dict)
    return (
        snapshot_dict.get("mode") == "overworld"
        and snapshot_dict.get("battle_type_raw") == 0
        and is_allowed_position(position)
    )


def pewter_navigation_snapshot_is_routeable(snapshot_dict: dict[str, Any]) -> bool:
    position = pewter_snapshot_position(snapshot_dict)
    return (
        snapshot_dict.get("mode") == "overworld"
        and snapshot_dict.get("battle_type_raw") == 0
        and position is not None
        and position.map_id in PEWTER_MAP_IDS
    )


SUPPORTED_POKECENTER_NURSE_TILES = {
    MAP_VIRIDIAN_POKECENTER: Position(MAP_VIRIDIAN_POKECENTER, 3, 3),
    MAP_PEWTER_POKECENTER: Position(MAP_PEWTER_POKECENTER, 3, 3),
}


def run_pokecenter_heal_inputs(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
    max_inputs: int,
) -> Any:
    del before_snapshot
    last_snapshot = snapshot(pyboy)
    blocked_retries = 0
    while len(trace) < max_inputs:
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        save_screenshot(pyboy, screenshot_path)
        visual = inspect_ui_visual_state(screenshot_path)
        position = snapshot_position(current_dict)
        if (
            party_fully_healed(current_dict)
            and current_dict.get("mode") == "overworld"
            and not visual.bottom_text_box
            and not visual.upper_menu
        ):
            pyboy.tick(240, render)
            last_snapshot = snapshot(pyboy)
            save_screenshot(pyboy, screenshot_path)
            settled_visual = inspect_ui_visual_state(screenshot_path)
            settled_dict = snapshot_to_dict(last_snapshot)
            if (
                party_fully_healed(settled_dict)
                and settled_dict.get("mode") == "overworld"
                and not settled_visual.bottom_text_box
                and not settled_visual.upper_menu
            ):
                return last_snapshot
        if current_dict.get("battle_type_raw") not in {None, 0} or current_dict.get("mode") == "battle":
            return current

        nurse_tile = pokecenter_nurse_tile(position)
        if position is not None and nurse_tile is not None and position != nurse_tile:
            button = pokecenter_step_toward_counter(position, nurse_tile)
            step = ButtonInput(button, hold_frames=8, settle_frames=24)
            trace.append(step)
            before_position = position
            run_timed_trace(pyboy, [step], render=render)
            last_snapshot = snapshot(pyboy)
            after_position = snapshot_position(snapshot_to_dict(last_snapshot))
            if after_position == before_position:
                blocked_retries += 1
                pyboy.tick(60, render)
                if blocked_retries >= 4:
                    return last_snapshot
            else:
                blocked_retries = 0
            continue

        button = "a"
        step = ButtonInput(button, hold_frames=8, settle_frames=180)
        trace.append(step)
        run_timed_trace(pyboy, [step], render=render)
        last_snapshot = snapshot(pyboy)
    return last_snapshot


def pokecenter_nurse_tile(position: Position | None) -> Position | None:
    if position is None:
        return None
    return SUPPORTED_POKECENTER_NURSE_TILES.get(position.map_id)


def pokecenter_step_toward_counter(position: Position, nurse_tile: Position) -> str:
    if position.x < nurse_tile.x:
        return "right"
    if position.x > nurse_tile.x:
        return "left"
    if position.y > nurse_tile.y:
        return "up"
    if position.y < nurse_tile.y:
        return "down"
    return "a"


def wait_for_navigation_trainer_engagement(
    pyboy: object,
    *,
    render: bool,
    max_frames: int,
) -> dict[str, Any] | None:
    waited = 0
    while waited < max_frames:
        chunk = min(NAVIGATION_TRAINER_ENGAGEMENT_WAIT_CHUNK, max_frames - waited)
        pyboy.tick(chunk, render)
        waited += chunk
        current = snapshot_to_dict(snapshot(pyboy))
        position = snapshot_position(current)
        if trainer_battle_active(current):
            return {
                "plan_status": "planned_trainer_battle",
                "reason": "trainer_battle_started",
                "summary": "Planned navigation to a trainer battle waypoint.",
                "wait_frames": waited,
                "position": position.format() if position else "unknown",
                "battle_type_raw": current.get("battle_type_raw"),
            }
        if trainer_engagement_dialogue_active(current):
            return {
                "plan_status": "planned_trainer_engagement",
                "reason": "trainer_engagement_dialogue",
                "summary": "Planned navigation to a forced trainer engagement dialogue waypoint.",
                "wait_frames": waited,
                "position": position.format() if position else "unknown",
                "battle_type_raw": current.get("battle_type_raw"),
            }
    return None


def trainer_engagement_plan_result(
    engagement: dict[str, Any],
    *,
    buttons: list[str],
    expansions: int,
) -> dict[str, Any]:
    return {
        "status": engagement["plan_status"],
        "summary": str(engagement["summary"]),
        "buttons": buttons,
        "expansions": expansions,
        "position": engagement.get("position", "unknown"),
        "battle_type_raw": engagement.get("battle_type_raw"),
        "wait_frames": engagement.get("wait_frames"),
    }


def trainer_battle_active(snapshot_dict: dict[str, Any]) -> bool:
    return snapshot_dict.get("mode") == "battle" and snapshot_dict.get("battle_type_raw") == 2


def trainer_engagement_dialogue_active(snapshot_dict: dict[str, Any]) -> bool:
    return snapshot_dict.get("mode") in {"dialogue", "menu_or_dialogue_uncertain"} and snapshot_dict.get(
        "battle_type_raw"
    ) in {None, 0}


def wild_battle_active(snapshot_dict: dict[str, Any]) -> bool:
    return snapshot_dict.get("mode") == "battle" and snapshot_dict.get("battle_type_raw") == 1


def direction_order_toward(current: Position, target: Position) -> tuple[str, ...]:
    return tuple(
        sorted(
            NAVIGATION_DIRECTIONS,
            key=lambda button: manhattan_distance(position_after_button(current, button), target),
        )
    )


def position_after_button(position: Position, button: str) -> Position:
    if button == "up":
        return Position(position.map_id, position.x, position.y - 1)
    if button == "down":
        return Position(position.map_id, position.x, position.y + 1)
    if button == "left":
        return Position(position.map_id, position.x - 1, position.y)
    if button == "right":
        return Position(position.map_id, position.x + 1, position.y)
    return position


def manhattan_distance(left: Position, right: Position) -> int:
    if left.map_id != right.map_id:
        return 10_000
    return abs(left.x - right.x) + abs(left.y - right.y)


def pyboy_state_bytes(pyboy: object) -> bytes:
    buffer = io.BytesIO()
    pyboy.save_state(buffer)
    return buffer.getvalue()


def load_pyboy_state_bytes(pyboy: object, state_bytes: bytes) -> None:
    pyboy.load_state(io.BytesIO(state_bytes))


def run_navigation_button(pyboy: object, button: str, *, render: bool) -> dict[str, Any]:
    step = ButtonInput(
        button,
        hold_frames=NAVIGATION_HOLD_FRAMES,
        settle_frames=NAVIGATION_SETTLE_FRAMES,
    )
    run_timed_trace(pyboy, [step], render=render)
    pyboy.tick(NAVIGATION_EXTRA_SETTLE_FRAMES, render)
    return snapshot_to_dict(snapshot(pyboy))


def append_and_run_navigation_button(
    pyboy: object,
    trace: list[ButtonInput],
    button: str,
    *,
    render: bool,
) -> None:
    step = ButtonInput(
        button,
        hold_frames=NAVIGATION_HOLD_FRAMES,
        settle_frames=NAVIGATION_SETTLE_FRAMES,
    )
    trace.append(step)
    run_timed_trace(pyboy, [step], render=render)
    pyboy.tick(NAVIGATION_EXTRA_SETTLE_FRAMES, render)


def configure_skill_emulation(pyboy: object, emulation_speed: int) -> None:
    if hasattr(pyboy, "set_emulation_speed"):
        pyboy.set_emulation_speed(emulation_speed)


def execute_throw_from_current_battle(
    pyboy: object,
    *,
    rom_path: str | Path,
    run_dir: Path,
    before_snapshot: dict[str, Any],
    render: bool,
    executor: str,
    battle_menu_policy: str | Path | None,
    max_steps: int,
) -> ThrowExecutionArtifact:
    if executor == "scripted":
        return execute_scripted_throw_from_current_battle(
            pyboy,
            run_dir=run_dir,
            before_snapshot=before_snapshot,
            render=render,
        )
    if executor in {"battle-menu-controller", "battle-menu-bc"}:
        return execute_battle_menu_throw_option(
            pyboy,
            rom_path=rom_path,
            run_dir=run_dir,
            render=render,
            executor=executor,
            battle_menu_policy=battle_menu_policy,
            max_steps=max_steps,
        )
    raise ValueError(
        "throw_executor must be one of: scripted, battle-menu-controller, battle-menu-bc"
    )


def execute_scripted_throw_from_current_battle(
    pyboy: object,
    *,
    run_dir: Path,
    before_snapshot: dict[str, Any],
    render: bool,
) -> ThrowExecutionArtifact:
    trace: list[ButtonInput] = []
    recovery_status = recover_to_battle_action_menu(
        pyboy,
        trace=trace,
        screenshot_path=run_dir / "recovery.png",
        render=render,
    )
    if recovery_status != "action_menu":
        metadata = {
            "schema": "throw_execution_v1",
            "executor": "scripted",
            "status": "recovery_failed",
            "summary": "Could not recover to the battle action menu before throwing a ball.",
            "recovery_status": recovery_status,
            "trace": json.loads(dump_trace(trace)),
        }
        write_throw_execution_metadata(run_dir, metadata)
        return ThrowExecutionArtifact(
            status="recovery_failed",
            summary=metadata["summary"],
            trace=trace,
            metadata=metadata,
        )

    move_to_item_and_use(
        pyboy,
        trace=trace,
        snapshot_dict=before_snapshot,
        screenshot_path=run_dir / "menu.png",
        render=render,
    )
    metadata = {
        "schema": "throw_execution_v1",
        "executor": "scripted",
        "status": "throw_sequence_sent",
        "summary": "Scripted menu inputs were sent; outcome must be verified by the critic.",
        "recovery_status": recovery_status,
        "trace": json.loads(dump_trace(trace)),
    }
    write_throw_execution_metadata(run_dir, metadata)
    return ThrowExecutionArtifact(
        status="throw_initiated",
        summary=metadata["summary"],
        trace=trace,
        metadata=metadata,
    )


def execute_battle_menu_throw_option(
    pyboy: object,
    *,
    rom_path: str | Path,
    run_dir: Path,
    render: bool,
    executor: str,
    battle_menu_policy: str | Path | None,
    max_steps: int,
) -> ThrowExecutionArtifact:
    from pokemon_player.battle_menu_env import (
        ACTION_NAMES,
        BattleMenuEnvConfig,
        BattleMenuThrowEnv,
        expert_action_for,
        valid_action_mask_for,
    )

    bc_model = None
    if executor == "battle-menu-bc":
        if battle_menu_policy is None:
            raise ValueError("battle-menu-bc requires --battle-menu-policy")
        from pokemon_player.battle_menu_bc import load_policy

        bc_model, _checkpoint = load_policy(battle_menu_policy)

    env = BattleMenuThrowEnv(
        BattleMenuEnvConfig(
            rom_path=Path(rom_path),
            state_paths=(),
            window="SDL2",
            render=render,
            max_steps=max_steps,
            screenshot_root=run_dir / "throw-option-screens",
        ),
        pyboy=pyboy,
    )
    reset_trace: list[ButtonInput] = []
    recovery_status = recover_to_battle_action_menu(
        pyboy,
        trace=reset_trace,
        screenshot_path=run_dir / "throw-menu-recovery.png",
        render=render,
        max_presses=20,
    )
    if recovery_status != "action_menu":
        metadata = {
            "schema": "throw_execution_v1",
            "executor": executor,
            "status": "recovery_failed",
            "summary": "Could not reset to the battle action menu before throwing a ball.",
            "recovery_status": recovery_status,
            "throw_initiated": False,
            "button_trace": json.loads(dump_trace(reset_trace)),
            "battle_menu_policy": str(battle_menu_policy) if battle_menu_policy else None,
        }
        write_throw_execution_metadata(run_dir, metadata)
        return ThrowExecutionArtifact(
            status="recovery_failed",
            summary=str(metadata["summary"]),
            trace=reset_trace,
            metadata=metadata,
        )
    obs, initial_info = env.begin_current_state()
    terminated = False
    truncated = False
    total_reward = 0.0
    last_info: dict[str, Any] = {}
    trace: list[ButtonInput] = [*reset_trace]
    raw_invalid_predictions = 0

    while not (terminated or truncated):
        facts = env.previous_facts
        if facts is None:
            break
        if executor == "battle-menu-bc":
            from pokemon_player.battle_menu_bc import predict_action

            mask = valid_action_mask_for(
                facts,
                item_menu_steps=env._item_menu_steps,
                in_item_flow=env._in_item_flow,
            )
            raw_action = predict_action(bc_model, obs, deterministic=True)
            raw_invalid_predictions += int(not bool(mask[raw_action]))
            action = predict_action(
                bc_model,
                obs,
                valid_mask=mask,
                deterministic=True,
            )
        else:
            action = ACTION_NAMES.index(
                expert_action_for(
                    facts,
                    item_menu_steps=env._item_menu_steps,
                    in_item_flow=env._in_item_flow,
                )
            )
        obs, reward, terminated, truncated, last_info = env.step(int(action))
        total_reward += reward
        trace.append(
            ButtonInput(
                ACTION_NAMES[int(action)],
                hold_frames=env.config.release_frame,
                settle_frames=max(env.config.action_frames - env.config.release_frame, 0),
            )
        )

    reason = last_info.get("terminated_reason") or ("truncated" if truncated else "unknown")
    throw_initiated = bool(last_info.get("throw_initiated") or env._throw_initiated)
    status = "throw_initiated" if throw_initiated else str(reason)
    final_facts = env.previous_facts.to_dict() if env.previous_facts else None
    if final_facts is not None:
        final_facts["throw_initiated"] = throw_initiated
    metadata = {
        "schema": "throw_execution_v1",
        "executor": executor,
        "status": status,
        "summary": (
            "Battle-menu option initiated a ball throw."
            if throw_initiated
            else "Battle-menu option stopped before initiating a ball throw."
        ),
        "terminated": terminated,
        "truncated": truncated,
        "terminated_reason": reason,
        "throw_initiated": throw_initiated,
        "total_reward": total_reward,
        "steps": len(env.trace),
        "recovery_status": recovery_status,
        "recovery_trace": json.loads(dump_trace(reset_trace)),
        "initial_facts": initial_info.get("facts"),
        "final_facts": final_facts,
        "option_trace": env.trace,
        "button_trace": json.loads(dump_trace(trace)),
        "raw_invalid_predictions": raw_invalid_predictions,
        "battle_menu_policy": str(battle_menu_policy) if battle_menu_policy else None,
    }
    write_throw_execution_metadata(run_dir, metadata)
    return ThrowExecutionArtifact(
        status=status,
        summary=str(metadata["summary"]),
        trace=trace,
        metadata=metadata,
    )


def write_throw_execution_metadata(run_dir: Path, metadata: dict[str, Any]) -> None:
    (run_dir / "throw_execution.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def classify_attempt_catch_failure(
    result: SkillResult,
    *,
    execution: dict[str, Any],
) -> dict[str, str]:
    if result.status in {"succeeded", "failed"}:
        return {
            "category": "resolved_skill_outcome",
            "owner_phase": "none",
            "reason": "The skill critic produced a terminal catch outcome.",
        }
    if result.status == "blocked":
        return {
            "category": "blocked_prerequisite",
            "owner_phase": "scenario_or_director",
            "reason": result.summary,
        }

    throw_execution = execution.get("throw_execution")
    attempts = execution.get("attempts")
    if not throw_execution and isinstance(attempts, list) and attempts:
        throw_execution = attempts[-1].get("throw_execution")

    if isinstance(throw_execution, dict) and not throw_execution.get("throw_initiated"):
        status = str(throw_execution.get("status", "unknown"))
        owner_phase = "recovery" if "recovery" in status else "executor"
        if throw_execution.get("executor") == "battle-menu-bc":
            owner_phase = "learned_option"
        return {
            "category": "throw_executor_failed",
            "owner_phase": owner_phase,
            "reason": str(throw_execution.get("summary", result.summary)),
        }

    if "precondition" in result.summary.lower():
        return {
            "category": "precondition_uncertain",
            "owner_phase": "state",
            "reason": result.summary,
        }

    return {
        "category": "outcome_uncertain",
        "owner_phase": "critic",
        "reason": result.summary,
    }


def attempt_catch_throw_trace() -> list[ButtonInput]:
    return [
        ButtonInput("a", hold_frames=8, settle_frames=16),
        ButtonInput("a", hold_frames=8, settle_frames=16),
    ]


def run_timed_trace(pyboy: object, trace: list[ButtonInput], *, render: bool) -> None:
    # PyBoy's input queue is not reliably consumed from loaded states when ticks
    # are fully unrendered. Rendering ticks still works with the null window.
    tick_render = True
    for step in trace:
        send_window_event(pyboy, PRESS_EVENTS[step.button])
        pyboy.tick(step.hold_frames, tick_render)
        send_window_event(pyboy, RELEASE_EVENTS[step.button])
        if step.settle_frames > 1:
            pyboy.tick(step.settle_frames - 1, tick_render)
        pyboy.tick(1, tick_render if render else True)


def choose_starter_trace(starter: str, *, nickname: str | None) -> list[ButtonInput]:
    # From Oak's "Which POKEMON do you want?" prompt, B returns to the
    # ball-selection surface. The player can then stand below the requested
    # ball, face up, confirm the starter, and decline the nickname prompt.
    route_to_ball = {
        "charmander": ("b", "down", "right", "up"),
        "squirtle": ("b", "down", "right", "right", "up"),
        "bulbasaur": ("b", "down", "right", "right", "right", "up"),
    }[starter]
    buttons = [
        *route_to_ball,
        *("a",) * 13,
    ]
    if nickname:
        buttons.append("a")
    else:
        buttons.extend(["down", "a", *(("a",) * 5)])
    return [ButtonInput(button, hold_frames=8, settle_frames=72) for button in buttons]


def normalize_optional_nickname(nickname: str | None) -> str | None:
    if nickname is None:
        return None
    target = nickname.strip().upper()
    if not target:
        return None
    if not SUPPORTED_NICKNAME.fullmatch(target):
        raise ValueError("choose_starter nickname v0 supports A-Z nicknames from 1 to 10 characters.")
    return target


def wait_for_starter_party_species(
    pyboy: object,
    *,
    expected_species: str,
    max_wait_frames: int,
    render: bool,
) -> Any:
    last = snapshot(pyboy)
    for frame in range(max_wait_frames):
        pyboy.tick(1, render)
        if frame % 15 != 0:
            continue
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        party = current_dict.get("party")
        if isinstance(party, list):
            for member in party:
                if isinstance(member, dict) and member.get("species_name") == expected_species:
                    return current
        last = current
    return last


def wait_for_party_nickname(
    pyboy: object,
    *,
    nickname: str,
    max_wait_frames: int,
    render: bool,
) -> Any:
    last = snapshot(pyboy)
    for frame in range(max_wait_frames):
        pyboy.tick(1, render)
        if frame % 15 != 0:
            continue
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        party = current_dict.get("party")
        if isinstance(party, list):
            for member in party:
                if isinstance(member, dict) and str(member.get("nickname", "")).upper() == nickname:
                    return current
        last = current
    return last


def send_window_event(pyboy: object, event_name: str) -> None:
    from pyboy.utils import WindowEvent

    pyboy.send_input(getattr(WindowEvent, event_name))


def recover_to_battle_action_menu(
    pyboy: object,
    *,
    trace: list[ButtonInput],
    screenshot_path: Path,
    render: bool,
    max_presses: int = 20,
) -> str:
    for _ in range(max_presses):
        save_screenshot(pyboy, screenshot_path)
        ui = inspect_battle_ui_screenshot(screenshot_path)
        if ui.kind == "action_menu":
            return "action_menu"
        if ui.kind in {"item_menu", "move_menu", "party_menu"}:
            step = ButtonInput("b", hold_frames=8, settle_frames=24)
        else:
            step = ButtonInput("a", hold_frames=8, settle_frames=36)
        trace.append(step)
        run_timed_trace(pyboy, [step], render=render)
    save_screenshot(pyboy, screenshot_path)
    return inspect_battle_ui_screenshot(screenshot_path).kind


def run_advance_battle_dialogue_inputs(
    pyboy: object,
    *,
    trace: list[ButtonInput],
    screenshot_path: Path,
    render: bool,
    max_inputs: int,
) -> Any:
    last_snapshot = snapshot(pyboy)
    for _ in range(max_inputs):
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        save_screenshot(pyboy, screenshot_path)
        ui = inspect_battle_ui_screenshot(screenshot_path)
        if current_dict.get("mode") != "battle" or current_dict.get("battle_type_raw") in {None, 0}:
            return current
        if ui.kind == "action_menu":
            return current
        if ui.kind in {"item_menu", "move_menu", "party_menu"}:
            return current
        if ui.kind == "unknown":
            pyboy.tick(60, render)
            last_snapshot = snapshot(pyboy)
            continue
        step = ButtonInput("a", hold_frames=8, settle_frames=36)
        trace.append(step)
        run_timed_trace(pyboy, [step], render=render)
        last_snapshot = snapshot(pyboy)
    return last_snapshot


def move_to_item_and_use(
    pyboy: object,
    *,
    trace: list[ButtonInput],
    snapshot_dict: dict[str, Any],
    screenshot_path: Path,
    render: bool,
) -> None:
    save_screenshot(pyboy, screenshot_path)
    ui = inspect_battle_ui_screenshot(screenshot_path)
    for button in path_to_item(ui.cursor):
        step = ButtonInput(button, hold_frames=8, settle_frames=24)
        trace.append(step)
        run_timed_trace(pyboy, [step], render=render)
    open_item = ButtonInput("a", hold_frames=8, settle_frames=36)
    trace.append(open_item)
    run_timed_trace(pyboy, [open_item], render=render)
    wait_for_battle_ui_kind(pyboy, "item_menu", screenshot_path=screenshot_path, render=render)
    target_index = best_ball_inventory_index(snapshot_dict)
    inventory_slots = len(snapshot_dict.get("inventory", []))
    current_index = current_menu_item(pyboy)
    item_steps = [
        ButtonInput(button, hold_frames=8, settle_frames=18)
        for button in bag_item_cursor_path(
            current_index=current_index,
            target_index=target_index,
            inventory_slots=inventory_slots,
        )
    ]
    item_steps.extend(attempt_catch_throw_trace())
    use_steps = item_steps
    trace.extend(use_steps)
    run_timed_trace(pyboy, use_steps, render=render)


def path_to_item(cursor: BattleActionCursor) -> tuple[str, ...]:
    if cursor == "item":
        return ()
    if cursor == "fight":
        return ("down",)
    if cursor == "pkmn":
        return ("down", "left")
    if cursor == "run":
        return ("left",)
    return ("down",)


def best_ball_inventory_index(snapshot_dict: dict[str, Any]) -> int:
    ball_priority = {0x01: 0, 0x02: 1, 0x03: 2, 0x04: 3}
    candidates: list[tuple[int, int]] = []
    for index, item in enumerate(snapshot_dict.get("inventory", [])):
        if not isinstance(item, dict):
            continue
        item_id = int(item.get("item_id", 0))
        quantity = int(item.get("quantity", 0))
        if item_id in ball_priority and quantity > 0:
            candidates.append((ball_priority[item_id], index))
    if not candidates:
        return 0
    return min(candidates)[1]


def bag_item_cursor_path(
    *,
    current_index: int,
    target_index: int,
    inventory_slots: int,
) -> tuple[str, ...]:
    # Battle bag menus include a Cancel row after the last item. Treating that
    # row as part of the cycle lets us recover from a remembered cursor below
    # the target item without walking blindly into invalid item use.
    return cyclic_menu_path(current_index, target_index, max(inventory_slots + 1, 1))


def wait_for_battle_ui_kind(
    pyboy: object,
    kind: str,
    *,
    screenshot_path: Path,
    render: bool,
    max_frames: int = 180,
) -> bool:
    for _ in range(max_frames):
        pyboy.tick(1, render)
        save_screenshot(pyboy, screenshot_path)
        if inspect_battle_ui_screenshot(screenshot_path).kind == kind:
            return True
    return False


def wait_for_attempt_catch_outcome(
    pyboy: object,
    *,
    before_snapshot: dict[str, Any],
    screenshot_path: Path,
    trace: list[ButtonInput],
    render: bool,
    max_wait_frames: int,
) -> Any:
    before_balls = poke_ball_count(before_snapshot)
    last_snapshot = snapshot(pyboy)
    last_dialogue_advance_frame = -10_000
    for frame in range(max_wait_frames):
        pyboy.tick(1, render)
        if frame % 15 != 0:
            continue
        current = snapshot(pyboy)
        current_dict = snapshot_to_dict(current)
        save_screenshot(pyboy, screenshot_path)
        result = attempt_catch(
            current_dict,
            before_snapshot=before_snapshot,
            screenshot_path=screenshot_path,
        )
        if result.status in {"succeeded", "failed"} and poke_ball_count(current_dict) < before_balls:
            return current
        if "screenshot=throw_dialogue" in result.evidence:
            if frame - last_dialogue_advance_frame >= 60:
                advance = ButtonInput("a", hold_frames=8, settle_frames=24)
                trace.append(advance)
                run_timed_trace(pyboy, [advance], render=render)
                last_dialogue_advance_frame = frame
                current = snapshot(pyboy)
                current_dict = snapshot_to_dict(current)
            if result.status in {"succeeded", "failed"} and poke_ball_count(current_dict) < before_balls:
                return current
        last_snapshot = current
    return last_snapshot


def make_run_dir(run_root: str | Path, skill_id: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(run_root) / skill_id / stamp
    suffix = 1
    while run_dir.exists():
        run_dir = Path(run_root) / skill_id / f"{stamp}-{suffix:02d}"
        suffix += 1
    run_dir.mkdir(parents=True)
    return run_dir


def skill_run_report(
    *,
    rom: RomFingerprint,
    state_in: str | Path,
    before: Any,
    after: Any,
    result: SkillResult,
    trace: list[ButtonInput],
    before_state_path: Path,
    after_state_path: Path,
    before_screenshot_path: Path,
    after_screenshot_path: Path,
    trace_path: Path,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "schema": "skill_run_report_v1",
        "skill_id": result.skill_id,
        "created_utc": datetime.now(UTC).isoformat(),
        "state_in": str(state_in),
        "rom": {
            "title": rom.title,
            "path": str(rom.path),
            "sha256": rom.sha256,
            "md5": rom.md5,
            "size_bytes": rom.size_bytes,
        },
        "result": result.to_dict(),
        "trace_file": str(trace_path),
        "trace": json.loads(dump_trace(trace)),
        "before_state_file": str(before_state_path),
        "after_state_file": str(after_state_path),
        "before_screenshot_file": str(before_screenshot_path),
        "after_screenshot_file": str(after_screenshot_path),
        "before_snapshot_hash": snapshot_hash(before),
        "after_snapshot_hash": snapshot_hash(after),
        "before_snapshot": snapshot_to_dict(before),
        "after_snapshot": snapshot_to_dict(after),
    }
    if execution is not None:
        report["execution"] = execution
        report["failure_classification"] = execution.get("failure_classification")
    return report
