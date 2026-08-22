from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from pokemon_player import memory_map as mm
from pokemon_player.battle_ui import inspect_battle_ui_screenshot
from pokemon_player.pyboy_lab import load_state, save_screenshot, save_state, snapshot
from pokemon_player.skill_execution import (
    RELEASE_EVENTS,
    PRESS_EVENTS,
    release_all_window_inputs,
    send_window_event,
)
from pokemon_player.skills.attempt_catch import poke_ball_count
from pokemon_player.snapshot_io import snapshot_to_dict

try:
    from gymnasium import Env as _GymEnv
except ImportError:
    _GymEnv = object


ACTION_NAMES = ("down", "left", "right", "up", "a", "b")
DEFAULT_SCREEN_SHAPE = (72, 80)
FACT_VECTOR_LEN = 29
INVENTORY_OBS_SLOTS = 6
UI_KIND_CODES = {
    "unknown": 0,
    "action_menu": 1,
    "item_menu": 2,
    "dialogue": 3,
    "move_menu": 4,
    "party_menu": 5,
}
UI_CURSOR_CODES = {
    "unknown": 0,
    "fight": 1,
    "item": 2,
    "pkmn": 3,
    "run": 4,
    "move_1": 5,
    "move_2": 6,
    "move_3": 7,
    "move_4": 8,
}
BALL_ITEM_IDS = {0x01, 0x02, 0x03, 0x04}


@dataclass(frozen=True)
class BattleMenuRewardConfig:
    ball_decreased: float = 10.0
    throw_initiated: float = 12.0
    catch_succeeded: float = 15.0
    battle_ended_without_throw: float = -20.0
    enemy_hp_decreased: float = -25.0
    invalid_item_used: float = -15.0
    unsafe_battle_menu_select: float = -15.0
    item_menu_backtrack: float = -8.0
    player_hp_decreased: float = -1.0
    action_menu_item_selected: float = 0.75
    ball_item_selected: float = 4.0
    ui_progress_delta: float = 0.25
    expert_action: float = 0.15
    stagnant: float = -0.03
    step: float = -0.01
    timeout: float = -1.0


@dataclass(frozen=True)
class BattleMenuEnvConfig:
    rom_path: Path
    state_paths: tuple[Path, ...]
    window: str = "SDL2"
    render: bool = True
    action_frames: int = 48
    release_frame: int = 8
    settle_frames: int = 30
    max_steps: int = 48
    emulation_speed: int = 0
    screenshot_root: Path | None = None
    reward: BattleMenuRewardConfig = field(default_factory=BattleMenuRewardConfig)


@dataclass(frozen=True)
class BattleMenuFacts:
    mode: str
    battle_type_raw: int
    poke_balls: int
    all_balls: int
    party_count: int
    party_hp: int
    enemy_hp: int
    enemy_max_hp: int
    ui_kind: str
    ui_cursor: str
    bag_cursor_index: int = 0
    selected_item_id: int = 0
    selected_item_quantity: int = 0
    first_item_ids: tuple[int, ...] = ()
    first_item_quantities: tuple[int, ...] = ()
    inventory_item_count: int = 0
    best_ball_index: int = -1
    in_item_flow: bool = False
    throw_initiated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "battle_type_raw": self.battle_type_raw,
            "poke_balls": self.poke_balls,
            "all_balls": self.all_balls,
            "party_count": self.party_count,
            "party_hp": self.party_hp,
            "enemy_hp": self.enemy_hp,
            "enemy_max_hp": self.enemy_max_hp,
            "ui_kind": self.ui_kind,
            "ui_cursor": self.ui_cursor,
            "bag_cursor_index": self.bag_cursor_index,
            "selected_item_id": self.selected_item_id,
            "selected_item_quantity": self.selected_item_quantity,
            "first_item_ids": list(self.first_item_ids),
            "first_item_quantities": list(self.first_item_quantities),
            "inventory_item_count": self.inventory_item_count,
            "best_ball_index": self.best_ball_index,
            "in_item_flow": self.in_item_flow,
            "throw_initiated": self.throw_initiated,
        }


class BattleMenuThrowEnv(_GymEnv):
    """Tiny PyBoy environment for learning to navigate battle menus to throw a ball."""

    metadata = {"render_modes": ["rgb_array"]}

    def __init__(self, config: BattleMenuEnvConfig, *, pyboy: object | None = None) -> None:
        self.config = config
        self.pyboy = pyboy if pyboy is not None else self._open_pyboy()
        self._owns_pyboy = pyboy is None
        self.step_count = 0
        self.episode_id = ""
        self.state_path: Path | None = None
        self.initial_facts: BattleMenuFacts | None = None
        self.previous_facts: BattleMenuFacts | None = None
        self.trace: list[dict[str, Any]] = []
        self._last_screenshot_path: Path | None = None
        self._item_menu_steps = 0
        self._in_item_flow = False
        self._item_flow_a_presses = 0
        self._throw_initiated = False
        self._bag_cursor_index = 0
        self._init_gym_spaces()

    def _open_pyboy(self) -> object:
        from pokemon_player.pyboy_lab import open_emulator

        pyboy = open_emulator(self.config.rom_path, window=self.config.window)
        if hasattr(pyboy, "set_emulation_speed"):
            pyboy.set_emulation_speed(self.config.emulation_speed)
        return pyboy

    def _init_gym_spaces(self) -> None:
        try:
            from gymnasium import spaces
        except ImportError:
            self.action_space = None
            self.observation_space = None
            return

        self.action_space = spaces.Discrete(len(ACTION_NAMES))
        self.observation_space = spaces.Dict(
            {
                "screen": spaces.Box(
                    low=0,
                    high=255,
                    shape=(DEFAULT_SCREEN_SHAPE[0] * DEFAULT_SCREEN_SHAPE[1],),
                    dtype=np.uint8,
                ),
                "facts": spaces.Box(low=0, high=255, shape=(8,), dtype=np.uint8),
                "state": spaces.Box(low=0, high=255, shape=(FACT_VECTOR_LEN,), dtype=np.uint8),
            }
        )

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        rng = random.Random(seed)
        options = options or {}
        state_path = Path(options["state_path"]) if "state_path" in options else rng.choice(
            self.config.state_paths
        )
        load_state(self.pyboy, state_path)
        release_all_window_inputs(self.pyboy)
        self.pyboy.tick(2, self.config.render)
        self.pyboy.tick(self.config.settle_frames, self.config.render)
        self.step_count = 0
        self.episode_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.state_path = state_path
        self.trace = []
        self._item_menu_steps = 0
        self._in_item_flow = False
        self._item_flow_a_presses = 0
        self._throw_initiated = False
        self._bag_cursor_index = 0
        self.initial_facts = self._facts()
        self.previous_facts = self.initial_facts
        obs = self._observation()
        return obs, {"state_path": str(state_path), "facts": self.initial_facts.to_dict()}

    def begin_current_state(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Start an episode from the emulator's current state without loading a savestate."""
        release_all_window_inputs(self.pyboy)
        self.pyboy.tick(2, self.config.render)
        self.pyboy.tick(self.config.settle_frames, self.config.render)
        self.step_count = 0
        self.episode_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.state_path = None
        self.trace = []
        self._item_menu_steps = 0
        self._in_item_flow = False
        self._item_flow_a_presses = 0
        self._throw_initiated = False
        self._bag_cursor_index = 0
        self.initial_facts = self._facts()
        self.previous_facts = self.initial_facts
        obs = self._observation()
        return obs, {"state_path": None, "facts": self.initial_facts.to_dict()}

    def step(self, action: int) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        if action < 0 or action >= len(ACTION_NAMES):
            raise ValueError(f"action must be between 0 and {len(ACTION_NAMES) - 1}")
        if self.initial_facts is None or self.previous_facts is None:
            raise RuntimeError("reset() must be called before step().")

        previous = self.previous_facts
        action_name = ACTION_NAMES[action]
        valid_actions = valid_action_names_for(
            previous,
            item_menu_steps=self._item_menu_steps,
            in_item_flow=self._in_item_flow,
        )
        expert_action = expert_action_for(
            previous,
            item_menu_steps=self._item_menu_steps,
            in_item_flow=self._in_item_flow,
        )
        self._run_action(action_name)
        if previous.ui_kind == "item_menu" or (
            self._in_item_flow and action_name in {"up", "down"}
        ):
            self._update_bag_cursor(action_name)
        self.step_count += 1
        current = self._facts()
        self.previous_facts = current
        reward, reward_parts, terminated = score_transition(
            initial=self.initial_facts,
            previous=previous,
            current=current,
            config=self.config.reward,
        )
        truncated = self.step_count >= self.config.max_steps
        if truncated and not terminated:
            reward += self.config.reward.timeout
            reward_parts["timeout"] = self.config.reward.timeout
        if action_name == expert_action:
            reward += self.config.reward.expert_action
            reward_parts["expert_action"] = self.config.reward.expert_action
        if facts_are_stagnant(previous, current):
            reward += self.config.reward.stagnant
            reward_parts["stagnant"] = self.config.reward.stagnant
        action_menu_item_selected = (
            previous.ui_kind == "action_menu"
            and previous.ui_cursor == "item"
            and action_name == "a"
        )
        ball_item_selected = (
            action_name == "a"
            and previous.selected_item_id in BALL_ITEM_IDS
            and previous.selected_item_quantity > 0
            and (previous.ui_kind == "item_menu" or self._in_item_flow)
        )
        if action_menu_item_selected:
            reward += self.config.reward.action_menu_item_selected
            reward_parts["action_menu_item_selected"] = (
                self.config.reward.action_menu_item_selected
            )
        if ball_item_selected:
            reward += self.config.reward.ball_item_selected
            reward_parts["ball_item_selected"] = self.config.reward.ball_item_selected
        invalid_item_used = (
            previous.ui_kind == "item_menu"
            and action_name == "a"
            and previous.selected_item_id not in BALL_ITEM_IDS
        )
        unsafe_battle_menu_select = (
            previous.ui_kind == "action_menu"
            and previous.ui_cursor in {"fight", "pkmn", "run"}
            and action_name == "a"
        )
        item_menu_backtrack = previous.ui_kind == "item_menu" and action_name == "b"
        if invalid_item_used:
            reward += self.config.reward.invalid_item_used
            reward_parts["invalid_item_used"] = self.config.reward.invalid_item_used
            terminated = True
        if unsafe_battle_menu_select:
            reward += self.config.reward.unsafe_battle_menu_select
            reward_parts["unsafe_battle_menu_select"] = (
                self.config.reward.unsafe_battle_menu_select
            )
            terminated = True
        if item_menu_backtrack:
            reward += self.config.reward.item_menu_backtrack
            reward_parts["item_menu_backtrack"] = self.config.reward.item_menu_backtrack
            terminated = True
        if self._in_item_flow and action_name == "a":
            self._item_flow_a_presses += 1
        throw_initiated_now = False
        if ball_item_selected and not self._throw_initiated:
            self._throw_initiated = True
            throw_initiated_now = True
            reward += self.config.reward.throw_initiated
            reward_parts["throw_initiated"] = self.config.reward.throw_initiated
            terminated = True
        elif (
            self._in_item_flow
            and not self._throw_initiated
            and self._item_flow_a_presses >= 2
            and current.ui_kind in {"dialogue", "unknown"}
            and (previous.selected_item_id in BALL_ITEM_IDS or current.selected_item_id in BALL_ITEM_IDS)
        ):
            self._throw_initiated = True
            throw_initiated_now = True
            reward += self.config.reward.throw_initiated
            reward_parts["throw_initiated"] = self.config.reward.throw_initiated
            terminated = True
        if action_menu_item_selected:
            self._in_item_flow = True
            # The battle bag remembers its cursor between uses. Once ITEM is
            # selected, refresh facts with item-flow context so CURRENT_MENU_ITEM
            # becomes authoritative even when the first rendered bag frame is
            # still visually classified as the action menu.
            current = self._facts()
        if current.ui_kind == "item_menu":
            self._in_item_flow = True
            current = self._facts()
        stale_item_flow = (
            self._in_item_flow
            and current.ui_kind == "action_menu"
            and current.selected_item_id not in BALL_ITEM_IDS
            and current.best_ball_index >= 0
        )
        if (
            (
                current.ui_kind == "action_menu"
                and not action_menu_item_selected
                and not throw_initiated_now
                and not stale_item_flow
            )
            or current.all_balls < self.initial_facts.all_balls
        ):
            self._in_item_flow = False
            self._item_flow_a_presses = 0
        if previous.ui_kind == "item_menu":
            self._item_menu_steps += 1
        elif current.ui_kind != "item_menu":
            self._item_menu_steps = 0

        self.previous_facts = current

        info = {
            "action_name": action_name,
            "expert_action": expert_action,
            "valid_actions": valid_actions,
            "throw_initiated": self._throw_initiated,
            "facts": current.to_dict(),
            "reward_parts": reward_parts,
            "terminated_reason": (
                "invalid_item_used"
                if invalid_item_used
                else "unsafe_battle_menu_select"
                if unsafe_battle_menu_select
                else "item_menu_backtrack"
                if item_menu_backtrack
                else "throw_initiated"
                if throw_initiated_now
                else terminal_reason(self.initial_facts, current, previous=previous)
            )
            if terminated
            else None,
        }
        self.trace.append(
            {
                "step": self.step_count,
                "action": action,
                "action_name": action_name,
                "reward": reward,
                "reward_parts": reward_parts,
                "throw_initiated": self._throw_initiated,
                "facts": current.to_dict(),
            }
        )
        return self._observation(), reward, terminated, truncated, info

    def _update_bag_cursor(self, action_name: str) -> None:
        inventory_size = self._bag_cursor_item_count()
        if action_name == "down":
            self._bag_cursor_index = (self._bag_cursor_index + 1) % inventory_size
        elif action_name == "up":
            self._bag_cursor_index = (self._bag_cursor_index - 1) % inventory_size

    def _bag_cursor_item_count(self) -> int:
        inventory_size = self.previous_facts.inventory_item_count if self.previous_facts else 0
        return max(inventory_size + 1, 1)

    def close(self) -> None:
        if self._owns_pyboy:
            self.pyboy.stop(False)

    def save_episode(self, output_dir: str | Path) -> dict[str, Any]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        report = {
            "schema": "battle_menu_trace_v1",
            "created_utc": datetime.now(UTC).isoformat(),
            "state_path": str(self.state_path) if self.state_path else None,
            "steps": self.trace,
            "throw_initiated": any(step.get("throw_initiated") for step in self.trace),
            "initial_facts": self.initial_facts.to_dict() if self.initial_facts else None,
            "final_facts": self.previous_facts.to_dict() if self.previous_facts else None,
        }
        save_state(self.pyboy, output / "final.state")
        save_screenshot(self.pyboy, output / "final.png")
        (output / "trace.json").write_text(json.dumps(report, indent=2, sort_keys=True))
        return report

    def _run_action(self, action_name: str) -> None:
        release_all_window_inputs(self.pyboy)
        self.pyboy.tick(1, self.config.render)
        send_window_event(self.pyboy, PRESS_EVENTS[action_name])
        for frame in range(self.config.action_frames):
            if frame == self.config.release_frame:
                send_window_event(self.pyboy, RELEASE_EVENTS[action_name])
            self.pyboy.tick(1, self.config.render)
        if self.config.release_frame >= self.config.action_frames:
            send_window_event(self.pyboy, RELEASE_EVENTS[action_name])

    def _facts(self) -> BattleMenuFacts:
        snap = snapshot_to_dict(snapshot(self.pyboy))
        screenshot_path = self._scratch_screenshot_path()
        save_screenshot(self.pyboy, screenshot_path)
        ui = inspect_battle_ui_screenshot(screenshot_path)
        party_hp = sum(int(member.get("hp", 0)) for member in snap.get("party", []))
        inventory = snap.get("inventory", [])
        if ui.kind == "item_menu" or self._in_item_flow:
            self._bag_cursor_index = normalize_bag_cursor_index(
                int(self.pyboy.memory[mm.CURRENT_MENU_ITEM]),
                len(inventory),
            )
        item_ids, item_quantities = inventory_prefix(inventory, INVENTORY_OBS_SLOTS)
        selected_item_id, selected_item_quantity = selected_inventory_item(
            inventory,
            self._bag_cursor_index,
        )
        all_balls = sum(
            int(item.get("quantity", 0))
            for item in inventory
            if isinstance(item, dict) and int(item.get("item_id", 0)) in BALL_ITEM_IDS
        )
        return BattleMenuFacts(
            mode=str(snap.get("mode", "unknown")),
            battle_type_raw=int(snap.get("battle_type_raw", 0)),
            poke_balls=poke_ball_count(snap),
            all_balls=all_balls,
            party_count=len(snap.get("party", [])),
            party_hp=party_hp,
            enemy_hp=read_u16be(self.pyboy.memory, mm.ENEMY_BATTLE_HP),
            enemy_max_hp=read_u16be(self.pyboy.memory, mm.ENEMY_BATTLE_MAX_HP),
            ui_kind=ui.kind,
            ui_cursor=ui.cursor,
            bag_cursor_index=self._bag_cursor_index,
            selected_item_id=selected_item_id,
            selected_item_quantity=selected_item_quantity,
            first_item_ids=item_ids,
            first_item_quantities=item_quantities,
            inventory_item_count=len(inventory),
            best_ball_index=best_ball_inventory_index(inventory),
            in_item_flow=self._in_item_flow,
            throw_initiated=self._throw_initiated,
        )

    def _observation(self) -> dict[str, Any]:
        screen = self._screen_array()
        facts = self.previous_facts or self._facts()
        return {
            "screen": screen,
            "facts": np.array(
                [
                    min(facts.poke_balls, 255),
                    min(facts.all_balls, 255),
                    min(facts.party_count, 255),
                    min(facts.party_hp, 255),
                    min(facts.enemy_hp, 255),
                    min(facts.enemy_max_hp, 255),
                    min(facts.battle_type_raw, 255),
                    min(self.step_count, 255),
                ],
                dtype=np.uint8,
            ),
            "state": structured_state_vector(facts, self.step_count),
        }

    def _screen_array(self) -> np.ndarray:
        image = self.pyboy.screen.image
        if callable(image):
            image = image()
        gray = image.convert("L").resize((DEFAULT_SCREEN_SHAPE[1], DEFAULT_SCREEN_SHAPE[0]))
        return np.asarray(gray, dtype=np.uint8).reshape(-1)

    def _scratch_screenshot_path(self) -> Path:
        root = self.config.screenshot_root or Path("research") / "artifacts" / "battle-menu-tmp"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{id(self)}.png"
        self._last_screenshot_path = path
        return path


def score_transition(
    *,
    initial: BattleMenuFacts,
    previous: BattleMenuFacts,
    current: BattleMenuFacts,
    config: BattleMenuRewardConfig,
) -> tuple[float, dict[str, float], bool]:
    parts: dict[str, float] = {"step": config.step}
    terminated = False

    if current.all_balls < previous.all_balls:
        parts["ball_decreased"] = config.ball_decreased
        terminated = True
        if current.party_count > initial.party_count:
            parts["catch_succeeded"] = config.catch_succeeded

    progress_delta = ui_progress_score(current) - ui_progress_score(previous)
    if progress_delta:
        parts["ui_progress_delta"] = config.ui_progress_delta * progress_delta

    if current.enemy_hp < previous.enemy_hp:
        parts["enemy_hp_decreased"] = config.enemy_hp_decreased
        terminated = True

    if current.party_hp < previous.party_hp:
        parts["player_hp_decreased"] = config.player_hp_decreased

    ended_without_throw = (
        previous.mode == "battle"
        and current.mode != "battle"
        and current.all_balls >= initial.all_balls
    )
    if ended_without_throw:
        parts["battle_ended_without_throw"] = config.battle_ended_without_throw
        terminated = True

    return sum(parts.values()), parts, terminated


def structured_state_vector(facts: BattleMenuFacts, step_count: int) -> np.ndarray:
    values = [
        facts.poke_balls,
        facts.all_balls,
        facts.party_count,
        facts.party_hp,
        facts.enemy_hp,
        facts.enemy_max_hp,
        facts.battle_type_raw,
        step_count,
        UI_KIND_CODES.get(facts.ui_kind, 0),
        UI_CURSOR_CODES.get(facts.ui_cursor, 0),
        facts.bag_cursor_index,
        facts.selected_item_id,
        facts.selected_item_quantity,
        facts.best_ball_index if facts.best_ball_index >= 0 else 255,
        int(facts.in_item_flow),
        int(facts.throw_initiated),
    ]
    values.extend(facts.first_item_ids[:INVENTORY_OBS_SLOTS])
    values.extend(facts.first_item_quantities[:INVENTORY_OBS_SLOTS])
    values.append(1 if facts.selected_item_id in BALL_ITEM_IDS else 0)
    if len(values) != FACT_VECTOR_LEN:
        raise AssertionError(f"structured state vector length drifted to {len(values)}")
    return np.array([min(max(int(value), 0), 255) for value in values], dtype=np.uint8)


def inventory_prefix(inventory: Any, length: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    ids: list[int] = []
    quantities: list[int] = []
    if isinstance(inventory, list):
        for item in inventory[:length]:
            if isinstance(item, dict):
                ids.append(int(item.get("item_id", 0)))
                quantities.append(int(item.get("quantity", 0)))
    while len(ids) < length:
        ids.append(0)
        quantities.append(0)
    return tuple(ids), tuple(quantities)


def selected_inventory_item(inventory: Any, index: int) -> tuple[int, int]:
    if not isinstance(inventory, list) or index < 0 or index >= len(inventory):
        return 0, 0
    item = inventory[index]
    if not isinstance(item, dict):
        return 0, 0
    return int(item.get("item_id", 0)), int(item.get("quantity", 0))


def best_ball_inventory_index(inventory: Any) -> int:
    if not isinstance(inventory, list):
        return -1
    ball_priority = {0x01: 0, 0x02: 1, 0x03: 2, 0x04: 3}
    candidates: list[tuple[int, int]] = []
    for index, item in enumerate(inventory):
        if not isinstance(item, dict):
            continue
        item_id = int(item.get("item_id", 0))
        quantity = int(item.get("quantity", 0))
        if item_id in ball_priority and quantity > 0:
            candidates.append((ball_priority[item_id], index))
    if not candidates:
        return -1
    return min(candidates)[1]


def ui_progress_score(facts: BattleMenuFacts) -> int:
    if facts.ui_kind == "item_menu":
        return 3
    if facts.ui_kind == "action_menu" and facts.ui_cursor == "item":
        return 2
    if facts.ui_kind == "action_menu":
        return 1
    if facts.ui_kind == "move_menu":
        return -1
    return 0


def expert_action_for(
    facts: BattleMenuFacts,
    *,
    item_menu_steps: int = 0,
    in_item_flow: bool = False,
) -> str:
    return valid_action_names_for(
        facts,
        item_menu_steps=item_menu_steps,
        in_item_flow=in_item_flow,
    )[0]


def valid_action_names_for(
    facts: BattleMenuFacts,
    *,
    item_menu_steps: int = 0,
    in_item_flow: bool = False,
) -> tuple[str, ...]:
    if in_item_flow and facts.selected_item_id not in BALL_ITEM_IDS and facts.best_ball_index >= 0:
        if facts.bag_cursor_index < facts.best_ball_index:
            return ("down",)
        if facts.bag_cursor_index > facts.best_ball_index:
            return ("up",)
        return ("a",)
    if in_item_flow and facts.ui_kind == "unknown":
        return ("a",)
    if facts.ui_kind == "dialogue":
        return ("a",)
    if facts.ui_kind == "item_menu":
        if facts.selected_item_id in BALL_ITEM_IDS and facts.selected_item_quantity > 0:
            return ("a",)
        if facts.best_ball_index >= 0:
            if facts.bag_cursor_index < facts.best_ball_index:
                return ("down",)
            if facts.bag_cursor_index > facts.best_ball_index:
                return ("up",)
            return ("a",)
        # Fallback for older captures/tests where item identity was not yet
        # promoted into the observation. Current known states put Town Map above
        # Poke Ball, so the historical route is down, then confirm.
        return ("down",) if item_menu_steps == 0 else ("a",)
    if facts.ui_kind == "move_menu":
        if facts.ui_cursor == "move_1":
            return ("a",)
        if facts.ui_cursor in {"move_2", "move_3", "move_4"}:
            return ("up",)
        return ("up",)
    if facts.ui_kind == "party_menu":
        return ("b",)
    if facts.ui_kind == "action_menu":
        if facts.ui_cursor == "fight":
            return ("down",)
        if facts.ui_cursor == "item":
            return ("a",)
        if facts.ui_cursor == "pkmn":
            return ("left",)
        if facts.ui_cursor == "run":
            return ("left",)
    return ("b",)


def valid_action_mask_for(
    facts: BattleMenuFacts,
    *,
    item_menu_steps: int = 0,
    in_item_flow: bool = False,
) -> np.ndarray:
    valid_names = set(
        valid_action_names_for(
            facts,
            item_menu_steps=item_menu_steps,
            in_item_flow=in_item_flow,
        )
    )
    return np.array([name in valid_names for name in ACTION_NAMES], dtype=np.bool_)


def facts_are_stagnant(previous: BattleMenuFacts, current: BattleMenuFacts) -> bool:
    return (
        previous.mode == current.mode
        and previous.battle_type_raw == current.battle_type_raw
        and previous.all_balls == current.all_balls
        and previous.party_count == current.party_count
        and previous.party_hp == current.party_hp
        and previous.enemy_hp == current.enemy_hp
        and previous.ui_kind == current.ui_kind
        and previous.ui_cursor == current.ui_cursor
    )


def terminal_reason(
    initial: BattleMenuFacts,
    current: BattleMenuFacts,
    *,
    previous: BattleMenuFacts | None = None,
) -> str | None:
    if previous is not None and current.enemy_hp < previous.enemy_hp:
        return "enemy_hp_decreased"
    if current.all_balls < initial.all_balls:
        return "ball_decreased"
    if current.mode != "battle":
        return "battle_ended"
    return None


def read_u16be(memory: object, address: int) -> int:
    return (int(memory[address]) << 8) | int(memory[address + 1])


def normalize_bag_cursor_index(raw_index: int, inventory_slots: int) -> int:
    return raw_index % max(inventory_slots + 1, 1)
