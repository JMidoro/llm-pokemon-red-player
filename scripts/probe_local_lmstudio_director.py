from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.director_contracts import DirectorRequest, JsonObject  # noqa: E402
from pokemon_player.director_player import promoted_signals, skill_availability  # noqa: E402
from pokemon_player.director_provider_factory import make_provider  # noqa: E402
from pokemon_player.director_reporting import build_director_report  # noqa: E402
from pokemon_player.director_runtime import DirectorRuntime  # noqa: E402
from pokemon_player.pyboy_lab import (  # noqa: E402
    load_state,
    open_emulator,
    save_screenshot,
    snapshot,
)
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict  # noqa: E402


DEFAULT_STATE = (
    ROOT
    / "research"
    / "golden-states"
    / "local"
    / "viridian_forest_wild_battle_weedle.state"
)
DEFAULT_ROM = ROOT / "research" / "PokemonRed.gb"
DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "google/gemma-4-e4b"
DEFAULT_GOAL = (
    "Choose the single enabled semantic skill that best advances the current Pokemon Red "
    "state without executing it."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe local LM Studio through the canonical Director runtime."
    )
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--rom", default=str(DEFAULT_ROM))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--request-timeout-seconds", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--no-image", action="store_true")
    parser.add_argument("--run-root", default=None)
    args = parser.parse_args()

    run_root = (
        Path(args.run_root)
        if args.run_root
        else ROOT / "research" / "artifacts" / "local-model-probes"
    )
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = run_dir / "screenshot.png"
    state_path = Path(args.state).resolve()
    rom_path = Path(args.rom).resolve()
    snapshot_dict, snapshot_hash_value, signals, available = load_state_context(
        rom_path,
        state_path,
        screenshot_path,
    )
    provider = make_provider(
        "lmstudio-chat",
        env_path=ROOT / ".env",
        base_url=args.base_url,
        api_token=args.api_token,
        timeout_seconds=args.request_timeout_seconds,
    )
    request = DirectorRequest(
        goal=args.goal,
        model=args.model,
        provider="lmstudio-chat",
        enabled_skills=tuple(available),
        context={
            "probe": True,
            "snapshot": compact_snapshot(snapshot_dict),
            "signals": signals,
        },
        screenshot_path=None if args.no_image else screenshot_path,
        temperature=args.temperature,
        max_output_tokens=args.max_tokens,
        runtime_instructions=(
            "This is a decision-only probe; choose one enabled skill but do not assume it ran.",
        ),
        metadata={
            "checkpoint": {
                "kind": "saved_input_state",
                "statePath": str(state_path),
                "screenshotPath": str(screenshot_path),
                "snapshotHash": snapshot_hash_value,
                "actionStarted": False,
            }
        },
    )
    tick = DirectorRuntime(provider, max_retries=args.max_retries).run_tick(request)
    if tick.decision.error:
        finish: JsonObject = {
            "status": "error",
            "success": False,
            "summary": tick.decision.error.message,
            "failureCategory": tick.decision.error.category,
            "actionStarted": False,
        }
    else:
        finish = {
            "status": "stopped",
            "success": False,
            "summary": "Local model decision probe completed without emulator execution.",
            "failureCategory": None,
            "actionStarted": False,
        }
    report_path = run_dir / "report.json"
    report = build_director_report(
        run_id=run_id,
        mode="provider_probe",
        provider=provider,
        model=args.model,
        goal=args.goal,
        requests=[request],
        ticks=[tick],
        finish=finish,
        artifacts={
            "reportPath": str(report_path),
            "statePath": str(state_path),
            "screenshotPath": str(screenshot_path),
        },
        context={"snapshot": compact_snapshot(snapshot_dict)},
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(report_path),
                "screenshot": str(screenshot_path),
                "decision": tick.decision.to_dict(),
                "enabledSkills": [skill.get("id") for skill in available],
            },
            indent=2,
        )
    )
    return 1 if tick.decision.error else 0


def load_state_context(
    rom_path: Path,
    state_path: Path,
    screenshot_path: Path,
) -> tuple[dict[str, Any], str, list[JsonObject], list[JsonObject]]:
    rom = fingerprint_rom(rom_path)
    pyboy = open_emulator(rom.path, window="null")
    try:
        load_state(pyboy, state_path)
        pyboy.tick(60, False)
        save_screenshot(pyboy, screenshot_path)
        current = snapshot(pyboy)
        snapshot_dict = snapshot_to_dict(current)
        snapshot_hash_value = snapshot_hash(current)
    finally:
        pyboy.stop(False)
    signals = promoted_signals(snapshot_dict, screenshot_path)
    available = [
        skill
        for skill in skill_availability(snapshot_dict, screenshot_path)
        if skill.get("enabled") is True
    ]
    return snapshot_dict, snapshot_hash_value, signals, available


def compact_snapshot(snapshot_dict: dict[str, Any]) -> JsonObject:
    return {
        "mode": snapshot_dict.get("mode"),
        "battleTypeRaw": snapshot_dict.get("battle_type_raw"),
        "position": snapshot_dict.get("position"),
        "activePartySlot": snapshot_dict.get("active_party_slot"),
        "activePartyMember": snapshot_dict.get("active_party_member"),
        "enemy": snapshot_dict.get("enemy"),
        "party": snapshot_dict.get("party"),
        "inventory": snapshot_dict.get("inventory"),
        "money": snapshot_dict.get("money"),
        "badges": snapshot_dict.get("badge_names"),
        "summary": snapshot_dict.get("plaintext_summary"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
