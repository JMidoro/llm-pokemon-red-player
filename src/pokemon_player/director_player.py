from __future__ import annotations

import argparse
import json
import shutil
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from urllib.parse import parse_qs, urlparse

from pokemon_player.battle_ui import inspect_battle_ui_screenshot
from pokemon_player.capsule_a_navigation import (
    LANDMARKS as CAPSULE_A_LANDMARKS,
    approved_grass_patch_for_position,
    at_landmark,
    is_allowed_position,
    resolve_grass_patch,
    snapshot_position,
)
from pokemon_player.pyboy_lab import ButtonInput, load_state, open_emulator, save_screenshot, save_state, snapshot
from pokemon_player.rom import RomFingerprint, fingerprint_rom
from pokemon_player.skill_execution import (
    SkillRunArtifact,
    execute_advance_battle_dialogue,
    execute_advance_dialogue,
    execute_attempt_catch,
    execute_choose_starter,
    execute_close_menu_or_cancel,
    execute_complete_prologue,
    execute_enter_grass_search_loop,
    execute_enter_nickname_text,
    execute_handle_nickname_prompt,
    execute_handle_move_learning_prompt,
    execute_handle_trainer_switch_prompt,
    execute_heal_at_pokecenter,
    execute_navigate_within_pallet_region,
    execute_navigate_within_pewter_region,
    execute_navigate_within_viridian_forest_region,
    execute_overworld_rearrange_party,
    execute_purchase_pokemart_item,
    execute_recover_to_overworld,
    execute_resolve_battle_outcome_dialogue_bundle,
    execute_run_from_wild_battle,
    execute_switch_party_member,
    execute_talk_to_npc,
    execute_use_move,
    run_timed_trace,
)
from pokemon_player.skills.advance_battle_dialogue import advance_battle_dialogue
from pokemon_player.skills.advance_dialogue import advance_dialogue
from pokemon_player.skills.attempt_catch import attempt_catch, poke_ball_count
from pokemon_player.skills.choose_starter import choose_starter
from pokemon_player.skills.close_menu_or_cancel import close_menu_or_cancel
from pokemon_player.skills.complete_prologue import complete_prologue
from pokemon_player.skills.enter_grass_search_loop import enter_grass_search_loop
from pokemon_player.skills.enter_nickname_text import enter_nickname_text
from pokemon_player.skills.handle_nickname_prompt import (
    NicknameChoice,
    handle_nickname_prompt,
    screenshot_has_nickname_intro_dialogue,
    screenshot_has_naming_screen,
    screenshot_has_nickname_prompt,
)
from pokemon_player.skills.handle_move_learning_prompt import (
    MoveLearningChoice,
    handle_move_learning_prompt,
    move_options as move_learning_options,
    screenshot_has_move_learning_prompt,
)
from pokemon_player.skills.handle_trainer_switch_prompt import (
    TrainerSwitchChoice,
    handle_trainer_switch_prompt,
    screenshot_has_trainer_switch_prompt,
)
from pokemon_player.skills.heal_at_pokecenter import heal_at_pokecenter
from pokemon_player.skills.navigate_within_viridian_forest_region import (
    navigate_within_viridian_forest_region,
)
from pokemon_player.skills.navigate_within_pallet_region import navigate_within_pallet_region
from pokemon_player.skills.navigate_within_pewter_region import navigate_within_pewter_region
from pokemon_player.pallet_navigation import (
    default_navigation_target as default_pallet_navigation_target,
    target_options_for_current_map as pallet_target_options_for_current_map,
)
from pokemon_player.pewter_navigation import (
    LANDMARKS as PEWTER_LANDMARKS,
    PEWTER_MAP_IDS,
    default_navigation_target as default_pewter_navigation_target,
    target_options_for_current_map as pewter_target_options_for_current_map,
)
from pokemon_player.skills.overworld_rearrange_party import overworld_rearrange_party
from pokemon_player.skills.purchase_pokemart_item import (
    normalize_shop_item,
    purchase_pokemart_item,
    stock_for_snapshot,
)
from pokemon_player.skills.recover_to_overworld import recover_to_overworld
from pokemon_player.skills.resolve_battle_outcome_dialogue_bundle import (
    resolve_battle_outcome_dialogue_bundle,
    screenshot_has_pokedex_intro_dialogue,
    screenshot_has_pokedex_page,
)
from pokemon_player.skills.run_from_wild_battle import run_from_wild_battle
from pokemon_player.skills.switch_party_member import switch_party_member
from pokemon_player.skills.talk_to_npc import (
    default_interaction_target,
    interaction_options,
    talk_to_npc,
)
from pokemon_player.skills.use_move import use_move
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict


EXECUTABLE_SKILLS = (
    "advance_battle_dialogue",
    "advance_dialogue",
    "attempt_catch",
    "choose_starter",
    "close_menu_or_cancel",
    "complete_prologue",
    "enter_grass_search_loop",
    "enter_nickname_text",
    "handle_nickname_prompt",
    "handle_move_learning_prompt",
    "handle_trainer_switch_prompt",
    "heal_at_pokecenter",
    "literal_button_press",
    "navigate_within_pallet_region",
    "navigate_within_pewter_region",
    "navigate_within_viridian_forest_region",
    "overworld_rearrange_party",
    "purchase_pokemart_item",
    "recover_to_overworld",
    "resolve_battle_outcome_dialogue_bundle",
    "run_from_wild_battle",
    "switch_party_member",
    "talk_to_npc",
    "use_move",
)


SKILL_LABELS = {
    "advance_battle_dialogue": "Advance Battle Dialogue",
    "advance_dialogue": "Advance Dialogue",
    "attempt_catch": "Throw Poke Ball",
    "choose_starter": "Choose Starter",
    "close_menu_or_cancel": "Close Menu / Cancel",
    "complete_prologue": "Complete Prologue",
    "enter_grass_search_loop": "Enter Grass Search",
    "enter_nickname_text": "Enter Nickname Text",
    "handle_nickname_prompt": "Handle Nickname Prompt",
    "handle_move_learning_prompt": "Handle Move Learning",
    "handle_trainer_switch_prompt": "Handle Trainer Switch Prompt",
    "heal_at_pokecenter": "Heal At PokeCenter",
    "literal_button_press": "Press Button",
    "navigate_within_pallet_region": "Navigate Pallet",
    "navigate_within_pewter_region": "Navigate Pewter",
    "navigate_within_viridian_forest_region": "Navigate Capsule A",
    "overworld_rearrange_party": "Rearrange Party",
    "purchase_pokemart_item": "Buy Mart Item",
    "recover_to_overworld": "Recover To Overworld",
    "resolve_battle_outcome_dialogue_bundle": "Resolve Battle Outcome",
    "run_from_wild_battle": "Run From Wild Battle",
    "switch_party_member": "Switch Party Member",
    "talk_to_npc": "Talk To NPC",
    "use_move": "Use Move",
}

DIRECTOR_BUTTONS = ("a", "b", "up", "down", "left", "right", "start", "select")

REQUEST_TIMEOUT_SECONDS = 300


@dataclass
class DirectorPlayerConfig:
    rom_path: Path
    state_path: Path | None
    host: str
    port: int
    window: str
    render: bool
    run_root: Path
    status_dir: Path
    post_load_settle_frames: int = 60
    idle_tick_hz: int = 60
    emulation_speed: int = 1
    status_period_seconds: float = 5.0
    slow_tick_ms: float = 120.0
    slow_status_ms: float = 200.0
    operations_control_path: Path | None = None


@dataclass(frozen=True)
class PlayerCommand:
    action: str
    payload: dict[str, Any]
    future: Future[dict[str, Any]]


@dataclass
class DirectorPlayer:
    pyboy: Any
    rom: RomFingerprint
    config: DirectorPlayerConfig
    started_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    busy: bool = False
    last_result: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    command_queue: Queue[PlayerCommand] = field(default_factory=Queue, init=False, repr=False)
    cached_status: dict[str, Any] | None = field(default=None, init=False, repr=False)
    cached_status_at: float = field(default=0.0, init=False, repr=False)
    status_cache_lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    last_observed_snapshot: dict[str, Any] | None = field(default=None, init=False, repr=False)
    session_id: str = field(default="", init=False)
    session_dir: Path = field(init=False)
    event_log_path: Path = field(init=False)
    manifest_path: Path = field(init=False)
    event_artifact_dir: Path = field(init=False)
    event_seq: int = field(default=0, init=False)
    last_slow_tick_logged_at: float = field(default=0.0, init=False, repr=False)
    diagnostic_mode: bool = field(default=False, init=False)
    stop_after_action_latched: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.stop_event = threading.Event()
        self.config.run_root.mkdir(parents=True, exist_ok=True)
        self.config.status_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = timestamp_for_path(self.started_utc, prefix="session")
        self.session_dir = self.config.run_root / "sessions" / self.session_id
        self.event_artifact_dir = self.session_dir / "events"
        self.event_log_path = self.session_dir / "events.jsonl"
        self.manifest_path = self.session_dir / "manifest.json"
        self.event_artifact_dir.mkdir(parents=True, exist_ok=True)
        if self.config.state_path:
            load_state(self.pyboy, self.config.state_path)
        self.pyboy.set_emulation_speed(self.config.emulation_speed)
        self.pyboy.tick(self.config.post_load_settle_frames, self.config.render)
        self._write_session_manifest()
        self._record_session_event(
            "session_started",
            "Director player session started.",
            evidence=[
                f"state_path={self.config.state_path}" if self.config.state_path else "state_path=none",
                f"window={self.config.window}",
                f"render={self.config.render}",
            ],
            capture_artifacts=True,
        )
        self._fresh_status(log_observations=False)

    def stop(self) -> None:
        self.stop_event.set()
        self.pyboy.stop(False)

    def run_main_loop(self) -> None:
        idle_interval = 1 / self.config.idle_tick_hz if self.config.idle_tick_hz > 0 else 0.05
        while not self.stop_event.is_set():
            try:
                command = self.command_queue.get(timeout=idle_interval)
            except Empty:
                control = self._control_state()
                if control["stopAfterAction"]:
                    self.stop_after_action_latched = True
                if self.config.idle_tick_hz > 0 and not self.busy and control["state"] == "running" and not self.stop_after_action_latched:
                    tick_started = time.perf_counter()
                    self.pyboy.tick(1, self.config.render)
                    tick_ms = (time.perf_counter() - tick_started) * 1000
                    self._maybe_log_slow_tick(tick_ms)
                    self._maybe_refresh_status_cache()
                continue
            self._handle_command(command)

    def request_status(self, *, fresh: bool = False) -> dict[str, Any]:
        if fresh:
            return self._submit("fresh_status", {})
        with self.status_cache_lock:
            if self.cached_status is not None:
                return self._cached_status_response_locked()
        return self._submit("status", {})

    def request_load_state(self, state_path: str | Path) -> dict[str, Any]:
        return self._submit("load_state", {"state_path": str(state_path)})

    def request_execute_skill(self, skill_id: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._submit("execute_skill", {"skill_id": skill_id, "args": args or {}})

    def request_manual_input(self, button: str) -> dict[str, Any]:
        return self._submit("manual_input", {"button": button})

    def request_diagnostic_mode(self, enabled: bool) -> dict[str, Any]:
        return self._submit("diagnostic_mode", {"enabled": enabled})

    def request_capture_interpretation(self, title: str, description: str) -> dict[str, Any]:
        return self._submit(
            "capture_interpretation",
            {"title": title, "description": description},
        )

    def _submit(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        future: Future[dict[str, Any]] = Future()
        self.command_queue.put(PlayerCommand(action=action, payload=payload, future=future))
        return future.result(timeout=REQUEST_TIMEOUT_SECONDS)

    def _handle_command(self, command: PlayerCommand) -> None:
        try:
            if command.action == "status":
                result = self._status()
            elif command.action == "fresh_status":
                result = self._fresh_status(log_observations=True)
            elif command.action == "load_state":
                result = self._load_state(str(command.payload.get("state_path", "")))
            elif command.action == "execute_skill":
                result = self._execute_skill(
                    str(command.payload.get("skill_id", "")),
                    command.payload.get("args") if isinstance(command.payload.get("args"), dict) else {},
                )
            elif command.action == "manual_input":
                result = self._manual_input(str(command.payload.get("button", "")))
            elif command.action == "diagnostic_mode":
                result = self._set_diagnostic_mode(bool(command.payload.get("enabled")))
            elif command.action == "capture_interpretation":
                result = self._capture_interpretation(
                    str(command.payload.get("title", "")),
                    str(command.payload.get("description", "")),
                )
            else:
                raise ValueError(f"Unsupported director player command: {command.action}")
            command.future.set_result(result)
        except Exception as exc:
            command.future.set_exception(exc)
        finally:
            if command.action in {
                "load_state",
                "execute_skill",
                "manual_input",
                "capture_interpretation",
            } and self._control_state()["stopAfterAction"]:
                self.stop_after_action_latched = True
            self.command_queue.task_done()

    def _control_state(self) -> dict[str, Any]:
        path = getattr(self.config, "operations_control_path", None)
        control: dict[str, Any] = {}
        if path:
            try:
                loaded = json.loads(Path(path).read_text(encoding="utf-8"))
                control = loaded if isinstance(loaded, dict) else {}
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                control = {}
        state = str(control.get("state") or "running")
        if state not in {"running", "paused", "emergency_stopped"}:
            state = "running"
        return {"state": state, "stopAfterAction": bool(control.get("stopAfterAction"))}

    def _effective_control_state(self) -> str:
        control = self._control_state()
        if control["state"] == "running" and not control["stopAfterAction"]:
            self.stop_after_action_latched = False
        if getattr(self, "stop_after_action_latched", False):
            return "stopped_after_action"
        return control["state"]

    def _assert_game_action_allowed(self) -> None:
        state = self._effective_control_state()
        if state == "paused":
            raise RuntimeError("Director player is paused by Operations.")
        if state == "emergency_stopped":
            raise RuntimeError("Director player is emergency-stopped by Operations.")
        if state == "stopped_after_action":
            raise RuntimeError("Director player stopped after the previous action.")

    def _set_diagnostic_mode(self, enabled: bool) -> dict[str, Any]:
        self.diagnostic_mode = enabled
        self._record_session_event(
            "diagnostic_mode",
            "Raw button diagnostic capture mode enabled." if enabled else "Raw button diagnostic capture mode disabled.",
            status="warning" if enabled else "info",
            args={"enabled": enabled},
        )
        with self.status_cache_lock:
            self.cached_status = None
        return self._fresh_status(log_observations=False)

    def _status(self) -> dict[str, Any]:
        with self.status_cache_lock:
            if self.cached_status is not None:
                return self._cached_status_response_locked()
        return self._fresh_status(log_observations=True)

    def _cached_status_response_locked(self) -> dict[str, Any]:
        assert self.cached_status is not None
        status = {**self.cached_status, "busy": self.busy}
        performance = dict(status.get("performance") or {})
        performance["statusAgeSeconds"] = round(max(time.monotonic() - self.cached_status_at, 0.0), 2)
        status["performance"] = performance
        return status

    def _fresh_status(self, *, log_observations: bool) -> dict[str, Any]:
        status_started = time.perf_counter()
        current = snapshot(self.pyboy)
        current_dict = snapshot_to_dict(current)
        current_hash = snapshot_hash(current)
        screenshot_path = self.config.status_dir / "current.png"
        save_screenshot(self.pyboy, screenshot_path)
        if log_observations:
            self._append_observation_events(current_dict, current_hash=current_hash, screenshot_path=screenshot_path)
        else:
            self.last_observed_snapshot = current_dict
        availability = skill_availability(current_dict, screenshot_path)
        signals = promoted_signals(current_dict, screenshot_path)
        status_ms = (time.perf_counter() - status_started) * 1000
        self._maybe_log_slow_status(status_ms)
        status = {
            "schema": "director_player_status_v1",
            "running": True,
            "busy": self.busy,
            "control": {
                "state": self._effective_control_state(),
                "stopAfterAction": self._control_state()["stopAfterAction"],
            },
            "diagnosticMode": getattr(self, "diagnostic_mode", False),
            "startedUtc": self.started_utc,
            "session": {
                "id": self.session_id,
                "dir": str(self.session_dir),
                "eventLogPath": str(self.event_log_path),
                "manifestPath": str(self.manifest_path),
            },
            "rom": {
                "path": str(self.rom.path),
                "title": self.rom.title,
                "sha256": self.rom.sha256,
            },
            "player": {
                "window": self.config.window,
                "render": self.config.render,
                "runRoot": str(self.config.run_root),
                "statusDir": str(self.config.status_dir),
                "statusPeriodSeconds": self.config.status_period_seconds,
            },
            "snapshotHash": current_hash,
            "snapshot": current_dict,
            "screenshotPath": str(screenshot_path),
            "signals": signals,
            "skills": availability,
            "lastResult": self.last_result,
            "history": list(reversed(self.history[-20:])),
            "performance": {
                "freshStatusMs": round(status_ms, 1),
                "statusAgeSeconds": 0.0,
            },
        }
        with self.status_cache_lock:
            self.cached_status = status
            self.cached_status_at = time.monotonic()
        return status

    def _maybe_refresh_status_cache(self) -> None:
        if self.config.status_period_seconds <= 0:
            return
        now = time.monotonic()
        with self.status_cache_lock:
            due = self.cached_status is None or now - self.cached_status_at >= self.config.status_period_seconds
        if due:
            self._fresh_status(log_observations=True)

    def _append_observation_events(
        self,
        current_dict: dict[str, Any],
        *,
        current_hash: str,
        screenshot_path: Path,
    ) -> None:
        for summary, evidence in informative_snapshot_events(self.last_observed_snapshot, current_dict):
            event = self._record_session_event(
                "observation",
                summary,
                evidence=evidence,
                snapshot_hash_value=current_hash,
                screenshot_path=screenshot_path,
                capture_artifacts=True,
            )
            artifact_evidence = list(evidence)
            if event.get("statePath"):
                artifact_evidence.append(f"event_state={event['statePath']}")
            if event.get("screenshotPath"):
                artifact_evidence.append(f"event_screenshot={event['screenshotPath']}")
            self.history.append(info_history_item(summary, artifact_evidence))
        self.last_observed_snapshot = current_dict

    def _load_state(self, state_path: str | Path) -> dict[str, Any]:
        self._assert_game_action_allowed()
        candidate = Path(state_path).resolve()
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        self.busy = True
        try:
            load_state(self.pyboy, candidate)
            self.pyboy.tick(self.config.post_load_settle_frames, self.config.render)
            self.history.append(info_history_item(f"Loaded state: {candidate.name}", [f"state_path={candidate}"]))
            self._record_session_event(
                "state_loaded",
                f"Loaded state: {candidate.name}",
                evidence=[f"state_path={candidate}"],
                state_path=candidate,
                capture_artifacts=True,
            )
        finally:
            self.busy = False
        self.cached_status = None
        return self._fresh_status(log_observations=False)

    def _execute_skill(self, skill_id: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_game_action_allowed()
        if skill_id not in EXECUTABLE_SKILLS:
            raise ValueError(f"Unsupported director-player skill: {skill_id}")
        args = args or {}
        if skill_id == "literal_button_press":
            raw_button = args.get("button")
            if raw_button is None and isinstance(args.get("buttons"), list) and args["buttons"]:
                raw_button = args["buttons"][0]
            return self._literal_button_press(str(raw_button or "a"), args)
        self.busy = True
        started = datetime.now(UTC).isoformat()
        state_in = self.config.status_dir / "skill-input.state"
        save_state(self.pyboy, state_in)
        try:
            artifact = self._dispatch_skill(skill_id, state_in, args)
            result = {
                "createdUtc": started,
                "skillId": artifact.result.skill_id,
                "status": artifact.result.status,
                "summary": artifact.result.summary,
                "evidence": list(artifact.result.evidence),
                "warnings": list(artifact.result.warnings),
                "runDir": str(artifact.run_dir),
                "reportPath": str(artifact.report_path),
                "args": args,
            }
        except Exception as exc:
            result = {
                "createdUtc": started,
                "skillId": skill_id,
                "status": "error",
                "summary": str(exc),
                "evidence": [],
                "warnings": [exc.__class__.__name__],
                "runDir": None,
                "reportPath": None,
                "args": args,
            }
        finally:
            self.busy = False
        self.last_result = result
        self.history.append(result)
        self._record_session_event(
            "skill_result",
            str(result["summary"]),
            status=str(result["status"]),
            evidence=list(result["evidence"]),
            run_dir=result["runDir"],
            report_path=result["reportPath"],
            args=result["args"],
        )
        self.cached_status = None
        return self._fresh_status(log_observations=True)

    def _literal_button_press(self, button: str, args: dict[str, Any]) -> dict[str, Any]:
        normalized = button.strip().lower()
        if normalized not in DIRECTOR_BUTTONS:
            raise ValueError(f"Unsupported literal button: {button}")
        self.busy = True
        started = datetime.now(UTC).isoformat()
        try:
            run_timed_trace(
                self.pyboy,
                [ButtonInput(normalized, hold_frames=8, settle_frames=36)],
                render=self.config.render,
            )
            result = {
                "createdUtc": started,
                "skillId": "literal_button_press",
                "status": "succeeded",
                "summary": f"Pressed {normalized.upper()} once.",
                "evidence": [f"button={normalized}"],
                "warnings": [],
                "runDir": None,
                "reportPath": None,
                "args": args,
            }
        except Exception as exc:
            result = {
                "createdUtc": started,
                "skillId": "literal_button_press",
                "status": "error",
                "summary": str(exc),
                "evidence": [],
                "warnings": [exc.__class__.__name__],
                "runDir": None,
                "reportPath": None,
                "args": args,
            }
        finally:
            self.busy = False
        self.last_result = result
        self.history.append(result)
        self._record_session_event(
            "skill_result",
            str(result["summary"]),
            status=str(result["status"]),
            evidence=list(result["evidence"]),
            args=result["args"],
        )
        self.cached_status = None
        return self._fresh_status(log_observations=False)

    def _manual_input(self, button: str) -> dict[str, Any]:
        self._assert_game_action_allowed()
        if not getattr(self, "diagnostic_mode", False):
            raise PermissionError("Raw button input is available only in explicit diagnostic capture mode.")
        if button not in DIRECTOR_BUTTONS:
            raise ValueError(f"Unsupported manual button: {button}")
        self.busy = True
        started = datetime.now(UTC).isoformat()
        run_dir = self.config.run_root / "manual_input" / timestamp_for_path(started, prefix=button)
        run_dir.mkdir(parents=True, exist_ok=True)
        before_state_path = run_dir / "before.state"
        after_state_path = run_dir / "after.state"
        before_screenshot_path = run_dir / "before.png"
        after_screenshot_path = run_dir / "after.png"
        report_path = run_dir / "report.json"
        trace = [ButtonInput(button, hold_frames=8, settle_frames=36)]
        try:
            before = snapshot(self.pyboy)
            save_state(self.pyboy, before_state_path)
            save_screenshot(self.pyboy, before_screenshot_path)
            run_timed_trace(self.pyboy, trace, render=self.config.render)
            after = snapshot(self.pyboy)
            save_state(self.pyboy, after_state_path)
            save_screenshot(self.pyboy, after_screenshot_path)
            report = {
                "schema": "director_manual_input_v1",
                "createdUtc": started,
                "button": button,
                "rom": {
                    "path": str(self.rom.path),
                    "title": self.rom.title,
                    "sha256": self.rom.sha256,
                },
                "before": snapshot_to_dict(before),
                "after": snapshot_to_dict(after),
                "beforeSnapshotHash": snapshot_hash(before),
                "afterSnapshotHash": snapshot_hash(after),
                "beforeStatePath": str(before_state_path),
                "afterStatePath": str(after_state_path),
                "beforeScreenshotPath": str(before_screenshot_path),
                "afterScreenshotPath": str(after_screenshot_path),
                "trace": [{"button": button, "hold_frames": 8, "settle_frames": 36}],
                "note": "Manual Director UI input; treat as a likely skill coverage or executor gap.",
            }
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            result = {
                "createdUtc": started,
                "skillId": "manual_input",
                "status": "info",
                "summary": f"Manual button {button} pressed; diagnostic artifacts captured.",
                "evidence": [
                    f"button={button}",
                    f"before_state={before_state_path}",
                    f"after_state={after_state_path}",
                    f"before_screenshot={before_screenshot_path}",
                    f"after_screenshot={after_screenshot_path}",
                ],
                "warnings": ["manual_input_indicates_skill_gap"],
                "runDir": str(run_dir),
                "reportPath": str(report_path),
                "args": {"button": button},
            }
        finally:
            self.busy = False
        self.last_result = result
        self.history.append(result)
        self._record_session_event(
            "manual_input",
            str(result["summary"]),
            status=str(result["status"]),
            evidence=list(result["evidence"]),
            run_dir=str(run_dir),
            report_path=str(report_path),
            args={"button": button},
        )
        self.cached_status = None
        return self._fresh_status(log_observations=True)

    def _capture_interpretation(self, title: str, description: str) -> dict[str, Any]:
        self._assert_game_action_allowed()
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Capture title is required.")
        cleaned_description = description.strip()
        self.busy = True
        started = datetime.now(UTC).isoformat()
        run_dir = (
            self.config.run_root
            / "interpretation_captures"
            / timestamp_for_path(started, prefix=safe_path_token(cleaned_title)[:48] or "capture")
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        state_path = run_dir / "state.state"
        screenshot_path = run_dir / "screenshot.png"
        report_path = run_dir / "report.json"
        try:
            current = snapshot(self.pyboy)
            current_dict = snapshot_to_dict(current)
            current_hash = snapshot_hash(current)
            save_state(self.pyboy, state_path)
            save_screenshot(self.pyboy, screenshot_path)
            signals = promoted_signals(current_dict, screenshot_path)
            skills = skill_availability(current_dict, screenshot_path)
            report = {
                "schema": "director_interpretation_capture_v1",
                "createdUtc": started,
                "title": cleaned_title,
                "description": cleaned_description,
                "rom": {
                    "path": str(self.rom.path),
                    "title": self.rom.title,
                    "sha256": self.rom.sha256,
                },
                "session": {
                    "id": self.session_id,
                    "dir": str(self.session_dir),
                    "eventLogPath": str(self.event_log_path),
                },
                "snapshotHash": current_hash,
                "snapshot": current_dict,
                "screenshotPath": str(screenshot_path),
                "statePath": str(state_path),
                "interpretation": {
                    "signals": signals,
                    "skills": skills,
                },
            }
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            result = {
                "createdUtc": started,
                "skillId": "capture_interpretation",
                "status": "info",
                "summary": f"Captured interpretation: {cleaned_title}",
                "evidence": [
                    f"title={cleaned_title}",
                    f"state={state_path}",
                    f"screenshot={screenshot_path}",
                    f"report={report_path}",
                ],
                "warnings": [],
                "runDir": str(run_dir),
                "reportPath": str(report_path),
                "args": {"title": cleaned_title, "description": cleaned_description},
            }
        finally:
            self.busy = False
        self.last_result = result
        self.history.append(result)
        self._record_session_event(
            "interpretation_capture",
            str(result["summary"]),
            status=str(result["status"]),
            evidence=list(result["evidence"]),
            snapshot_hash_value=current_hash,
            screenshot_path=screenshot_path,
            state_path=state_path,
            run_dir=str(run_dir),
            report_path=str(report_path),
            args={"title": cleaned_title, "description": cleaned_description},
        )
        self.cached_status = None
        with self.status_cache_lock:
            self.cached_status = None
        return self._fresh_status(log_observations=False)

    def _write_session_manifest(self) -> None:
        manifest = {
            "schema": "director_session_manifest_v1",
            "sessionId": self.session_id,
            "startedUtc": self.started_utc,
            "sessionDir": str(self.session_dir),
            "eventLogPath": str(self.event_log_path),
            "rom": {
                "path": str(self.rom.path),
                "title": self.rom.title,
                "sha256": self.rom.sha256,
            },
            "config": {
                "statePath": str(self.config.state_path) if self.config.state_path else None,
                "window": self.config.window,
                "render": self.config.render,
                "idleTickHz": self.config.idle_tick_hz,
                "emulationSpeed": self.config.emulation_speed,
                "statusPeriodSeconds": self.config.status_period_seconds,
                "slowTickMs": self.config.slow_tick_ms,
                "slowStatusMs": self.config.slow_status_ms,
            },
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    def _record_session_event(
        self,
        kind: str,
        summary: str,
        *,
        status: str = "info",
        evidence: list[str] | tuple[str, ...] = (),
        snapshot_hash_value: str | None = None,
        screenshot_path: str | Path | None = None,
        state_path: str | Path | None = None,
        run_dir: str | Path | None = None,
        report_path: str | Path | None = None,
        args: dict[str, Any] | None = None,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        sequence = self.event_seq
        self.event_seq += 1
        created = datetime.now(UTC).isoformat()
        event_state_path: Path | None = None
        event_screenshot_path: Path | None = None
        warnings: list[str] = []
        if capture_artifacts:
            artifact_dir = self.event_artifact_dir / f"{sequence:05d}-{safe_path_token(kind)}"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            event_state_path = artifact_dir / "state.state"
            event_screenshot_path = artifact_dir / "screenshot.png"
            try:
                save_state(self.pyboy, event_state_path)
            except Exception as exc:
                warnings.append(f"state_capture_failed={exc.__class__.__name__}: {exc}")
                event_state_path = None
            try:
                if screenshot_path and Path(screenshot_path).exists():
                    shutil.copyfile(screenshot_path, event_screenshot_path)
                else:
                    save_screenshot(self.pyboy, event_screenshot_path)
            except Exception as exc:
                warnings.append(f"screenshot_capture_failed={exc.__class__.__name__}: {exc}")
                event_screenshot_path = None

        event = {
            "schema": "director_session_event_v1",
            "sequence": sequence,
            "createdUtc": created,
            "kind": kind,
            "status": status,
            "summary": summary,
            "evidence": list(evidence),
            "snapshotHash": snapshot_hash_value,
            "statePath": str(event_state_path or state_path) if (event_state_path or state_path) else None,
            "screenshotPath": str(event_screenshot_path or screenshot_path)
            if (event_screenshot_path or screenshot_path)
            else None,
            "runDir": str(run_dir) if run_dir else None,
            "reportPath": str(report_path) if report_path else None,
            "args": args or {},
            "warnings": warnings,
        }
        with self.event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def _maybe_log_slow_tick(self, tick_ms: float) -> None:
        if self.config.slow_tick_ms <= 0 or tick_ms < self.config.slow_tick_ms:
            return
        now = time.monotonic()
        if now - self.last_slow_tick_logged_at < 5:
            return
        self.last_slow_tick_logged_at = now
        self._record_session_event(
            "performance_warning",
            f"Idle PyBoy tick took {tick_ms:.1f} ms.",
            status="warning",
            evidence=[
                f"tick_ms={tick_ms:.1f}",
                f"idle_tick_hz={self.config.idle_tick_hz}",
                f"render={self.config.render}",
            ],
        )

    def _maybe_log_slow_status(self, status_ms: float) -> None:
        if self.config.slow_status_ms <= 0 or status_ms < self.config.slow_status_ms:
            return
        self._record_session_event(
            "performance_warning",
            f"Fresh Director status build took {status_ms:.1f} ms.",
            status="warning",
            evidence=[
                f"status_ms={status_ms:.1f}",
                f"status_period_seconds={self.config.status_period_seconds}",
            ],
        )

    def _dispatch_skill(self, skill_id: str, state_in: Path, args: dict[str, Any]) -> SkillRunArtifact:
        common = {
            "state_in": state_in,
            "rom": self.rom,
            "run_root": self.config.run_root,
            "render": self.config.render,
            "post_load_settle_frames": self.config.post_load_settle_frames,
            "emulation_speed": self.config.emulation_speed,
        }
        if skill_id == "advance_dialogue":
            return execute_advance_dialogue(self.pyboy, **common)
        if skill_id == "advance_battle_dialogue":
            return execute_advance_battle_dialogue(
                self.pyboy,
                **common,
                max_inputs=int(args.get("maxInputs", 32)),
            )
        if skill_id == "attempt_catch":
            return execute_attempt_catch(
                self.pyboy,
                **common,
                max_wait_frames=int(args.get("maxWaitFrames", 1800)),
                throw_executor=str(args.get("throwExecutor", "battle-menu-controller")),
                battle_menu_max_steps=int(args.get("battleMenuMaxSteps", 40)),
            )
        if skill_id == "close_menu_or_cancel":
            return execute_close_menu_or_cancel(self.pyboy, **common)
        if skill_id == "complete_prologue":
            return execute_complete_prologue(
                self.pyboy,
                **common,
                player_name=str(args.get("playerName", args.get("player_name", "RED"))).upper(),
                rival_name=str(args.get("rivalName", args.get("rival_name", "BLUE"))).upper(),
                handoff=str(args.get("handoff", "pallet_outside")),  # type: ignore[arg-type]
                max_intro_presses=int(args.get("maxIntroPresses", 120)),
                max_handoff_inputs=int(args.get("maxHandoffInputs", 120)),
            )
        if skill_id == "choose_starter":
            return execute_choose_starter(
                self.pyboy,
                **common,
                starter=str(args.get("starter", "squirtle")),
                nickname=str(args["nickname"]) if args.get("nickname") else None,
                max_wait_frames=int(args.get("maxWaitFrames", 1800)),
            )
        if skill_id == "enter_grass_search_loop":
            return execute_enter_grass_search_loop(
                self.pyboy,
                **common,
                patch=str(args.get("patch", "current_map")),
                max_steps=int(args.get("maxSteps", 240)),
            )
        if skill_id == "handle_nickname_prompt":
            return execute_handle_nickname_prompt(
                self.pyboy,
                **common,
                choice=normalize_nickname_choice_arg(args),
            )
        if skill_id == "handle_move_learning_prompt":
            choice = normalize_move_learning_choice_arg(args)
            forget_move = normalize_requested_move_arg(
                args.get("forgetMove", args.get("forget_move", args.get("move")))
            )
            if choice == "replace" and (forget_move is None or forget_move == ""):
                raise ValueError("handle_move_learning_prompt requires forgetMove when choice is replace.")
            return execute_handle_move_learning_prompt(
                self.pyboy,
                **common,
                choice=choice,
                forget_move=forget_move,
            )
        if skill_id == "handle_trainer_switch_prompt":
            choice = normalize_trainer_switch_choice_arg(args)
            target = normalize_party_target_arg(args.get("target"))
            if choice == "switch" and (target is None or target == ""):
                raise ValueError("handle_trainer_switch_prompt requires target when choice is switch.")
            if isinstance(target, str) and target.isdigit():
                target = int(target)
            return execute_handle_trainer_switch_prompt(
                self.pyboy,
                **common,
                choice=choice,
                target=target,
                max_wait_frames=int(args.get("maxWaitFrames", 1200)),
            )
        if skill_id == "heal_at_pokecenter":
            return execute_heal_at_pokecenter(
                self.pyboy,
                **common,
                max_inputs=int(args.get("maxInputs", 24)),
            )
        if skill_id == "enter_nickname_text":
            return execute_enter_nickname_text(
                self.pyboy,
                **common,
                nickname=normalize_nickname_text_arg(args),
            )
        if skill_id == "navigate_within_viridian_forest_region":
            return execute_navigate_within_viridian_forest_region(
                self.pyboy,
                **common,
                target=str(args.get("target", "forest_grass")),
                max_inputs=int(args.get("maxInputs", 260)),
                max_segment_expansions=int(args.get("maxSegmentExpansions", 3000)),
                planner_window=str(args.get("plannerWindow", "null")),
            )
        if skill_id == "navigate_within_pallet_region":
            return execute_navigate_within_pallet_region(
                self.pyboy,
                **common,
                target=str(args["target"]) if args.get("target") else None,
                max_inputs=int(args.get("maxInputs", 180)),
                max_segment_expansions=int(args.get("maxSegmentExpansions", 1600)),
                planner_window=str(args.get("plannerWindow", "null")),
            )
        if skill_id == "navigate_within_pewter_region":
            return execute_navigate_within_pewter_region(
                self.pyboy,
                **common,
                target=str(args["target"]) if args.get("target") else None,
                max_inputs=int(args.get("maxInputs", 260)),
                max_segment_expansions=int(args.get("maxSegmentExpansions", 3000)),
                planner_window=str(args.get("plannerWindow", "null")),
            )
        if skill_id == "overworld_rearrange_party":
            target = args.get("target")
            if target is None or target == "":
                raise ValueError("overworld_rearrange_party requires target.")
            if isinstance(target, str) and target.isdigit():
                target = int(target)
            return execute_overworld_rearrange_party(
                self.pyboy,
                **common,
                target=target,
                destination_slot=int(args.get("destinationSlot", 1)),
            )
        if skill_id == "purchase_pokemart_item":
            return execute_purchase_pokemart_item(
                self.pyboy,
                **common,
                item=normalize_shop_item_arg(args),
                quantity=int(args.get("quantity", 1) or 1),
            )
        if skill_id == "recover_to_overworld":
            return execute_recover_to_overworld(
                self.pyboy,
                **common,
                max_inputs=int(args.get("maxInputs", 12)),
            )
        if skill_id == "resolve_battle_outcome_dialogue_bundle":
            return execute_resolve_battle_outcome_dialogue_bundle(self.pyboy, **common)
        if skill_id == "run_from_wild_battle":
            return execute_run_from_wild_battle(
                self.pyboy,
                **common,
                max_wait_frames=int(args.get("maxWaitFrames", 900)),
            )
        if skill_id == "switch_party_member":
            target = normalize_party_target_arg(args.get("target"))
            if target is None or target == "":
                raise ValueError("switch_party_member requires target.")
            if isinstance(target, str) and target.isdigit():
                target = int(target)
            return execute_switch_party_member(
                self.pyboy,
                **common,
                target=target,
                max_wait_frames=int(args.get("maxWaitFrames", 1200)),
            )
        if skill_id == "talk_to_npc":
            target = str(args.get("target") or "").strip()
            if not target:
                raise ValueError("talk_to_npc requires target.")
            return execute_talk_to_npc(
                self.pyboy,
                **common,
                target=target,
            )
        if skill_id == "use_move":
            move = normalize_requested_move_arg(args.get("move"))
            if move is None or move == "":
                raise ValueError("use_move requires move.")
            return execute_use_move(
                self.pyboy,
                **common,
                requested_move=move,
                max_wait_frames=int(args.get("maxWaitFrames", 1200)),
            )
        raise ValueError(f"Unsupported director-player skill: {skill_id}")


def info_history_item(summary: str, evidence: list[str] | tuple[str, ...]) -> dict[str, Any]:
    return {
        "createdUtc": datetime.now(UTC).isoformat(),
        "skillId": "observation",
        "status": "info",
        "summary": summary,
        "evidence": list(evidence),
        "warnings": [],
        "runDir": None,
        "reportPath": None,
        "args": {},
    }


def timestamp_for_path(timestamp: str, *, prefix: str) -> str:
    normalized = (
        timestamp.replace(":", "")
        .replace("-", "")
        .replace(".", "")
        .replace("+", "Z")
        .replace("T", "T")
    )
    return f"{prefix}-{normalized}"


def safe_path_token(value: str) -> str:
    cleaned = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in {"-", "_"}:
            cleaned.append(char)
        else:
            cleaned.append("-")
    token = "".join(cleaned).strip("-")
    return token or "event"


def informative_snapshot_events(
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> list[tuple[str, list[str]]]:
    if before is None:
        return []
    before_party = party_by_slot(before)
    after_party = party_by_slot(after)
    events: list[tuple[str, list[str]]] = []
    before_battle = battle_active(before)
    after_battle = battle_active(after)
    before_enemy = enemy_facts(before)
    after_enemy = enemy_facts(after)

    if not before_battle and after_battle:
        events.append(
            (
                "Battle started.",
                [
                    f"battle_type_raw={after.get('battle_type_raw')}",
                    f"enemy={format_enemy(after_enemy)}",
                ],
            )
        )
    if before_battle and not after_battle:
        events.append(
            (
                "Battle ended.",
                [
                    f"battle_type_raw={before.get('battle_type_raw')} -> {after.get('battle_type_raw')}",
                    f"last_enemy={format_enemy(before_enemy)}",
                ],
            )
        )
    if before_battle and after_battle and enemy_signature(before_enemy) != enemy_signature(after_enemy):
        events.append(
            (
                "Opponent Pokemon changed.",
                [
                    f"before={format_enemy(before_enemy)}",
                    f"after={format_enemy(after_enemy)}",
                ],
            )
        )
    if (
        before_battle
        and after_battle
        and before_enemy
        and after_enemy
        and int(before_enemy.get("hp", 0) or 0) > 0
        and int(after_enemy.get("hp", 0) or 0) == 0
    ):
        events.append(
            (
                "Enemy Pokemon HP reached 0.",
                [
                    f"enemy={format_enemy(after_enemy)}",
                    f"before_hp={before_enemy.get('hp')}",
                    f"after_hp={after_enemy.get('hp')}",
                ],
            )
        )

    if party_signature(before_party) != party_signature(after_party):
        events.append(
            (
                "Party composition changed.",
                [
                    f"before={format_party_signature(before_party)}",
                    f"after={format_party_signature(after_party)}",
                ],
            )
        )

    for slot, member in after_party.items():
        previous = before_party.get(slot)
        if not previous:
            continue
        label = party_member_label(member)
        before_species = previous.get("species_name")
        after_species = member.get("species_name")
        if before_species != after_species:
            events.append(
                (
                    f"{label} evolved from {before_species} into {after_species}.",
                    [f"slot={slot}", f"before_species={before_species}", f"after_species={after_species}"],
                )
            )
        before_level = previous.get("level")
        after_level = member.get("level")
        if before_level != after_level:
            events.append(
                (
                    f"{label} level changed.",
                    [f"slot={slot}", f"before_level={before_level}", f"after_level={after_level}"],
                )
            )
        before_moves = move_names(previous)
        after_moves = move_names(member)
        if before_moves != after_moves:
            added = [move for move in after_moves if move and move not in before_moves]
            removed = [move for move in before_moves if move and move not in after_moves]
            summary = f"{label} move list changed."
            if added and not removed:
                summary = f"{label} learned {', '.join(added)}."
            events.append(
                (
                    summary,
                    [
                        f"slot={slot}",
                        f"before_moves={', '.join(before_moves) or 'none'}",
                        f"after_moves={', '.join(after_moves) or 'none'}",
                    ],
                )
            )
    return events


def battle_active(snapshot_dict: dict[str, Any]) -> bool:
    return snapshot_dict.get("mode") == "battle" and snapshot_dict.get("battle_type_raw") not in {None, 0}


def enemy_facts(snapshot_dict: dict[str, Any]) -> dict[str, Any] | None:
    enemy = snapshot_dict.get("enemy")
    return enemy if isinstance(enemy, dict) else None


def enemy_signature(enemy: dict[str, Any] | None) -> tuple[Any, Any, Any]:
    if not enemy:
        return (None, None, None)
    return (enemy.get("species_id"), enemy.get("species_name"), enemy.get("level"))


def format_enemy(enemy: dict[str, Any] | None) -> str:
    if not enemy:
        return "none"
    return (
        f"{enemy.get('species_name', 'unknown')} "
        f"Lv{enemy.get('level', '?')} HP {enemy.get('hp', '?')}/{enemy.get('max_hp', '?')}"
    )


def party_by_slot(snapshot_dict: dict[str, Any]) -> dict[int, dict[str, Any]]:
    party = snapshot_dict.get("party")
    if not isinstance(party, list):
        return {}
    members: dict[int, dict[str, Any]] = {}
    for member in party:
        if not isinstance(member, dict):
            continue
        slot = member.get("slot")
        if isinstance(slot, int):
            members[slot] = member
    return members


def party_signature(party: dict[int, dict[str, Any]]) -> tuple[tuple[int, Any, Any], ...]:
    return tuple(
        (slot, member.get("species_id"), member.get("species_name"))
        for slot, member in sorted(party.items())
    )


def format_party_signature(party: dict[int, dict[str, Any]]) -> str:
    if not party:
        return "empty"
    return "; ".join(f"{slot}:{party_member_label(member)}" for slot, member in sorted(party.items()))


def party_member_label(member: dict[str, Any]) -> str:
    nickname = member.get("nickname")
    species = member.get("species_name") or "unknown"
    if nickname and nickname != species:
        return f"{nickname} ({species})"
    return str(species)


def move_names(member: dict[str, Any]) -> list[str]:
    moves = member.get("moves")
    if not isinstance(moves, list):
        return []
    names: list[str] = []
    for move in moves:
        if not isinstance(move, dict):
            continue
        move_id = int(move.get("move_id", 0) or 0)
        if not move_id:
            continue
        names.append(str(move.get("move_name") or f"move:{move_id}"))
    return names


def promoted_signals(snapshot_dict: dict[str, Any], screenshot_path: Path) -> list[dict[str, Any]]:
    position = snapshot_position(snapshot_dict)
    patch = approved_grass_patch_for_position(position)
    landmark_id = next(
        (
            landmark.id
            for landmark in (*CAPSULE_A_LANDMARKS.values(), *PEWTER_LANDMARKS.values())
            if at_landmark(position, landmark)
        ),
        None,
    )
    enemy = snapshot_dict.get("enemy") if isinstance(snapshot_dict.get("enemy"), dict) else None
    active = (
        snapshot_dict.get("active_party_member")
        if isinstance(snapshot_dict.get("active_party_member"), dict)
        else None
    )
    battle_ui = inspect_battle_ui_screenshot(screenshot_path)
    battle_dialogue_ready = (
        snapshot_dict.get("mode") == "battle"
        and snapshot_dict.get("battle_type_raw") not in {None, 0}
        and battle_ui.kind == "dialogue"
    )
    return [
        signal("mode", "Mode", snapshot_dict.get("mode"), "mode-and-ui-state-classification"),
        signal("battle_type_raw", "Battle Type", snapshot_dict.get("battle_type_raw"), "mode-and-ui-state-classification"),
        signal(
            "battle_ui",
            "Battle UI",
            f"{battle_ui.kind} / {battle_ui.cursor}",
            "battle-menu-and-cursor-detection",
        ),
        signal(
            "battle_dialogue_ready",
            "Battle Dialogue Ready",
            battle_dialogue_ready,
            "battle-dialogue-advancement-contract",
        ),
        signal(
            "position",
            "Position",
            position.format() if position else "unknown",
            "capsule-a-region-and-landmarks",
        ),
        signal(
            "capsule_a_allowed",
            "Capsule A Region",
            "inside" if is_allowed_position(position) else "outside",
            "capsule-a-region-and-landmarks",
        ),
        signal(
            "pewter_region",
            "Pewter Region",
            "inside" if position is not None and position.map_id in PEWTER_MAP_IDS else "outside",
            "pewter-region-navigation-contract",
        ),
        signal("landmark", "Landmark", landmark_id or "none", "capsule-a-region-and-landmarks"),
        signal(
            "grass_patch",
            "Grass Patch",
            patch.id if patch else "none",
            "grass-patch-and-encounter-search",
        ),
        signal(
            "in_approved_grass",
            "In Approved Grass",
            bool(patch and patch.contains(position)),
            "grass-patch-and-encounter-search",
        ),
        signal("poke_balls", "Poke Balls", poke_ball_count(snapshot_dict), "item-use-and-bag-selection"),
        signal(
            "active_battler",
            "Active Battler",
            active_summary(active),
            "party-switch-and-active-battler",
        ),
        signal(
            "enemy",
            "Enemy",
            enemy_summary(enemy),
            "battle-enemy-facts",
        ),
    ]


def skill_availability(snapshot_dict: dict[str, Any], screenshot_path: Path) -> list[dict[str, Any]]:
    mode = snapshot_dict.get("mode")
    battle_type = snapshot_dict.get("battle_type_raw")
    in_battle = mode == "battle" and battle_type not in {None, 0}
    post_catch_context = in_battle and battle_enemy_hp(snapshot_dict) > 0
    nickname_prompt_visible = post_catch_context and screenshot_has_nickname_prompt(screenshot_path)
    nickname_intro_visible = post_catch_context and screenshot_has_nickname_intro_dialogue(screenshot_path)
    naming_screen_visible = screenshot_has_naming_screen(screenshot_path)
    pokedex_page_visible = screenshot_has_pokedex_page(screenshot_path)
    pokedex_intro_visible = (
        battle_enemy_hp(snapshot_dict) > 0 and screenshot_has_pokedex_intro_dialogue(screenshot_path)
    )
    trainer_switch_prompt_visible = screenshot_has_trainer_switch_prompt(snapshot_dict, screenshot_path)
    move_learning_prompt_visible = screenshot_has_move_learning_prompt(snapshot_dict, screenshot_path)
    availability: list[dict[str, Any]] = []

    availability.append(skill_from_result("advance_dialogue", advance_dialogue(snapshot_dict, screenshot_path=screenshot_path)))
    availability.append(
        skill_from_result(
            "advance_battle_dialogue",
            advance_battle_dialogue(snapshot_dict, screenshot_path=screenshot_path),
            params={
                "requiredPromotions": [
                    "mode-and-ui-state-classification",
                    "battle-menu-and-cursor-detection",
                    "battle-dialogue-advancement-contract",
                ]
            },
        )
    )
    outcome_probe = resolve_battle_outcome_dialogue_bundle(
        snapshot_dict,
        screenshot_path=screenshot_path,
    )
    availability.append(
        skill_from_result(
            "resolve_battle_outcome_dialogue_bundle",
            outcome_probe,
            params={
                "requiredPromotions": [
                    "mode-and-ui-state-classification",
                    "battle-menu-and-cursor-detection",
                    "battle-dialogue-advancement-contract",
                    "party-switch-and-active-battler",
                ],
                "execution": "bounded_dialogue_bundle",
                "maxInputs": 16,
            },
        )
    )
    availability.append(
        skill_from_result("close_menu_or_cancel", close_menu_or_cancel(snapshot_dict, screenshot_path=screenshot_path))
    )
    availability.append(
        skill_from_result("recover_to_overworld", recover_to_overworld(snapshot_dict, screenshot_path=screenshot_path))
    )
    availability.append(
        skill_from_result(
            "heal_at_pokecenter",
            heal_at_pokecenter(snapshot_dict, screenshot_path=screenshot_path),
            params={"requiredPromotions": ["capsule-a-region-and-landmarks", "mode-and-ui-state-classification"]},
        )
    )
    mart_stock = stock_for_snapshot(snapshot_dict)
    default_mart_item = "Poke Ball" if any(item.name == "Poke Ball" for item in mart_stock) else (mart_stock[0].name if mart_stock else "Poke Ball")
    mart_purchase_probe = purchase_pokemart_item(
        snapshot_dict,
        item=default_mart_item,
        quantity=1,
        screenshot_path=screenshot_path,
    )
    availability.append(
        skill_from_result(
            "purchase_pokemart_item",
            mart_purchase_probe,
            params={
                "argsSchema": {
                    "item": "string item name exactly from itemNames",
                    "quantity": "integer number of single-item purchases to perform",
                },
                "exampleArgs": {"item": default_mart_item, "quantity": 99 if default_mart_item == "Poke Ball" else 1},
                "stock": [
                    {"itemId": item.item_id, "name": item.name, "price": item.price}
                    for item in mart_stock
                ],
                "itemNames": [item.name for item in mart_stock],
                "quantityPolicy": "Pokemon Red buys one item at a time; this skill repeats the purchase flow quantity times and stops when money runs out.",
                "requiredPromotions": ["mode-and-ui-state-classification", "mart-buy-menu-contract"],
            },
        )
    )
    if outcome_probe.status == "succeeded":
        suppress_skill(
            availability,
            "advance_battle_dialogue",
            reason=(
                "A bounded battle-outcome bundle is available and will stop before the next "
                "tactical, party, or choice surface."
            ),
        )
    npc_options = interaction_options(snapshot_dict)
    default_npc_target = default_interaction_target(snapshot_dict)
    npc_probe = talk_to_npc(
        snapshot_dict,
        target=default_npc_target or "",
        screenshot_path=screenshot_path,
    )
    availability.append(
        skill_from_result(
            "talk_to_npc",
            npc_probe,
            params={
                "argsSchema": {
                    "target": "NPC target id exactly from targets",
                },
                "exampleArgs": {"target": default_npc_target} if default_npc_target else {},
                "defaultTarget": default_npc_target,
                "targets": npc_options,
                "targetIds": [option["id"] for option in npc_options],
                "requiredPromotions": [
                    "mode-and-ui-state-classification",
                    "early-game-npc-interaction-contract",
                ],
            },
        )
    )
    availability.append(
        {
            "id": "literal_button_press",
            "label": SKILL_LABELS["literal_button_press"],
            "enabled": False,
            "reason": (
                "Literal controller input is an operator-only diagnostic escape hatch; "
                "the LLM Director must use a semantic skill."
            ),
            "status": "blocked",
            "params": {
                "argsSchema": {"button": "one of: a, b, up, down, left, right, start, select"},
                "exampleArgs": {"button": "a"},
                "buttons": list(DIRECTOR_BUTTONS),
            },
        }
    )
    availability.append(
        skill_from_result(
            "complete_prologue",
            complete_prologue(snapshot_dict, screenshot_path=screenshot_path),
            params={
                "argsSchema": {
                    "playerName": "uppercase A-Z player name, 1 to 7 characters",
                    "rivalName": "uppercase A-Z rival name, 1 to 7 characters",
                    "handoff": "red_house_2f or pallet_outside",
                },
                "exampleArgs": {"playerName": "RED", "rivalName": "BLUE", "handoff": "pallet_outside"},
                "defaultPlayerName": "RED",
                "defaultRivalName": "BLUE",
                "defaultHandoff": "pallet_outside",
                "requiredPromotions": ["prologue-menu-and-naming-contract", "pallet-region-navigation-contract"],
            },
        )
    )
    availability.append(
        skill_from_result(
            "choose_starter",
            choose_starter(snapshot_dict, starter="squirtle", screenshot_path=screenshot_path),
            params={
                "argsSchema": {
                    "starter": "bulbasaur, charmander, or squirtle",
                    "nickname": "optional uppercase A-Z nickname, 1 to 10 characters; omit to decline nickname",
                },
                "exampleArgs": {"starter": "squirtle"},
                "exampleArgsWithNickname": {"starter": "squirtle", "nickname": "SHELL"},
                "defaultStarter": "squirtle",
                "starters": ["bulbasaur", "charmander", "squirtle"],
                "nicknamePolicy": "If nickname is present, the starter will be nicknamed; if omitted, nickname is declined.",
                "requiredPromotions": ["oak-lab-starter-selection-contract"],
            },
        )
    )
    availability.append(
        skill_from_result(
            "navigate_within_viridian_forest_region",
            navigate_within_viridian_forest_region(
                snapshot_dict,
                target="forest_grass",
                screenshot_path=screenshot_path,
            ),
            params={
                "targets": [
                    "forest_grass",
                    "viridian_city",
                    "viridian_pokecenter",
                    "route_2",
                    "south_gate",
                    "mid_north",
                    "north_gate",
                    "north_gate_north",
                    "forest_north_exit",
                ]
            },
        )
    )
    pallet_options = pallet_target_options_for_current_map(snapshot_dict)
    default_pallet_target = default_pallet_navigation_target(snapshot_dict)
    pallet_result = navigate_within_pallet_region(snapshot_dict, target=default_pallet_target)
    availability.append(
        {
            "id": "navigate_within_pallet_region",
            "label": SKILL_LABELS["navigate_within_pallet_region"],
            "enabled": pallet_result.status == "succeeded",
            "reason": pallet_result.summary,
            "status": pallet_result.status,
            "params": {
                "argsSchema": {"target": "Pallet landmark id or alias; use one of targetIds when possible."},
                "exampleArgs": {"target": default_pallet_target},
                "defaultTarget": default_pallet_target,
                "currentMapTargets": pallet_options,
                "targetIds": [
                    "pallet_bedroom_entrance",
                    "pallet_bedroom_exit",
                    "pallet_home_1f_entrance",
                    "pallet_home_1f_exit",
                    "pallet_grass_entrance",
                    "pallet_oak_trigger",
                    "oaks_lab_entrance",
                    "oaks_lab_exit",
                    "oaks_lab_rival_trigger",
                    "oaks_lab_starter_table",
                    "rivals_home_entrance",
                    "rivals_home_exit",
                    "route_1_entrance",
                    "route_1_south",
                    "route_1_north_exit",
                    "viridian_city_south_entrance",
                    "viridian_mart_front_door",
                    "viridian_mart_entrance",
                    "viridian_mart_counter",
                ],
                "requiredPromotions": ["pallet-region-navigation-contract"],
            },
        }
    )
    pewter_options = pewter_target_options_for_current_map(snapshot_dict)
    default_pewter_target = default_pewter_navigation_target(snapshot_dict)
    pewter_result = navigate_within_pewter_region(
        snapshot_dict,
        target=default_pewter_target,
        screenshot_path=screenshot_path,
    )
    availability.append(
        {
            "id": "navigate_within_pewter_region",
            "label": SKILL_LABELS["navigate_within_pewter_region"],
            "enabled": pewter_result.status == "succeeded",
            "reason": pewter_result.summary,
            "status": pewter_result.status,
            "params": {
                "argsSchema": {"target": "Pewter landmark id or alias; use one of targetIds when possible."},
                "exampleArgs": {"target": default_pewter_target},
                "defaultTarget": default_pewter_target,
                "currentMapTargets": pewter_options,
                "targetIds": [
                    "viridian_forest_north_gate_exit",
                    "pewter_city_viridian_forest_exit",
                    "pewter_route2_grass",
                    "pewter_city_south_entrance",
                    "pewter_city_center",
                    "pewter_pokecenter_entrance",
                    "pewter_pokecenter_inside",
                    "pewter_pokecenter_counter",
                    "pewter_mart_entrance",
                    "pewter_mart_inside",
                    "pewter_mart_counter",
                    "pewter_gym_entrance",
                    "pewter_gym_inside",
                    "pewter_gym_trainer_pre_battle",
                    "pewter_gym_brock_pre_battle",
                    "pewter_city_route3_exit",
                    "pewter_museum_entrance",
                    "pewter_museum_bush",
                    "pewter_cut_bush",
                ],
                "requiredPromotions": ["pewter-region-navigation-contract"],
            },
        }
    )
    reorder_options = party_reorder_options(snapshot_dict)
    reorder_probe = None
    if reorder_options:
        first_target = reorder_options[0]["slot"]
        destination = 1 if first_target != 1 else min(len(reorder_options), 2)
        reorder_probe = overworld_rearrange_party(
            snapshot_dict,
            target=first_target,
            destination_slot=destination,
        )
    availability.append(
        {
            "id": "overworld_rearrange_party",
            "label": SKILL_LABELS["overworld_rearrange_party"],
            "enabled": bool(reorder_options and reorder_probe and reorder_probe.status == "succeeded"),
            "reason": reorder_probe.summary if reorder_probe else "Stable overworld with at least two party members is required.",
            "status": reorder_probe.status if reorder_probe else "blocked",
            "params": {
                "targets": reorder_options,
                "destinationSlots": [option["slot"] for option in reorder_options],
                "requiredPromotions": ["overworld-party-reorder-contract", "mode-and-ui-state-classification"],
            },
        }
    )
    position = snapshot_position(snapshot_dict)
    grass_patch = approved_grass_patch_for_position(position) or resolve_grass_patch("current_map")
    default_grass_patch = grass_patch.id if grass_patch else "current_map"
    grass_result = enter_grass_search_loop(snapshot_dict, patch="current_map")
    grass_enabled = grass_result.status == "succeeded" and not in_battle
    availability.append(
        {
            "id": "enter_grass_search_loop",
            "label": SKILL_LABELS["enter_grass_search_loop"],
            "enabled": grass_enabled,
            "reason": "Already in battle." if in_battle else grass_result.summary,
            "status": grass_result.status,
            "params": {
                "patches": [default_grass_patch],
                "defaultPatch": "current_map",
            },
        }
    )
    availability.append(
        skill_from_result(
            "handle_nickname_prompt",
            handle_nickname_prompt(snapshot_dict, screenshot_path=screenshot_path),
            params={
                "argsSchema": {"choice": "accept or decline"},
                "exampleArgs": {"choice": "decline"},
                "choices": ["decline", "accept"],
                "defaultChoice": "decline",
                "requiredPromotions": [
                    "post-catch-pokedex-registration-contract",
                    "nickname-prompt-detector",
                ],
            },
        )
    )
    availability.append(
        skill_from_result(
            "enter_nickname_text",
            enter_nickname_text(snapshot_dict, screenshot_path=screenshot_path, nickname="ABK"),
            params={
                "argsSchema": {
                    "nickname": "uppercase A-Z nickname, 1 to 10 characters; lowercase/user text will be normalized",
                },
                "exampleArgs": {"nickname": "ABK"},
                "defaultNickname": "ABK",
                "supportedPattern": "^[A-Z]{1,10}$",
                "requiredPromotions": ["nickname-entry-keyboard-contract"],
            },
        )
    )
    availability.append(skill_from_result("attempt_catch", attempt_catch(snapshot_dict, screenshot_path=screenshot_path)))
    availability.append(
        skill_from_result(
            "run_from_wild_battle",
            run_from_wild_battle(snapshot_dict, screenshot_path=screenshot_path),
            params={
                "requiredPromotions": [
                    "mode-and-ui-state-classification",
                    "battle-menu-and-cursor-detection",
                ],
                "usage": "Use to leave unwanted wild encounters; unavailable in trainer battles.",
            },
        )
    )

    move_options = active_move_options(snapshot_dict)
    move_probe = None
    if move_options:
        move_probe = use_move(snapshot_dict, requested_move=move_options[0]["name"], screenshot_path=screenshot_path)
    availability.append(
        {
            "id": "use_move",
            "label": SKILL_LABELS["use_move"],
            "enabled": bool(move_options and move_probe and move_probe.status == "succeeded"),
            "reason": move_probe.summary if move_probe else "No active move is available.",
            "status": move_probe.status if move_probe else "blocked",
            "params": {
                "argsSchema": {"move": "string move name or numeric move id; do not pass the whole move option object"},
                "exampleArgs": {"move": move_options[0]["name"]} if move_options else {},
                "moves": move_options,
                "moveNames": [option["name"] for option in move_options],
                "moveIds": [option["moveId"] for option in move_options],
            },
        }
    )

    target_options = switch_target_options(snapshot_dict)
    switch_probe = None
    if target_options:
        switch_probe = switch_party_member(
            snapshot_dict,
            target=target_options[0]["slot"],
            screenshot_path=screenshot_path,
        )
    availability.append(
        {
            "id": "switch_party_member",
            "label": SKILL_LABELS["switch_party_member"],
            "enabled": bool(target_options and switch_probe and switch_probe.status == "succeeded"),
            "reason": switch_probe.summary if switch_probe else "No non-active conscious party member is available.",
            "status": switch_probe.status if switch_probe else "blocked",
            "params": {
                "argsSchema": {"target": "party slot number, species name, or nickname; do not pass the whole target option object"},
                "exampleArgs": {"target": target_options[0]["slot"]} if target_options else {},
                "targets": target_options,
                "targetSlots": [option["slot"] for option in target_options],
                "targetNames": [
                    str(option.get("nickname") or option.get("species"))
                    for option in target_options
                    if option.get("nickname") or option.get("species")
                ],
            },
        }
    )
    trainer_switch_probe = handle_trainer_switch_prompt(
        snapshot_dict,
        choice="keep",
        screenshot_path=screenshot_path,
    )
    availability.append(
        skill_from_result(
            "handle_trainer_switch_prompt",
            trainer_switch_probe,
            params={
                "argsSchema": {
                    "choice": "keep or switch",
                    "target": "required with switch: party slot number, species, or nickname",
                },
                "exampleArgs": {"choice": "keep"},
                "exampleSwitchArgs": (
                    {"choice": "switch", "target": target_options[0]["slot"]}
                    if target_options
                    else None
                ),
                "choices": ["keep", "switch"],
                "targets": target_options,
                "requiredPromotions": [
                    "battle-dialogue-advancement-contract",
                    "party-switch-and-active-battler",
                ],
            },
        )
    )
    current_move_options = move_learning_options(snapshot_dict.get("active_party_member"))
    move_learning_probe = handle_move_learning_prompt(
        snapshot_dict,
        choice="skip",
        screenshot_path=screenshot_path,
    )
    availability.append(
        skill_from_result(
            "handle_move_learning_prompt",
            move_learning_probe,
            params={
                "argsSchema": {
                    "choice": "skip or replace",
                    "forgetMove": "required with replace: current move name or slot",
                },
                "exampleArgs": {"choice": "skip"},
                "exampleReplaceArgs": (
                    {"choice": "replace", "forgetMove": current_move_options[0]["name"]}
                    if current_move_options
                    else None
                ),
                "choices": ["skip", "replace"],
                "moves": current_move_options,
                "requiredPromotions": ["battle-dialogue-advancement-contract"],
            },
        )
    )
    if pokedex_page_visible or pokedex_intro_visible:
        for skill_id in ("attempt_catch", "use_move", "switch_party_member"):
            suppress_skill(
                availability,
                skill_id,
                reason="Post-catch Pokedex registration dialogue is visible; advance battle outcome dialogue.",
            )
    if nickname_intro_visible:
        for skill_id in (
            "advance_battle_dialogue",
            "resolve_battle_outcome_dialogue_bundle",
            "literal_button_press",
            "attempt_catch",
            "run_from_wild_battle",
            "use_move",
            "switch_party_member",
        ):
            suppress_skill(
                availability,
                skill_id,
                reason="Post-catch nickname intro dialogue is visible; use handle_nickname_prompt.",
            )
    if nickname_prompt_visible or naming_screen_visible:
        for skill_id in (
            "advance_battle_dialogue",
            "resolve_battle_outcome_dialogue_bundle",
            "literal_button_press",
            "attempt_catch",
            "run_from_wild_battle",
            "use_move",
            "switch_party_member",
        ):
            suppress_skill(
                availability,
                skill_id,
                reason=(
                    "Nickname prompt is a decision surface; use handle_nickname_prompt."
                    if nickname_prompt_visible
                    else "Naming keyboard is active; nickname text-entry support is required."
                ),
            )
    if trainer_switch_prompt_visible:
        for skill_id in (
            "advance_battle_dialogue",
            "resolve_battle_outcome_dialogue_bundle",
            "literal_button_press",
            "attempt_catch",
            "run_from_wild_battle",
            "use_move",
            "switch_party_member",
        ):
            suppress_skill(
                availability,
                skill_id,
                reason="Shift-style trainer switch prompt is visible; use handle_trainer_switch_prompt.",
            )
    if move_learning_prompt_visible:
        for skill_id in (
            "advance_battle_dialogue",
            "resolve_battle_outcome_dialogue_bundle",
            "literal_button_press",
            "attempt_catch",
            "run_from_wild_battle",
            "use_move",
            "switch_party_member",
        ):
            suppress_skill(
                availability,
                skill_id,
                reason="Four-move learning prompt is visible; use handle_move_learning_prompt.",
            )
    return availability


def signal(identifier: str, label: str, value: Any, promotion: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "value": value,
        "promotion": promotion,
    }


def skill_from_result(skill_id: str, result: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": skill_id,
        "label": SKILL_LABELS[skill_id],
        "enabled": result.status == "succeeded",
        "reason": result.summary,
        "status": result.status,
        "params": params or {},
    }


def suppress_skill(availability: list[dict[str, Any]], skill_id: str, *, reason: str) -> None:
    for skill in availability:
        if skill["id"] != skill_id:
            continue
        skill["enabled"] = False
        skill["reason"] = reason
        skill["status"] = "blocked"
        return


def active_summary(member: dict[str, Any] | None) -> str:
    if not member:
        return "none"
    return (
        f"{member.get('species_name', 'unknown')} "
        f"Lv{member.get('level', '?')} HP {member.get('hp', '?')}/{member.get('max_hp', '?')}"
    )


def enemy_summary(enemy: dict[str, Any] | None) -> str:
    if not enemy:
        return "none"
    return (
        f"{enemy.get('species_name', 'unknown')} "
        f"Lv{enemy.get('level', '?')} HP {enemy.get('hp', '?')}/{enemy.get('max_hp', '?')}"
    )


def battle_enemy_hp(snapshot_dict: dict[str, Any]) -> int:
    enemy = snapshot_dict.get("enemy")
    if not isinstance(enemy, dict):
        return 0
    try:
        return int(enemy.get("hp", 0) or 0)
    except (TypeError, ValueError):
        return 0


def active_move_options(snapshot_dict: dict[str, Any]) -> list[dict[str, Any]]:
    active = snapshot_dict.get("active_party_member")
    if not isinstance(active, dict):
        return []
    moves = active.get("moves")
    if not isinstance(moves, list):
        return []
    options = []
    for index, move in enumerate(moves, start=1):
        if not isinstance(move, dict):
            continue
        move_id = int(move.get("move_id", 0) or 0)
        pp = int(move.get("pp", 0) or 0)
        name = str(move.get("move_name", ""))
        if move_id and pp > 0:
            options.append({"slot": index, "name": name, "pp": pp, "moveId": move_id})
    return options


def normalize_requested_move_arg(value: Any) -> str | int | None:
    if isinstance(value, dict):
        for key in ("name", "moveName", "move_name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        for key in ("moveId", "move_id", "id"):
            candidate = value.get(key)
            if isinstance(candidate, int):
                return candidate
            if isinstance(candidate, str) and candidate.isdigit():
                return int(candidate)
        return None
    return value


def normalize_party_target_arg(value: Any) -> str | int | None:
    if isinstance(value, dict):
        slot = value.get("slot")
        if isinstance(slot, int):
            return slot
        if isinstance(slot, str) and slot.isdigit():
            return int(slot)
        for key in ("nickname", "species", "speciesName", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None
    return value


def normalize_shop_item_arg(args: dict[str, Any]) -> str:
    raw = args.get("item", args.get("itemName", args.get("name", "Poke Ball")))
    if isinstance(raw, dict):
        raw = raw.get("name") or raw.get("item") or raw.get("itemName")
    return normalize_shop_item(raw)


def normalize_nickname_choice_arg(args: dict[str, Any]) -> NicknameChoice:
    raw = args.get("choice", args.get("nicknameChoice", args.get("decision", args.get("answer", "decline"))))
    if isinstance(raw, bool):
        return "accept" if raw else "decline"
    value = str(raw).strip().lower()
    if value in {"accept", "yes", "y", "true", "nickname", "name"}:
        return "accept"
    return "decline"


def normalize_move_learning_choice_arg(args: dict[str, Any]) -> MoveLearningChoice:
    raw = args.get("choice", args.get("decision", args.get("response", "skip")))
    value = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if value in {"replace", "learn", "yes", "accept", "forget"}:
        return "replace"
    return "skip"


def normalize_trainer_switch_choice_arg(args: dict[str, Any]) -> TrainerSwitchChoice:
    raw = args.get("choice", args.get("decision", args.get("response", "keep")))
    value = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if value in {"switch", "change", "yes", "accept", "switch_pokemon"}:
        return "switch"
    return "keep"


def normalize_nickname_text_arg(args: dict[str, Any]) -> str:
    raw = args.get("nickname", args.get("nicknameText", args.get("text", args.get("name", ""))))
    if isinstance(raw, dict):
        raw = raw.get("nickname", raw.get("text", raw.get("name", "")))
    token = ""
    for char in str(raw).upper():
        if "A" <= char <= "Z":
            token += char
        elif token:
            break
    return token[:10]


def switch_target_options(snapshot_dict: dict[str, Any]) -> list[dict[str, Any]]:
    active_slot = snapshot_dict.get("active_party_slot")
    party = snapshot_dict.get("party")
    if not isinstance(party, list):
        return []
    options = []
    for member in party:
        if not isinstance(member, dict):
            continue
        slot = member.get("slot")
        hp = int(member.get("hp", 0) or 0)
        if slot == active_slot or hp <= 0:
            continue
        options.append(
            {
                "slot": slot,
                "species": member.get("species_name", "unknown"),
                "nickname": member.get("nickname"),
                "hp": hp,
                "maxHp": member.get("max_hp"),
            }
        )
    return options


def party_reorder_options(snapshot_dict: dict[str, Any]) -> list[dict[str, Any]]:
    party = snapshot_dict.get("party")
    if not isinstance(party, list):
        return []
    options = []
    for member in party:
        if not isinstance(member, dict):
            continue
        slot = member.get("slot")
        if not isinstance(slot, int):
            continue
        options.append(
            {
                "slot": slot,
                "species": member.get("species_name", "unknown"),
                "nickname": member.get("nickname"),
                "hp": int(member.get("hp", 0) or 0),
                "maxHp": member.get("max_hp"),
            }
        )
    return sorted(options, key=lambda item: item["slot"])


class DirectorPlayerHandler(BaseHTTPRequestHandler):
    player: DirectorPlayer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/", "/status", "/health"}:
            self.write_json({"error": "not found"}, status=404)
            return
        query = parse_qs(parsed.query)
        self.write_json(self.player.request_status(fresh=query.get("fresh", ["0"])[0] == "1"))

    def do_POST(self) -> None:
        try:
            body = self.read_json_body()
            if self.path == "/skill":
                self.write_json(self.player.request_execute_skill(str(body.get("skillId", "")), body.get("args") or {}))
                return
            if self.path == "/load-state":
                self.write_json(self.player.request_load_state(str(body.get("statePath", ""))))
                return
            if self.path == "/manual-input":
                self.write_json(self.player.request_manual_input(str(body.get("button", ""))))
                return
            if self.path == "/diagnostic-mode":
                self.write_json(self.player.request_diagnostic_mode(bool(body.get("enabled"))))
                return
            if self.path == "/capture-interpretation":
                self.write_json(
                    self.player.request_capture_interpretation(
                        str(body.get("title", "")),
                        str(body.get("description", "")),
                    )
                )
                return
            self.write_json({"error": "not found"}, status=404)
        except PermissionError as exc:
            self.write_json({"error": str(exc), "type": exc.__class__.__name__}, status=403)
        except FileNotFoundError as exc:
            self.write_json({"error": str(exc), "type": exc.__class__.__name__}, status=404)
        except RuntimeError as exc:
            self.write_json({"error": str(exc), "type": exc.__class__.__name__}, status=409)
        except (ValueError, json.JSONDecodeError) as exc:
            self.write_json({"error": str(exc), "type": exc.__class__.__name__}, status=400)
        except Exception as exc:
            self.write_json({"error": "Director player request failed.", "type": exc.__class__.__name__}, status=500)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0"))
        if length <= 0:
            return {}
        payload = self.rfile.read(length)
        return json.loads(payload.decode("utf-8"))

    def write_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = datetime.now(UTC).isoformat()
        print(f"[{timestamp}] {self.address_string()} {format % args}")


def serve(config: DirectorPlayerConfig) -> None:
    rom = fingerprint_rom(config.rom_path)
    pyboy = open_emulator(rom.path, window=config.window)
    player = DirectorPlayer(pyboy=pyboy, rom=rom, config=config)
    DirectorPlayerHandler.player = player
    server = ThreadingHTTPServer((config.host, config.port), DirectorPlayerHandler)
    server_thread = threading.Thread(target=server.serve_forever, name="director-player-http", daemon=True)
    print(f"Director player listening on http://{config.host}:{config.port}")
    print(f"ROM: {rom.path}")
    if config.state_path:
        print(f"Initial state: {config.state_path}")
    try:
        server_thread.start()
        player.run_main_loop()
    except KeyboardInterrupt:
        print("Stopping director player...")
    finally:
        player.stop()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


def parse_args() -> DirectorPlayerConfig:
    parser = argparse.ArgumentParser(description="Run a local PyBoy sidecar controlled by the lab UI Director page.")
    parser.add_argument("--rom", default="research/PokemonRed.gb")
    parser.add_argument("--state", help="Optional .state file to load before serving.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--window", choices=["SDL2", "null"], default="SDL2")
    parser.add_argument("--render", choices=["true", "false", "auto"], default="auto")
    parser.add_argument("--run-root", default="research/artifacts/director-player-runs")
    parser.add_argument("--status-dir", default="research/artifacts/director-player")
    parser.add_argument("--post-load-settle-frames", type=int, default=60)
    parser.add_argument("--idle-tick-hz", type=int, default=60)
    parser.add_argument("--emulation-speed", type=int, default=1)
    parser.add_argument(
        "--status-period-seconds",
        type=float,
        default=5.0,
        help="Minimum seconds between expensive status refreshes while idle.",
    )
    parser.add_argument(
        "--slow-tick-ms",
        type=float,
        default=120.0,
        help="Log a performance warning when an idle PyBoy tick exceeds this duration; set 0 to disable.",
    )
    parser.add_argument(
        "--slow-status-ms",
        type=float,
        default=200.0,
        help="Log a performance warning when a fresh status build exceeds this duration; set 0 to disable.",
    )
    parser.add_argument(
        "--operations-control",
        default="research/artifacts/operations/control.json",
        help="Shared Operations control file; pass an empty value to disable integration.",
    )
    args = parser.parse_args()
    render = args.window == "SDL2" if args.render == "auto" else args.render == "true"
    return DirectorPlayerConfig(
        rom_path=Path(args.rom).resolve(),
        state_path=Path(args.state).resolve() if args.state else None,
        host=args.host,
        port=args.port,
        window=args.window,
        render=render,
        run_root=Path(args.run_root).resolve(),
        status_dir=Path(args.status_dir).resolve(),
        post_load_settle_frames=args.post_load_settle_frames,
        idle_tick_hz=args.idle_tick_hz,
        emulation_speed=args.emulation_speed,
        status_period_seconds=args.status_period_seconds,
        slow_tick_ms=args.slow_tick_ms,
        slow_status_ms=args.slow_status_ms,
        operations_control_path=Path(args.operations_control).resolve() if args.operations_control else None,
    )


def main() -> int:
    serve(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
