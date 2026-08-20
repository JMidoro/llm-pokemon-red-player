from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import ButtonInput, load_state, open_emulator, save_screenshot, save_state, snapshot  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict  # noqa: E402


DEFAULT_ROM = ROOT / "research" / "PokemonRed.gb"
DEFAULT_STATE = ROOT / "research" / "golden-states" / "local" / "pallet_overworld_started.state"


@dataclass(frozen=True)
class WatchRange:
    name: str
    start: int
    end: int


@dataclass(frozen=True)
class ProbeAction:
    name: str
    description: str
    trace: tuple[ButtonInput, ...]
    capture_before: bool = True
    capture_after: bool = True


WATCH_RANGES = (
    WatchRange("missable_objects_flags", 0xD5A6, 0xD5C5),
    WatchRange("town_map_flag", 0xD5F3, 0xD5F3),
    WatchRange("oaks_parcel_flag", 0xD60D, 0xD60D),
    WatchRange("early_story_event_area", 0xD700, 0xD80F),
    WatchRange("mewtwo_ss_anne_late_story_spot_checks", 0xD803, 0xD85F),
    WatchRange("party_inventory_badges", 0xD163, 0xD356),
    WatchRange("map_position", 0xD35E, 0xD363),
    WatchRange("battle_mode", 0xD057, 0xD05E),
    WatchRange("menu_dialogue_cursor", 0xCC24, 0xCC2F),
)

STORY_TRIGGER_WATCHES = {
    "missable_objects_flags",
    "town_map_flag",
    "oaks_parcel_flag",
    "early_story_event_area",
    "mewtwo_ss_anne_late_story_spot_checks",
    "party_inventory_badges",
    "battle_mode",
    "menu_dialogue_cursor",
}


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def nav(button: str, *, settle: int = 72) -> ButtonInput:
    return ButtonInput(button, hold_frames=8, settle_frames=settle)


def tap(button: str, *, settle: int = 36) -> ButtonInput:
    return ButtonInput(button, hold_frames=8, settle_frames=settle)


def repeat(step: ButtonInput, count: int) -> tuple[ButtonInput, ...]:
    return tuple(step for _ in range(count))


def pallet_oak_trigger_plan() -> list[ProbeAction]:
    route = (
        "down",
        "down",
        "right",
        "right",
        "right",
        "right",
        "right",
        "right",
        "right",
        "up",
        "up",
        "up",
        "up",
        "up",
        "up",
        "up",
        "up",
        "right",
        "up",
        "left",
        "left",
        "up",
    )
    actions: list[ProbeAction] = []
    for index, button in enumerate(route, start=1):
        actions.append(
            ProbeAction(
                name=f"walk_to_grass_{index:02d}_{button}",
                description="Walk one tile along a conservative route from the Pallet house toward the long-grass Oak trigger.",
                trace=(nav(button),),
            )
        )
    actions.append(
        ProbeAction(
            name="advance_oak_intercept_dialogue",
            description="Progress any Oak interception dialogue or forced movement script that has begun.",
            trace=repeat(tap("a", settle=30), 30),
        )
    )
    return actions


def pallet_to_lab_starter_probe_plan() -> list[ProbeAction]:
    actions = pallet_oak_trigger_plan()
    actions.extend(
        [
            ProbeAction(
                name="settle_after_oak_escort",
                description="Allow forced Oak escort or lab entry scripts to settle.",
                trace=tuple(ButtonInput("a", hold_frames=1, settle_frames=1) for _ in range(240)),
                capture_before=True,
                capture_after=True,
            ),
            ProbeAction(
                name="advance_lab_intro_dialogue",
                description="Progress Oak's lab starter-selection dialogue conservatively.",
                trace=repeat(tap("a", settle=36), 80),
            ),
        ]
    )
    return actions


PLANS = {
    "pallet-oak-trigger": pallet_oak_trigger_plan,
    "pallet-to-lab-starter-probe": pallet_to_lab_starter_probe_plan,
}


def read_bytes(memory: object, start: int, end: int) -> tuple[int, ...]:
    values = memory[start : end + 1]
    return tuple(int(value) for value in values)


def read_watch_values(memory: object) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for watch in WATCH_RANGES:
        raw = read_bytes(memory, watch.start, watch.end)
        values[watch.name] = {
            "start": f"0x{watch.start:04X}",
            "end": f"0x{watch.end:04X}",
            "bytes": list(raw),
        }
    return values


def diff_watch_values(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for watch in WATCH_RANGES:
        old = before[watch.name]["bytes"]
        new = after[watch.name]["bytes"]
        for offset, (old_value, new_value) in enumerate(zip(old, new, strict=True)):
            if old_value == new_value:
                continue
            changes.append(
                {
                    "watch": watch.name,
                    "address": f"0x{watch.start + offset:04X}",
                    "before": old_value,
                    "after": new_value,
                }
            )
    return changes


def story_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [change for change in changes if change.get("watch") in STORY_TRIGGER_WATCHES]


def trace_to_json(trace: Iterable[ButtonInput]) -> list[dict[str, int | str]]:
    return [asdict(step) for step in trace]


class StoryProbe:
    def __init__(self, *, pyboy: object, run_dir: Path, render: bool) -> None:
        self.pyboy = pyboy
        self.run_dir = run_dir
        self.render = render
        self.capture_dir = run_dir / "captures"
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.events: list[dict[str, Any]] = []
        self.capture_index = 0
        self.last_watch_values = read_watch_values(self.pyboy.memory)

    def capture(
        self,
        *,
        label: str,
        reason: str,
        action: ProbeAction | None = None,
        changes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.pyboy.tick(1, True)
        self.wait_for_nonblack_screen()
        self.capture_index += 1
        safe_label = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in label.lower())
        stem = f"{self.capture_index:03d}_{safe_label}"
        state_path = self.capture_dir / f"{stem}.state"
        screenshot_path = self.capture_dir / f"{stem}.png"
        metadata_path = self.capture_dir / f"{stem}.json"
        snap = snapshot(self.pyboy)
        save_state(self.pyboy, state_path)
        save_screenshot(self.pyboy, screenshot_path)
        watch_values = read_watch_values(self.pyboy.memory)
        metadata = {
            "schema": "story_probe_capture_v1",
            "createdUtc": datetime.now(UTC).isoformat(),
            "label": label,
            "reason": reason,
            "statePath": str(state_path),
            "screenshotPath": str(screenshot_path),
            "snapshotHash": snapshot_hash(snap),
            "snapshot": snapshot_to_dict(snap),
            "watchValues": watch_values,
            "changes": changes or [],
        }
        if action:
            metadata["action"] = {
                "name": action.name,
                "description": action.description,
                "trace": trace_to_json(action.trace),
            }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        self.events.append(
            {
                "type": "capture",
                "label": label,
                "reason": reason,
                "statePath": str(state_path),
                "screenshotPath": str(screenshot_path),
                "metadataPath": str(metadata_path),
                "summary": snap.plaintext_summary(),
                "changes": changes or [],
            }
        )
        self.last_watch_values = watch_values
        return metadata

    def wait_for_nonblack_screen(self, *, max_frames: int = 180) -> None:
        for _ in range(max_frames):
            image = self.pyboy.screen.image
            if callable(image):
                image = image()
            if image.convert("L").getbbox() is not None:
                return
            self.pyboy.tick(1, self.render)

    def run_action(self, action: ProbeAction) -> None:
        if action.capture_before:
            self.capture(label=f"before_{action.name}", reason="Buffer state before story-probe action.", action=action)
        action_started = time.perf_counter()
        action_changes: list[dict[str, Any]] = []
        for step_index, step in enumerate(action.trace, start=1):
            before = self.last_watch_values
            self.pyboy.button(step.button, step.hold_frames)
            self.pyboy.tick(step.hold_frames, self.render)
            if step.settle_frames:
                for _ in range(step.settle_frames):
                    self.pyboy.tick(1, self.render)
                    after_tick = read_watch_values(self.pyboy.memory)
                    tick_changes = story_changes(diff_watch_values(before, after_tick))
                    if tick_changes:
                        action_changes.extend(tick_changes)
                        self.capture(
                            label=f"wram_change_{action.name}_{step_index:03d}",
                            reason="Candidate story/progression WRAM changed during action.",
                            action=action,
                            changes=tick_changes,
                        )
                        before = after_tick
            after = read_watch_values(self.pyboy.memory)
            step_changes = story_changes(diff_watch_values(before, after))
            if step_changes:
                action_changes.extend(step_changes)
                self.capture(
                    label=f"wram_change_{action.name}_{step_index:03d}",
                    reason="Candidate story/progression WRAM changed after button input.",
                    action=action,
                    changes=step_changes,
                )
            self.last_watch_values = after
        if action.capture_after:
            self.capture(
                label=f"after_{action.name}",
                reason=f"State after story-probe action completed in {(time.perf_counter() - action_started):.2f}s.",
                action=action,
                changes=action_changes,
            )

    def write_report(self, *, plan: str, state_in: Path, rom_path: Path) -> Path:
        report_path = self.run_dir / "report.json"
        report = {
            "schema": "story_probe_report_v1",
            "createdUtc": datetime.now(UTC).isoformat(),
            "plan": plan,
            "stateIn": str(state_in),
            "romPath": str(rom_path),
            "watchRanges": [asdict(watch) for watch in WATCH_RANGES],
            "events": self.events,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an unattended story-progression probe and capture WRAM/state evidence.")
    parser.add_argument("--rom", default=str(DEFAULT_ROM))
    parser.add_argument("--state-in", default=str(DEFAULT_STATE))
    parser.add_argument("--plan", choices=sorted(PLANS), default="pallet-oak-trigger")
    parser.add_argument("--out-root", default=str(ROOT / "research" / "artifacts" / "story-probes"))
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--max-actions", type=int, default=0, help="Limit actions for debugging. 0 means all.")
    args = parser.parse_args()

    rom = fingerprint_rom(args.rom)
    state_in = Path(args.state_in)
    run_dir = Path(args.out_root) / f"{args.plan}-{timestamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    actions = PLANS[args.plan]()
    if args.max_actions > 0:
        actions = actions[: args.max_actions]

    pyboy = open_emulator(rom.path, window="SDL2" if args.render else "null")
    try:
        load_state(pyboy, state_in)
        pyboy.tick(60, args.render)
        probe = StoryProbe(pyboy=pyboy, run_dir=run_dir, render=args.render)
        probe.capture(label="initial", reason="Initial state loaded for story probe.")
        for action in actions:
            probe.run_action(action)
        report_path = probe.write_report(plan=args.plan, state_in=state_in, rom_path=rom.path)
    finally:
        pyboy.stop(False)

    print(f"Story probe report: {report_path}")
    print(f"Captures: {run_dir / 'captures'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
