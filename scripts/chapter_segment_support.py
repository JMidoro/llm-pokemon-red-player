from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.chapter_direction import ChapterGoal  # noqa: E402
from pokemon_player import memory_map as mm  # noqa: E402
from pokemon_player.capsule_a_navigation import resolve_grass_patch, snapshot_position  # noqa: E402
from pokemon_player.pyboy_lab import ButtonInput, load_state, open_emulator, save_screenshot, save_state, snapshot  # noqa: E402
from pokemon_player.rom import RomFingerprint  # noqa: E402
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
    execute_handle_move_learning_prompt,
    execute_handle_trainer_switch_prompt,
    execute_heal_at_pokecenter,
    execute_navigate_within_pallet_region,
    execute_navigate_within_pewter_region,
    execute_navigate_within_viridian_forest_region,
    execute_purchase_pokemart_item,
    execute_recover_to_overworld,
    execute_resolve_battle_outcome_dialogue_bundle,
    execute_run_from_wild_battle,
    execute_switch_party_member,
    execute_talk_to_npc,
    execute_use_move,
    run_timed_trace,
)
from pokemon_player.skills.purchase_pokemart_item import normalize_shop_item  # noqa: E402
from pokemon_player.skills.talk_to_npc import default_interaction_target  # noqa: E402
from pokemon_player.snapshot_io import snapshot_to_dict  # noqa: E402
from pokemon_player.trace import load_trace  # noqa: E402


DEFAULT_ROM = ROOT / "research" / "PokemonRed.gb"
DEFAULT_STATE = ROOT / "research" / "golden-states" / "local" / "pallet_overworld_started.state"
DEFAULT_VIDEO_OUTPUT_DIR = Path("D:/Dropbox")

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
    "handle_move_learning_prompt",
    "handle_trainer_switch_prompt",
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
    "talk_to_npc",
    "use_move",
}


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def requested_success_reached(
    success_target: str,
    snapshot_dict: dict[str, Any],
    chapter_direction: ChapterGoal,
) -> tuple[bool, str]:
    if success_target == "chapter":
        return chapter_direction.success, chapter_direction.title
    if success_target != "capsule-a":
        raise ValueError(f"Unsupported success target: {success_target}")
    party = snapshot_dict.get("party")
    party = party if isinstance(party, list) else []
    has_pikachu = any(
        isinstance(member, dict)
        and str(member.get("species_name") or "").lower() == "pikachu"
        for member in party
    )
    position = snapshot_dict.get("position")
    position = position if isinstance(position, dict) else {}
    map_id = position.get("map_id")
    y = position.get("y")
    reached_north_exit = map_id == 0x2F or (
        map_id == 0x33 and isinstance(y, int) and y <= 0
    )
    return has_pikachu and reached_north_exit, "Capsule A north exit"


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
    position = snapshot_dict.get("position") if isinstance(snapshot_dict.get("position"), dict) else {}
    if chapter_direction.chapter_id == "chapter_5b_route_22_spearow" and position.get("map_id") == 0x21:
        # Reaching Route 22 is durable proof that the Viridian checkpoint travel
        # already completed, even when a new supervisor segment has no local history.
        return False
    if chapter_direction.chapter_id == "chapter_6_capsule_a" and position.get("map_id") in {
        0x21,
        0x32,
        0x33,
        0x34,
    }:
        # Frozen Capsule A starts are valid chapter starts after the checkpoint.
        # Reaching Route 22 or the forest is also durable evidence that a clean-boot
        # lineage passed Viridian, even after a supervisor segment boundary.
        return False
    return chapter_direction.chapter_id in {"chapter_5b_route_22_spearow", "chapter_6_capsule_a"}


def apply_chapter_skill_policy(
    available: list[dict[str, Any]],
    snapshot_dict: dict[str, Any],
    chapter_direction: ChapterGoal,
    history: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    interaction_target = default_interaction_target(snapshot_dict)
    expected_interaction = {
        "chapter_3_retrieve_parcel": "viridian_mart_clerk",
        "chapter_4_return_parcel_in_lab": "professor_oak",
        "chapter_5_acquire_poke_balls": "viridian_mart_clerk",
        "chapter_7_defeat_brock": "brock",
    }.get(chapter_direction.chapter_id)
    if interaction_target and interaction_target == expected_interaction:
        filtered = [skill for skill in available if skill.get("id") == "talk_to_npc"]
        if filtered:
            return (
                filtered,
                [
                    (
                        f"The player is already at {interaction_target}; use talk_to_npc "
                        f"target={interaction_target} to begin the story interaction."
                    )
                ],
            )
        dialogue = [skill for skill in available if skill.get("id") == "advance_dialogue"]
        if dialogue:
            return (
                dialogue,
                [
                    (
                        f"The interaction with {interaction_target} has already started; "
                        "advance_dialogue is the only relevant next action until the dialogue closes "
                        "or a battle/decision surface appears."
                    )
                ],
            )

    if should_suppress_mart_counter_navigation(snapshot_dict, chapter_direction):
        allowed_counter_skills = {
            "advance_dialogue",
            "purchase_pokemart_item",
            "talk_to_npc",
        }
        filtered = [skill for skill in available if skill.get("id") in allowed_counter_skills]
        if len(filtered) != len(available):
            return (
                filtered,
                [
                    (
                        "counter-navigation and recovery skills suppressed because the player is already at "
                        "the Viridian Mart counter; use talk_to_npc target=viridian_mart_clerk to "
                        "open the clerk dialogue, then purchase_pokemart_item when the BUY list is visible."
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

    search_patch_id = {
        "chapter_5b_route_22_spearow": "route_22_grass",
        "chapter_6_capsule_a": "viridian_forest_south_grass",
    }.get(chapter_direction.chapter_id)
    search_patch = resolve_grass_patch(search_patch_id) if search_patch_id else None
    position = snapshot_position(snapshot_dict)
    hp_ratio = active_hp_ratio(snapshot_dict)
    if (
        search_patch
        and search_patch.contains(position)
        and snapshot_dict.get("mode") == "overworld"
        and (hp_ratio is None or hp_ratio > 0.50)
    ):
        filtered = [skill for skill in available if skill.get("id") == "enter_grass_search_loop"]
        if filtered:
            return (
                filtered,
                [
                    (
                        f"The player is already inside {search_patch.label}; navigation to the patch is complete. "
                        "Use enter_grass_search_loop patch=current_map to search for the chapter target."
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
    if not target_species:
        return available, []
    if enemy_matches_species(snapshot_dict, target_species):
        hp_ratio = active_hp_ratio(snapshot_dict)
        if hp_ratio is not None and hp_ratio <= 0.50:
            return available, [f"{target_species} is the chapter target, but running remains available below 50% HP."]
        filtered = [skill for skill in available if skill.get("id") != "run_from_wild_battle"]
        if len(filtered) == len(available):
            return filtered, []
        return (
            filtered,
            [
                (
                    f"run_from_wild_battle suppressed because the active enemy is the chapter target, "
                    f"{target_species}; weaken it safely or use attempt_catch."
                )
            ],
        )
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
    if skill_id == "talk_to_npc" and not inferred.get("target"):
        target = default_interaction_target(snapshot_dict)
        if target:
            inferred["target"] = target
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
    return usable[0] if len(usable) == 1 else None


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
    "talk_to_npc",
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
        result["bundlePath"] = str(local_video)
        result["bytes"] = dropbox_video.stat().st_size if dropbox_video.exists() else None
    except OSError as exc:
        result["warnings"].append(f"Rendered video locally but could not copy it to {output_dir}: {exc}")
        result["localVideoPath"] = str(local_video)
        cleanup_video_temp(frame_dir=frame_dir, local_video=None, result=result)
        return result
    cleanup_video_temp(frame_dir=frame_dir, local_video=None, result=result)
    result["localVideoCleaned"] = False
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
        return execute_advance_battle_dialogue(pyboy, **common, max_inputs=int(args.get("maxInputs", 32)))
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
    if skill_id == "handle_move_learning_prompt":
        raw_choice = str(args.get("choice", args.get("decision", args.get("response", "skip")))).strip().lower()
        choice = "replace" if raw_choice in {"replace", "learn", "yes", "accept", "forget"} else "skip"
        forget_move = args.get("forgetMove", args.get("forget_move", args.get("move")))
        if isinstance(forget_move, dict):
            forget_move = (
                forget_move.get("name")
                or forget_move.get("moveName")
                or forget_move.get("slot")
                or forget_move.get("moveId")
            )
        if choice == "replace" and forget_move is None:
            return missing_skill_argument_result(skill_id, "forgetMove")
        return execute_handle_move_learning_prompt(
            pyboy,
            **common,
            choice=choice,
            forget_move=forget_move,
        )
    if skill_id == "handle_trainer_switch_prompt":
        raw_choice = str(args.get("choice", args.get("decision", args.get("response", "keep")))).strip().lower()
        choice = "switch" if raw_choice in {"switch", "change", "yes", "accept"} else "keep"
        target = args.get("target")
        if isinstance(target, dict):
            target = target.get("slot") or target.get("nickname") or target.get("species") or target.get("name")
        if choice == "switch" and target is None:
            return missing_skill_argument_result(skill_id, "target")
        if isinstance(target, str) and target.isdigit():
            target = int(target)
        return execute_handle_trainer_switch_prompt(
            pyboy,
            **common,
            choice=choice,
            target=target,
            max_wait_frames=int(args.get("maxWaitFrames", 1200)),
        )
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
        return execute_resolve_battle_outcome_dialogue_bundle(
            pyboy,
            **common,
            max_inputs=int(args.get("maxInputs", 16)),
        )
    if skill_id == "run_from_wild_battle":
        return execute_run_from_wild_battle(pyboy, **common, max_wait_frames=int(args.get("maxWaitFrames", 900)))
    if skill_id == "switch_party_member":
        target = args.get("target")
        if isinstance(target, dict):
            target = target.get("slot") or target.get("nickname") or target.get("species") or target.get("name")
        if target is None:
            return missing_skill_argument_result(skill_id, "target")
        if isinstance(target, str) and target.isdigit():
            target = int(target)
        return execute_switch_party_member(
            pyboy,
            **common,
            target=target,
            max_wait_frames=int(args.get("maxWaitFrames", 1200)),
        )
    if skill_id == "talk_to_npc":
        target = str(args.get("target") or "").strip()
        if not target:
            return missing_skill_argument_result(skill_id, "target")
        return execute_talk_to_npc(pyboy, **common, target=target)
    if skill_id == "use_move":
        requested_move = args.get("move", args.get("requestedMove"))
        if requested_move is None:
            requested_move = args.get("moveName", args.get("moveId"))
        if requested_move is None:
            return missing_skill_argument_result(skill_id, "move")
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
    raise ValueError(f"Unsupported chapter segment skill: {skill_id}")


def missing_skill_argument_result(skill_id: str, argument: str) -> dict[str, Any]:
    return {
        "actionStarted": False,
        "skill_id": skill_id,
        "status": "blocked",
        "summary": f"{skill_id} requires the {argument} argument before input can start.",
        "evidence": [f"missing_argument={argument}", "action_started=false"],
        "warnings": ["invalid_semantic_tool_arguments"],
    }


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
