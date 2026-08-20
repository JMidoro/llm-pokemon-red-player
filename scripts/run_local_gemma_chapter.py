from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.chapter_direction import ChapterGoal, current_chapter_goal  # noqa: E402
from pokemon_player.director_player import promoted_signals, skill_availability  # noqa: E402
from pokemon_player import memory_map as mm  # noqa: E402
from pokemon_player.pyboy_lab import ButtonInput, load_state, open_emulator, save_screenshot, save_state, snapshot  # noqa: E402
from pokemon_player.rom import RomFingerprint, fingerprint_rom  # noqa: E402
from pokemon_player.run_interrogation import interrogate_run_report  # noqa: E402
from pokemon_player.skill_execution import (  # noqa: E402
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
    execute_heal_at_pokecenter,
    execute_navigate_within_pallet_region,
    execute_navigate_within_pewter_region,
    execute_navigate_within_viridian_forest_region,
    execute_purchase_pokemart_item,
    execute_recover_to_overworld,
    execute_resolve_battle_outcome_dialogue_bundle,
    execute_run_from_wild_battle,
    execute_switch_party_member,
    execute_use_move,
    run_timed_trace,
)
from pokemon_player.skills.purchase_pokemart_item import normalize_shop_item  # noqa: E402
from pokemon_player.snapshot_io import snapshot_hash, snapshot_to_dict  # noqa: E402
from pokemon_player.trace import load_trace  # noqa: E402


DEFAULT_ROM = ROOT / "research" / "PokemonRed.gb"
DEFAULT_STATE = ROOT / "research" / "golden-states" / "local" / "pallet_overworld_started.state"
DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "google/gemma-4-e4b"
DEFAULT_VIDEO_OUTPUT_DIR = Path("D:/Dropbox")
DEFAULT_GOAL = (
    "Progress through Pokemon Red's early-game chapters from the current seed, including the prologue if starting from a clean boot. "
    "At every action, follow the current chapterDirection objective and choose one enabled local skill "
    "whose result should serve that objective. Do not use OpenAI or any cloud API."
)

SUPPORTED_SKILLS = {
    "advance_battle_dialogue",
    "advance_dialogue",
    "attempt_catch",
    "choose_starter",
    "close_menu_or_cancel",
    "complete_prologue",
    "enter_grass_search_loop",
    "enter_nickname_text",
    "handle_nickname_prompt",
    "heal_at_pokecenter",
    "literal_button_press",
    "navigate_within_pallet_region",
    "navigate_within_pewter_region",
    "navigate_within_viridian_forest_region",
    "purchase_pokemart_item",
    "recover_to_overworld",
    "resolve_battle_outcome_dialogue_bundle",
    "run_from_wild_battle",
    "switch_party_member",
    "use_move",
}


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_api_token(explicit: str | None) -> str:
    if explicit:
        return explicit
    dotenv = load_dotenv(ROOT / ".env")
    for key in ("LM_API_TOKEN", "LMSTUDIO_API_KEY", "LM_STUDIO_API_KEY"):
        value = os.environ.get(key) or dotenv.get(key)
        if value:
            return value
    raise RuntimeError(
        "LM Studio API token missing. Set LM_API_TOKEN in the process environment or .env. "
        "This script does not call OpenAI."
    )


def read_png_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def compact_snapshot(snapshot_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": snapshot_dict.get("mode"),
        "battle_type_raw": snapshot_dict.get("battle_type_raw"),
        "position": snapshot_dict.get("position"),
        "active_party_member": snapshot_dict.get("active_party_member"),
        "enemy": snapshot_dict.get("enemy"),
        "party": snapshot_dict.get("party"),
        "inventory": snapshot_dict.get("inventory"),
        "money": snapshot_dict.get("money"),
        "badges": snapshot_dict.get("badge_names"),
        "warnings": snapshot_dict.get("warnings"),
        "plaintext_summary": snapshot_dict.get("plaintext_summary"),
    }


def compact_skill(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": skill.get("id"),
        "label": skill.get("label"),
        "reason": skill.get("reason"),
        "params": skill.get("params") or {},
    }


def enabled_supported_skills(availability: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        skill
        for skill in availability
        if skill.get("enabled") is True and str(skill.get("id")) in SUPPORTED_SKILLS
    ]


def chapter_catch_target_species(chapter_direction: ChapterGoal) -> str | None:
    targets = {
        "chapter_5b_route_22_spearow_catch": "Spearow",
        "chapter_6_capsule_a_pikachu_catch": "Pikachu",
    }
    return targets.get(chapter_direction.chapter_id)


def enemy_matches_species(snapshot_dict: dict[str, Any], target_species: str) -> bool:
    enemy = snapshot_dict.get("enemy") if isinstance(snapshot_dict.get("enemy"), dict) else {}
    target = target_species.strip().lower()
    enemy_name = str(enemy.get("species_name", "")).strip().lower()
    if enemy_name == target:
        return True
    try:
        enemy_species_id = int(enemy.get("species_id"))
    except (TypeError, ValueError):
        return False
    return mm.species_name(enemy_species_id).strip().lower() == target


def default_purchase_quantity(args: dict[str, Any], item: str) -> int:
    if "quantity" in args:
        return max(int(args.get("quantity") or 1), 1)
    return 99 if normalize_shop_item(item).lower() == "poke ball" else 1


def active_hp_ratio(snapshot_dict: dict[str, Any]) -> float | None:
    active = snapshot_dict.get("active_party_member")
    if not isinstance(active, dict):
        party = snapshot_dict.get("party") if isinstance(snapshot_dict.get("party"), list) else []
        active = party[0] if party and isinstance(party[0], dict) else None
    if not isinstance(active, dict):
        return None
    try:
        hp = int(active.get("hp", 0) or 0)
        max_hp = int(active.get("max_hp", 0) or 0)
    except (TypeError, ValueError):
        return None
    if max_hp <= 0:
        return None
    return hp / max_hp


def party_needs_healing(snapshot_dict: dict[str, Any]) -> bool:
    party = snapshot_dict.get("party") if isinstance(snapshot_dict.get("party"), list) else []
    for member in party:
        if not isinstance(member, dict):
            continue
        try:
            hp = int(member.get("hp", 0) or 0)
            max_hp = int(member.get("max_hp", 0) or 0)
            status = int(member.get("status", 0) or 0)
        except (TypeError, ValueError):
            return True
        if max_hp > 0 and (hp < max_hp or status != 0):
            return True
    return False


def viridian_checkpoint_done(history: list[dict[str, Any]] | None) -> bool:
    for item in history or []:
        if item.get("skillId") != "heal_at_pokecenter":
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if result.get("status") != "succeeded":
            continue
        evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
        evidence_text = " ".join(str(piece) for piece in evidence)
        if "position=map=0x29" in evidence_text:
            return True
    return False


def requires_viridian_checkpoint(
    snapshot_dict: dict[str, Any],
    chapter_direction: ChapterGoal,
    history: list[dict[str, Any]] | None,
) -> bool:
    if viridian_checkpoint_done(history):
        return False
    if str(snapshot_dict.get("mode", "unknown")) == "battle":
        return False
    return chapter_direction.chapter_id in {"chapter_5b_route_22_spearow", "chapter_6_capsule_a"}


def apply_chapter_skill_policy(
    available: list[dict[str, Any]],
    snapshot_dict: dict[str, Any],
    chapter_direction: ChapterGoal,
    history: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if should_suppress_mart_counter_navigation(snapshot_dict, chapter_direction):
        allowed_counter_skills = {"advance_dialogue", "literal_button_press", "purchase_pokemart_item"}
        filtered = [skill for skill in available if skill.get("id") in allowed_counter_skills]
        if len(filtered) != len(available):
            return (
                filtered,
                [
                    (
                        "counter-navigation and recovery skills suppressed because the player is already at "
                        "the Viridian Mart counter; use literal_button_press button=A or advance_dialogue to "
                        "open/progress clerk dialogue, then purchase_pokemart_item when the BUY list is visible."
                    )
                ],
            )

    if requires_viridian_checkpoint(snapshot_dict, chapter_direction, history):
        position = snapshot_dict.get("position") if isinstance(snapshot_dict.get("position"), dict) else {}
        if position.get("map_id") == 0x29:
            allowed_checkpoint_skills = {"heal_at_pokecenter", "advance_dialogue", "literal_button_press", "recover_to_overworld"}
        else:
            allowed_checkpoint_skills = {
                "advance_dialogue",
                "close_menu_or_cancel",
                "literal_button_press",
                "navigate_within_pallet_region",
                "navigate_within_viridian_forest_region",
                "recover_to_overworld",
            }
        filtered = [skill for skill in available if skill.get("id") in allowed_checkpoint_skills]
        if len(filtered) != len(available):
            return (
                filtered,
                [
                    (
                        "Viridian PokeCenter checkpoint is required before Route 22 or Viridian Forest; "
                        "navigate to viridian_pokecenter, then use heal_at_pokecenter even if the party is already healthy."
                    )
                ],
            )

    if (
        chapter_direction.chapter_id in {"chapter_7_prepare_for_brock", "chapter_7_level_for_brock"}
        and party_needs_healing(snapshot_dict)
    ):
        return (
            available,
            [
                (
                    "party healing is required before Brock; navigate_within_pewter_region should target "
                    "pewter_pokecenter_counter, then use heal_at_pokecenter when it is enabled."
                )
            ],
        )

    if chapter_direction.chapter_id == "chapter_7_level_for_brock" and str(snapshot_dict.get("mode", "unknown")) == "battle":
        suppressed = {"attempt_catch", "run_from_wild_battle"}
        filtered = [skill for skill in available if skill.get("id") not in suppressed]
        if len(filtered) != len(available):
            return (
                filtered,
                [
                    (
                        "Brock preparation requires experience; run_from_wild_battle and attempt_catch are suppressed "
                        "during training battles. Use damaging moves, switch if needed, and heal after battle."
                    )
                ],
            )

    target_species = chapter_catch_target_species(chapter_direction)
    if not target_species or enemy_matches_species(snapshot_dict, target_species):
        return available, []
    enemy = snapshot_dict.get("enemy") if isinstance(snapshot_dict.get("enemy"), dict) else {}
    enemy_species = enemy.get("species_name") or "unknown"
    suppressed = {"attempt_catch"}
    hp_ratio = active_hp_ratio(snapshot_dict)
    if hp_ratio is not None and hp_ratio <= 0.50:
        suppressed.add("use_move")
    filtered = [skill for skill in available if skill.get("id") not in suppressed]
    if len(filtered) == len(available):
        return filtered, []
    notes = [
        (
            "attempt_catch suppressed because the current chapter target is "
            f"{target_species}, but the active wild enemy is {enemy_species}."
        )
    ]
    if "use_move" in suppressed:
        notes.append(
            "use_move suppressed for this non-target wild encounter because the active Pokemon is at or below 50% HP; run or recover instead."
        )
    return (filtered, notes)


def should_suppress_mart_counter_navigation(
    snapshot_dict: dict[str, Any],
    chapter_direction: ChapterGoal,
) -> bool:
    if chapter_direction.chapter_id != "chapter_5_acquire_poke_balls":
        return False
    position = snapshot_dict.get("position") if isinstance(snapshot_dict.get("position"), dict) else {}
    return (
        position.get("map_id") == 0x2A
        and position.get("x") == 2
        and position.get("y") == 5
    )


def build_tools(available: list[dict[str, Any]]) -> list[dict[str, Any]]:
    skill_ids = [str(skill.get("id")) for skill in available if skill.get("id")]
    return [
        {
            "type": "function",
            "function": {
                "name": "execute_skill",
                "description": "Execute one currently enabled local Pokemon player skill.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skillId": {"type": "string", "enum": skill_ids},
                        "args": {"type": "object", "additionalProperties": True},
                        "plaintextReasoning": {
                            "type": "string",
                            "description": "Brief reason for choosing this skill now.",
                        },
                    },
                    "required": ["skillId", "plaintextReasoning"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def build_messages(
    *,
    goal: str,
    chapter_direction: dict[str, Any],
    skill_policy_notes: list[str],
    action_index: int,
    max_actions: int,
    snapshot_dict: dict[str, Any],
    signals: list[dict[str, Any]],
    available: list[dict[str, Any]],
    history: list[dict[str, Any]],
    screenshot_path: Path,
    include_image: bool,
) -> list[dict[str, Any]]:
    system = (
        "You are a local-only Pokemon Red LLM Director running through LM Studio. "
        "You must choose high-level enabled skills, not raw button presses, unless literal_button_press is the only safe recovery. "
        "Never invent a skill. Never suggest using OpenAI or any external cloud service. "
        "The chapterDirection object is authoritative for the current local goal. "
        "Choose actions that directly serve chapterDirection.objective and use chapterDirection.hints as tactical guidance. "
        "When a hint names a navigation target, pass that exact target in args.target. "
        "If dialogue/script advancement is needed but advance_dialogue is not listed in enabledSkills, use literal_button_press with button=A. "
        "Never use literal_button_press to answer nickname prompts or type on the naming keyboard; use handle_nickname_prompt or enter_nickname_text. "
        "If buying Mart supplies and purchase_pokemart_item is enabled, use it instead of raw button presses. "
        "If the party is damaged or fainted before a gym/leader objective, prioritize PokeCenter navigation and heal_at_pokecenter before entering the gym. "
        "Do not automatically run from every non-target wild battle. Follow chapterDirection: during explicit target-species search, "
        "run from non-targets when that best serves the goal; during ordinary travel, prefer safe XP with use_move unless HP or resources are risky. "
        "If choosing use_move, include args.move exactly from enabledSkills params.moveNames. "
        "The harness stops automatically when chapterDirection.success is true. Until then, keep choosing enabled skills that advance the current game state."
    )
    tick = {
        "goal": goal,
        "chapterDirection": chapter_direction,
        "action_index": action_index,
        "max_actions": max_actions,
        "snapshot": compact_snapshot(snapshot_dict),
        "signals": signals,
        "enabledSkills": [compact_skill(skill) for skill in available],
        "skillPolicy": skill_policy_notes,
        "recentHistory": compact_history(history[-8:]),
        "rules": [
            "Call exactly one tool.",
            "Only execute_skill for ids listed in enabledSkills.",
            "Use valid args from each skill params.",
            "Do not attempt to finish the run yourself; the harness stops automatically on chapter success or budget exhaustion.",
        ],
    }
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(tick, indent=2)}]
    if include_image:
        content.append({"type": "image_url", "image_url": {"url": read_png_data_url(screenshot_path)}})
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]


def compact_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in history:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        compacted.append(
            {
                "action": item.get("action"),
                "skillId": item.get("skillId"),
                "args": item.get("args") or {},
                "status": result.get("status"),
                "summary": result.get("summary"),
                "warnings": result.get("warnings") or [],
            }
        )
    return compacted


def infer_missing_skill_args(
    skill_id: str,
    skill_args: dict[str, Any],
    chapter_direction: ChapterGoal,
    snapshot_dict: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    inferred = dict(skill_args)
    if skill_id == "navigate_within_viridian_forest_region" and chapter_direction.chapter_id == "chapter_6_capsule_a_exit_forest":
        inferred["target"] = "forest_north_exit"
    elif skill_id == "navigate_within_viridian_forest_region" and chapter_direction.chapter_id == "chapter_7_level_for_brock":
        position = snapshot_dict.get("position") if isinstance(snapshot_dict.get("position"), dict) else {}
        if position.get("map_id") == 0x33:
            try:
                y = int(position.get("y", 99))
            except (TypeError, ValueError):
                y = 99
            inferred["target"] = "north_gate_north" if y <= 0 else "forest_north_exit"
    elif skill_id == "navigate_within_viridian_forest_region" and not inferred.get("target"):
        if requires_viridian_checkpoint(snapshot_dict, chapter_direction, history):
            inferred["target"] = "viridian_pokecenter"
        elif chapter_direction.chapter_id == "chapter_5b_route_22_spearow":
            inferred["target"] = "route_22_grass"
        elif chapter_direction.chapter_id == "chapter_6_capsule_a":
            inferred["target"] = "forest_grass"
        elif chapter_direction.chapter_id == "chapter_6_capsule_a_exit_forest":
            inferred["target"] = "forest_north_exit"
    if skill_id == "enter_grass_search_loop" and not inferred.get("patch"):
        if chapter_direction.chapter_id == "chapter_7_level_for_brock":
            inferred["patch"] = "current_map"
    if skill_id == "use_move" and not inferred.get("move"):
        move = default_active_battle_move(snapshot_dict)
        if move:
            inferred["move"] = move
    if skill_id == "navigate_within_pewter_region":
        if chapter_direction.chapter_id == "chapter_7_level_for_brock":
            inferred["target"] = (
                "pewter_pokecenter_counter" if party_needs_healing(snapshot_dict) else "pewter_route2_grass"
            )
        elif inferred.get("target"):
            return inferred
        elif chapter_direction.chapter_id == "chapter_7_reach_pewter_city":
            inferred["target"] = "pewter_city_center"
        elif chapter_direction.chapter_id == "chapter_7_prepare_for_brock" and party_needs_healing(snapshot_dict):
            inferred["target"] = "pewter_pokecenter_counter"
        elif chapter_direction.chapter_id in {"chapter_7_prepare_for_brock", "chapter_7_defeat_brock"}:
            inferred["target"] = "pewter_gym_brock_pre_battle"
    return inferred


def default_active_battle_move(snapshot_dict: dict[str, Any]) -> str | None:
    active = snapshot_dict.get("active_party_member")
    if not isinstance(active, dict):
        return None
    moves = active.get("moves")
    if not isinstance(moves, list):
        return None
    usable: list[str] = []
    for move in moves:
        if not isinstance(move, dict):
            continue
        name = str(move.get("move_name") or move.get("name") or "").strip()
        if not name or name.lower() == "no move":
            continue
        try:
            pp = int(move.get("pp", 0) or 0)
        except (TypeError, ValueError):
            pp = 0
        if pp <= 0:
            continue
        usable.append(name)
    if not usable:
        return None
    non_damaging = {"growl", "leer", "tail whip", "string shot"}
    for name in usable:
        if name.lower() not in non_damaging:
            return name
    return usable[0]


def normalize_selected_skill(
    arguments: dict[str, Any],
    available: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    available_ids = {str(skill.get("id")) for skill in available}
    skill_id = str(arguments.get("skillId", ""))
    skill_args = arguments.get("args") if isinstance(arguments.get("args"), dict) else {}
    if skill_id in {"execute_move", "attack", "use_attack"} and "use_move" in available_ids:
        return "use_move", skill_args
    if skill_id != "execute_skill":
        return skill_id, skill_args

    nested_candidates = [skill_args, arguments]
    for candidate in nested_candidates:
        if not isinstance(candidate, dict):
            continue
        nested_id = str(candidate.get("skillId", ""))
        if nested_id in {"execute_move", "attack", "use_attack"} and "use_move" in available_ids:
            nested_args = candidate.get("args") if isinstance(candidate.get("args"), dict) else {}
            return "use_move", nested_args
        if nested_id in available_ids:
            nested_args = candidate.get("args") if isinstance(candidate.get("args"), dict) else {}
            return nested_id, nested_args
    return skill_id, skill_args


def call_lmstudio(
    base_url: str,
    payload: dict[str, Any],
    *,
    api_token: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LM Studio HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"LM Studio request failed: {exc.reason}") from exc


def selected_tool_from_response(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") if isinstance(response.get("choices"), list) else []
    if not choices or not isinstance(choices[0], dict):
        return {"name": "finish_run", "arguments": {"status": "failed", "success": False, "summary": "No choices returned.", "failureCategory": "no_choices"}}
    message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        call = tool_calls[0] if isinstance(tool_calls[0], dict) else {}
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        raw_args = function.get("arguments")
        args = {}
        if isinstance(raw_args, str) and raw_args:
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    args = parsed
            except json.JSONDecodeError:
                args = {"raw": raw_args}
        return {"name": function.get("name"), "arguments": args, "raw": call}
    content = message.get("content")
    if isinstance(content, str):
        try:
            parsed = json.loads(content.strip().strip("`"))
            if isinstance(parsed, dict) and "skillId" in parsed:
                return {"name": "execute_skill", "arguments": parsed, "rawText": content}
        except json.JSONDecodeError:
            pass
        return {
            "name": "finish_run",
            "arguments": {
                "status": "stopped",
                "success": False,
                "summary": content,
                "failureCategory": "text_response_without_tool",
            },
        }
    return {"name": "finish_run", "arguments": {"status": "failed", "success": False, "summary": "No tool call returned.", "failureCategory": "no_tool_call"}}


def chapter_success(snapshot_dict: dict[str, Any]) -> bool:
    position = snapshot_dict.get("position") if isinstance(snapshot_dict.get("position"), dict) else {}
    return (
        position.get("map_id") == 0x28
        and snapshot_dict.get("mode") in {"dialogue", "overworld", "menu_or_dialogue_uncertain"}
        and int(position.get("y", 99)) <= 4
    )


def save_current_artifacts(pyboy: object, run_dir: Path, label: str) -> tuple[Path, Path, dict[str, Any]]:
    screenshot_path = run_dir / f"{label}.png"
    state_path = run_dir / f"{label}.state"
    pyboy.tick(1, True)
    save_screenshot(pyboy, screenshot_path)
    save_state(pyboy, state_path)
    snapshot_dict = snapshot_to_dict(snapshot(pyboy))
    return screenshot_path, state_path, snapshot_dict


def append_video_frame(source: Path, frame_dir: Path, frame_index: int) -> int:
    frame_dir.mkdir(parents=True, exist_ok=True)
    destination = frame_dir / f"frame_{frame_index:06d}.png"
    shutil.copy2(source, destination)
    return frame_index + 1


PATHING_VIDEO_SKILLS = {
    "complete_prologue",
    "enter_grass_search_loop",
    "navigate_within_pallet_region",
    "navigate_within_pewter_region",
    "navigate_within_viridian_forest_region",
}


def append_skill_trace_video_frames(
    artifact: SkillRunArtifact | dict[str, Any],
    *,
    rom: RomFingerprint,
    skill_id: str,
    frame_dir: Path,
    frame_index: int,
    warnings: list[str],
    max_frames: int = 120,
) -> int:
    if skill_id not in PATHING_VIDEO_SKILLS or not isinstance(artifact, SkillRunArtifact):
        return frame_index
    try:
        frame_limit = 260 if skill_id == "complete_prologue" else max_frames
        report = json.loads(artifact.report_path.read_text(encoding="utf-8"))
        before_state = Path(str(report.get("before_state_file") or ""))
        trace_file = Path(str(report.get("trace_file") or ""))
        if not before_state.exists() or not trace_file.exists():
            return frame_index
        trace = load_trace(trace_file)
        if not trace:
            return frame_index
        replay = open_emulator(rom.path)
        try:
            load_state(replay, before_state)
            frame_dir.mkdir(parents=True, exist_ok=True)
            for step in trace[:frame_limit]:
                run_timed_trace(replay, [step], render=False)
                destination = frame_dir / f"frame_{frame_index:06d}.png"
                save_screenshot(replay, destination)
                frame_index += 1
        finally:
            replay.stop(False)
        if len(trace) > frame_limit:
            warnings.append(
                f"{skill_id} trace video was capped at {frame_limit} frames out of {len(trace)} inputs."
            )
    except Exception as exc:
        warnings.append(f"Could not append pathing trace frames for {skill_id}: {exc}")
    return frame_index


def render_video_artifact(
    *,
    run_dir: Path,
    frame_dir: Path,
    output_dir: Path,
    run_id: str,
    fps: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "enabled": True,
        "fps": fps,
        "frameDir": str(frame_dir),
        "frameDirCleaned": False,
        "localVideoCleaned": False,
        "dropboxPath": None,
        "warnings": [],
    }
    frames = sorted(frame_dir.glob("frame_*.png"))
    result["frameCount"] = len(frames)
    if not frames:
        result["warnings"].append("No video frames were captured.")
        cleanup_video_temp(frame_dir=frame_dir, local_video=None, result=result)
        return result

    ffmpeg = shutil.which("ffmpeg") or ("C:/ffmpeg/bin/ffmpeg.exe" if Path("C:/ffmpeg/bin/ffmpeg.exe").exists() else None)
    if not ffmpeg:
        result["warnings"].append("ffmpeg was not found on PATH; video was not rendered.")
        cleanup_video_temp(frame_dir=frame_dir, local_video=None, result=result)
        return result

    output_dir.mkdir(parents=True, exist_ok=True)
    local_video = run_dir / f"{run_id}.mp4"
    dropbox_video = output_dir / f"{run_id}.mp4"
    command = [
        ffmpeg,
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frame_dir / "frame_%06d.png"),
        "-vf",
        "scale=640:576:flags=neighbor,format=yuv420p",
        "-movflags",
        "+faststart",
        str(local_video),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    result["ffmpegReturnCode"] = completed.returncode
    if completed.returncode != 0:
        result["warnings"].append("ffmpeg failed to render the run video.")
        result["ffmpegStderr"] = completed.stderr[-4000:]
        cleanup_video_temp(frame_dir=frame_dir, local_video=local_video, result=result)
        return result

    try:
        shutil.copy2(local_video, dropbox_video)
        result["dropboxPath"] = str(dropbox_video)
        result["bytes"] = dropbox_video.stat().st_size if dropbox_video.exists() else None
    except OSError as exc:
        result["warnings"].append(f"Rendered video locally but could not copy it to {output_dir}: {exc}")
        result["localVideoPath"] = str(local_video)
        cleanup_video_temp(frame_dir=frame_dir, local_video=None, result=result)
        return result
    cleanup_video_temp(frame_dir=frame_dir, local_video=local_video, result=result)
    return result


def cleanup_video_temp(*, frame_dir: Path, local_video: Path | None, result: dict[str, Any]) -> None:
    if frame_dir.exists():
        shutil.rmtree(frame_dir, ignore_errors=True)
    result["frameDirCleaned"] = not frame_dir.exists()
    if local_video is not None and local_video.exists():
        local_video.unlink()
    result["localVideoCleaned"] = local_video is None or not local_video.exists()


def execute_local_skill(
    pyboy: object,
    *,
    skill_id: str,
    args: dict[str, Any],
    state_in: Path,
    rom: RomFingerprint,
    run_root: Path,
    render: bool,
) -> SkillRunArtifact | dict[str, Any]:
    common = {
        "state_in": state_in,
        "rom": rom,
        "run_root": run_root,
        "render": render,
        "post_load_settle_frames": 30,
        "emulation_speed": 0,
    }
    if skill_id == "advance_dialogue":
        return execute_advance_dialogue(pyboy, **common)
    if skill_id == "advance_battle_dialogue":
        return execute_advance_battle_dialogue(pyboy, **common, max_inputs=int(args.get("maxInputs", 16)))
    if skill_id == "attempt_catch":
        return execute_attempt_catch(
            pyboy,
            **common,
            max_wait_frames=int(args.get("maxWaitFrames", 1800)),
            throw_executor=str(args.get("throwExecutor", "battle-menu-controller")),
            battle_menu_max_steps=int(args.get("battleMenuMaxSteps", 40)),
        )
    if skill_id == "close_menu_or_cancel":
        return execute_close_menu_or_cancel(pyboy, **common)
    if skill_id == "complete_prologue":
        return execute_complete_prologue(
            pyboy,
            **common,
            player_name=str(args.get("playerName", args.get("player_name", "RED"))).upper(),
            rival_name=str(args.get("rivalName", args.get("rival_name", "BLUE"))).upper(),
            handoff=str(args.get("handoff", "pallet_outside")),  # type: ignore[arg-type]
            max_intro_presses=int(args.get("maxIntroPresses", 120)),
            max_handoff_inputs=int(args.get("maxHandoffInputs", 120)),
        )
    if skill_id == "choose_starter":
        return execute_choose_starter(
            pyboy,
            **common,
            starter=str(args.get("starter", "squirtle")),
            nickname=str(args["nickname"]) if args.get("nickname") else None,
            max_wait_frames=int(args.get("maxWaitFrames", 1800)),
        )
    if skill_id == "enter_grass_search_loop":
        return execute_enter_grass_search_loop(
            pyboy,
            **common,
            patch=str(args.get("patch", "current_map")),
            max_steps=int(args.get("maxSteps", 240)),
        )
    if skill_id == "enter_nickname_text":
        nickname = str(args.get("nickname", "ABK")).strip().upper()
        return execute_enter_nickname_text(pyboy, **common, nickname=nickname)
    if skill_id == "handle_nickname_prompt":
        raw_choice = str(args.get("choice", args.get("nicknameChoice", args.get("nickname", "decline")))).strip().lower()
        choice = "accept" if raw_choice in {"accept", "yes", "y", "true", "nickname", "name"} else "decline"
        return execute_handle_nickname_prompt(pyboy, **common, choice=choice)
    if skill_id == "heal_at_pokecenter":
        return execute_heal_at_pokecenter(pyboy, **common)
    if skill_id == "navigate_within_pallet_region":
        return execute_navigate_within_pallet_region(
            pyboy,
            **common,
            target=str(args["target"]) if args.get("target") else None,
            max_inputs=int(args.get("maxInputs", 180)),
            max_segment_expansions=int(args.get("maxSegmentExpansions", 8000)),
        )
    if skill_id == "navigate_within_viridian_forest_region":
        return execute_navigate_within_viridian_forest_region(
            pyboy,
            **common,
            target=str(args["target"]) if args.get("target") else None,
            max_inputs=int(args.get("maxInputs", 180)),
            max_segment_expansions=int(args.get("maxSegmentExpansions", 8000)),
        )
    if skill_id == "navigate_within_pewter_region":
        return execute_navigate_within_pewter_region(
            pyboy,
            **common,
            target=str(args["target"]) if args.get("target") else None,
            max_inputs=int(args.get("maxInputs", 260)),
            max_segment_expansions=int(args.get("maxSegmentExpansions", 8000)),
        )
    if skill_id == "purchase_pokemart_item":
        item_arg = args.get("item", args.get("itemName", args.get("name", "Poke Ball")))
        if isinstance(item_arg, dict):
            item_arg = item_arg.get("name") or item_arg.get("item") or item_arg.get("itemName") or "Poke Ball"
        item_name = str(item_arg)
        return execute_purchase_pokemart_item(
            pyboy,
            **common,
            item=item_name,
            quantity=default_purchase_quantity(args, item_name),
        )
    if skill_id == "recover_to_overworld":
        return execute_recover_to_overworld(pyboy, **common, max_inputs=int(args.get("maxInputs", 12)))
    if skill_id == "resolve_battle_outcome_dialogue_bundle":
        return execute_resolve_battle_outcome_dialogue_bundle(pyboy, **common)
    if skill_id == "run_from_wild_battle":
        return execute_run_from_wild_battle(pyboy, **common, max_wait_frames=int(args.get("maxWaitFrames", 900)))
    if skill_id == "switch_party_member":
        target = args.get("target")
        if isinstance(target, dict):
            target = target.get("slot") or target.get("nickname") or target.get("species") or target.get("name")
        if target is None:
            raise ValueError("switch_party_member requires target.")
        if isinstance(target, str) and target.isdigit():
            target = int(target)
        return execute_switch_party_member(
            pyboy,
            **common,
            target=target,
            max_wait_frames=int(args.get("maxWaitFrames", 1200)),
        )
    if skill_id == "use_move":
        requested_move = args.get("move", args.get("requestedMove"))
        if requested_move is None:
            requested_move = args.get("moveName", args.get("moveId"))
        if requested_move is None:
            raise ValueError("use_move requires move, requestedMove, moveName, or moveId.")
        return execute_use_move(
            pyboy,
            **common,
            requested_move=requested_move,
            max_wait_frames=int(args.get("maxWaitFrames", 900)),
        )
    if skill_id == "literal_button_press":
        raw_button = args.get("button")
        if raw_button is None and isinstance(args.get("buttons"), list) and args["buttons"]:
            raw_button = args["buttons"][0]
        button = str(raw_button or "a").strip().lower()
        if button not in {"a", "b", "up", "down", "left", "right", "start", "select"}:
            raise ValueError(f"Unsupported literal button: {button}")
        load_state(pyboy, state_in)
        run_timed_trace(pyboy, [ButtonInput(button, hold_frames=8, settle_frames=36)], render=render)
        return {"skill_id": skill_id, "status": "succeeded", "summary": f"Pressed {button.upper()} once.", "evidence": [f"button={button}"], "warnings": []}
    raise ValueError(f"Unsupported local Gemma chapter skill: {skill_id}")


def artifact_result_dict(artifact: SkillRunArtifact | dict[str, Any]) -> dict[str, Any]:
    if isinstance(artifact, dict):
        return artifact
    return {
        "skill_id": artifact.result.skill_id,
        "status": artifact.result.status,
        "summary": artifact.result.summary,
        "evidence": list(artifact.result.evidence),
        "warnings": list(artifact.result.warnings),
        "run_dir": str(artifact.run_dir),
        "report_path": str(artifact.report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local Gemma/LM Studio unattended chapter attempt.")
    parser.add_argument("--rom", default=str(DEFAULT_ROM))
    parser.add_argument("--state-in", default=str(DEFAULT_STATE))
    parser.add_argument(
        "--fresh-start",
        action="store_true",
        help="Boot the ROM with clean temporary SRAM instead of loading --state-in.",
    )
    parser.add_argument(
        "--fresh-start-boot-frames",
        type=int,
        default=1800,
        help="Frames to tick before the first action when --fresh-start is used.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--max-actions", type=int, default=100)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=180,
        help="Timeout for each local LM Studio chat completion request.",
    )
    parser.add_argument("--no-image", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Disable temporary frame capture and run video rendering.",
    )
    parser.add_argument(
        "--video-output-dir",
        default=str(DEFAULT_VIDEO_OUTPUT_DIR),
        help="Directory where the final run video is copied. Defaults to D:/Dropbox.",
    )
    parser.add_argument("--video-fps", type=int, default=2)
    args = parser.parse_args()

    api_token = resolve_api_token(args.api_token)
    rom = fingerprint_rom(args.rom)
    state_in = Path(args.state_in)
    run_dir = ROOT / "research" / "artifacts" / "local-gemma-chapter-runs" / timestamp()
    run_id = run_dir.name
    run_dir.mkdir(parents=True, exist_ok=True)
    skill_run_root = run_dir / "skill-runs"
    video_frame_dir = run_dir / "video-frames"
    video_frame_index = 1
    video_artifact: dict[str, Any] = {"enabled": False}
    pathing_frame_warnings: list[str] = []
    history: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    chapter_timeline: list[dict[str, Any]] = []

    clean_ram_path = run_dir / "fresh-start-clean.ram"
    if args.fresh_start:
        clean_ram_path.write_bytes(bytes([0]) * 32768)
        pyboy = open_emulator(rom.path, window="SDL2" if args.render else "null", ram_path=clean_ram_path)
        state_in = run_dir / "fresh-start-title.state"
    else:
        pyboy = open_emulator(rom.path, window="SDL2" if args.render else "null")
    finish: dict[str, Any] | None = None
    try:
        if args.fresh_start:
            pyboy.tick(args.fresh_start_boot_frames, args.render)
            save_state(pyboy, state_in)
        else:
            load_state(pyboy, state_in)
            pyboy.tick(60, args.render)
        for action_index in range(1, args.max_actions + 1):
            screenshot_path, current_state_path, snapshot_dict = save_current_artifacts(
                pyboy,
                run_dir,
                f"action_{action_index:03d}_before",
            )
            if not args.no_video:
                video_frame_index = append_video_frame(
                    screenshot_path,
                    video_frame_dir,
                    video_frame_index,
                )
            signals = promoted_signals(snapshot_dict, screenshot_path)
            chapter_direction = current_chapter_goal(snapshot_dict)
            available = enabled_supported_skills(skill_availability(snapshot_dict, screenshot_path))
            available, skill_policy_notes = apply_chapter_skill_policy(
                available,
                snapshot_dict,
                chapter_direction,
                history,
            )
            chapter_timeline.append({"action": action_index, **chapter_direction.to_dict()})
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
                    "summary": "No supported enabled local skills are available.",
                    "failureCategory": "no_supported_enabled_skills",
                }
                break

            payload = {
                "model": args.model,
                "messages": build_messages(
                    goal=args.goal,
                    chapter_direction=chapter_direction.to_dict(),
                    skill_policy_notes=skill_policy_notes,
                    action_index=action_index,
                    max_actions=args.max_actions,
                    snapshot_dict=snapshot_dict,
                    signals=signals,
                    available=available,
                    history=history,
                    screenshot_path=screenshot_path,
                    include_image=not args.no_image,
                ),
                "tools": build_tools(available),
                "tool_choice": "required",
                "temperature": args.temperature,
                "max_tokens": args.max_tokens,
            }
            try:
                response = call_lmstudio(
                    args.base_url,
                    payload,
                    api_token=api_token,
                    timeout_seconds=args.request_timeout_seconds,
                )
            except Exception as exc:
                requests.append(
                    {
                        "action": action_index,
                        "screenshot": str(screenshot_path),
                        "state": str(current_state_path),
                        "snapshot_hash": snapshot_hash(snapshot(pyboy)),
                        "enabled_skills": [skill.get("id") for skill in available],
                        "skill_policy": skill_policy_notes,
                        "error": str(exc),
                        "errorType": exc.__class__.__name__,
                    }
                )
                finish = {
                    "status": "stopped",
                    "success": False,
                    "summary": f"Local LM Studio request failed at action {action_index}: {exc}",
                    "failureCategory": "local_llm_request_failed",
                }
                break
            selected = selected_tool_from_response(response)
            requests.append(
                {
                    "action": action_index,
                    "screenshot": str(screenshot_path),
                    "state": str(current_state_path),
                    "snapshot_hash": snapshot_hash(snapshot(pyboy)),
                    "enabled_skills": [skill.get("id") for skill in available],
                    "skill_policy": skill_policy_notes,
                    "selected": selected,
                    "response": response,
                }
            )

            if selected.get("name") == "finish_run":
                arguments = selected.get("arguments") if isinstance(selected.get("arguments"), dict) else {}
                if chapter_direction.success:
                    finish = {
                        "status": str(arguments.get("status", "completed")),
                        "success": True,
                        "summary": str(arguments.get("summary", f"Gemma finished after satisfying {chapter_direction.title}.")),
                        "failureCategory": None,
                    }
                    break
                history.append(
                    {
                        "action": action_index,
                        "skillId": "finish_run",
                        "args": arguments,
                        "plaintextReasoning": arguments.get("plaintextReasoning"),
                        "result": {
                            "skill_id": "finish_run",
                            "status": "blocked",
                            "summary": "finish_run was rejected because the current chapter goal is not satisfied.",
                            "evidence": [
                                f"chapter_id={chapter_direction.chapter_id}",
                                f"chapter_success={chapter_direction.success}",
                            ],
                            "warnings": ["premature_finish_rejected"],
                        },
                    }
                )
                continue
            if selected.get("name") != "execute_skill":
                finish = {
                    "status": "failed",
                    "success": False,
                    "summary": f"Unexpected tool selected: {selected.get('name')}",
                    "failureCategory": "unexpected_tool",
                }
                break

            arguments = selected.get("arguments") if isinstance(selected.get("arguments"), dict) else {}
            skill_id, skill_args = normalize_selected_skill(arguments, available)
            skill_args = infer_missing_skill_args(skill_id, skill_args, chapter_direction, snapshot_dict, history)
            if skill_id not in {str(skill.get("id")) for skill in available}:
                history.append(
                    {
                        "action": action_index,
                        "skillId": skill_id,
                        "args": skill_args,
                        "plaintextReasoning": arguments.get("plaintextReasoning"),
                        "result": {
                            "skill_id": skill_id,
                            "status": "blocked",
                            "summary": f"{skill_id} is not currently enabled.",
                            "evidence": [
                                "enabled_skills=" + ",".join(str(skill.get("id")) for skill in available),
                                "hint=If text/script advancement is still needed, use literal_button_press with button=A.",
                            ],
                            "warnings": ["unavailable_skill_selected"],
                        },
                    }
                )
                continue

            try:
                artifact = execute_local_skill(
                    pyboy,
                    skill_id=skill_id,
                    args=skill_args,
                    state_in=current_state_path,
                    rom=rom,
                    run_root=skill_run_root,
                    render=args.render,
                )
                result = artifact_result_dict(artifact)
                if not args.no_video:
                    video_frame_index = append_skill_trace_video_frames(
                        artifact,
                        rom=rom,
                        skill_id=skill_id,
                        frame_dir=video_frame_dir,
                        frame_index=video_frame_index,
                        warnings=pathing_frame_warnings,
                    )
            except Exception as exc:
                result = {
                    "skill_id": skill_id,
                    "status": "blocked",
                    "summary": f"Skill execution failed before inputs were sent: {exc}",
                    "evidence": [
                        f"error_type={exc.__class__.__name__}",
                        "hint=Use the skill params exactly; required arguments must be present.",
                    ],
                    "warnings": ["skill_execution_error"],
                }
            history.append(
                {
                    "action": action_index,
                    "skillId": skill_id,
                    "args": skill_args,
                    "plaintextReasoning": arguments.get("plaintextReasoning"),
                    "result": result,
                }
            )
        else:
            finish = {
                "status": "checkpoint",
                "success": False,
                "summary": f"Action budget checkpoint reached after {args.max_actions} actions.",
                "failureCategory": None,
                "stopReason": "action_budget",
            }
        final_screenshot, final_state, final_snapshot = save_current_artifacts(pyboy, run_dir, "final")
        if not args.no_video:
            video_frame_index = append_video_frame(final_screenshot, video_frame_dir, video_frame_index)
    finally:
        pyboy.stop(False)

    if not args.no_video:
        video_artifact = render_video_artifact(
            run_dir=run_dir,
            frame_dir=video_frame_dir,
            output_dir=Path(args.video_output_dir),
            run_id=run_id,
            fps=max(args.video_fps, 1),
        )
        video_artifact.setdefault("warnings", []).extend(pathing_frame_warnings)

    report = {
        "schema": "local_gemma_chapter_run_v1",
        "createdUtc": datetime.now(UTC).isoformat(),
        "model": args.model,
        "baseUrl": args.base_url,
        "auth": {"tokenProvided": True},
        "stateIn": str(state_in),
        "freshStart": bool(args.fresh_start),
        "freshStartCleanRam": str(clean_ram_path) if args.fresh_start else None,
        "goal": args.goal,
        "maxActions": args.max_actions,
        "finish": finish,
        "chapterTimeline": chapter_timeline,
        "history": history,
        "requests": requests,
        "video": video_artifact,
        "pathingFrameWarnings": pathing_frame_warnings,
        "finalScreenshot": str(final_screenshot),
        "finalState": str(final_state),
        "finalSnapshot": final_snapshot,
    }
    report["checkpoint"] = interrogate_run_report(report)
    report_path = run_dir / "report.json"
    (run_dir / "checkpoint.json").write_text(json.dumps(report["checkpoint"], indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(report_path),
                "finalScreenshot": str(final_screenshot),
                "video": video_artifact,
                "finish": finish,
                "checkpoint": report["checkpoint"],
                "actionsTaken": len(history),
            },
            indent=2,
        )
    )
    return 0 if report["checkpoint"].get("verdict") not in {"unsafe_state", "model_error"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
