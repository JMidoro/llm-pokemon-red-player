from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.pyboy_lab import open_emulator  # noqa: E402
from pokemon_player.rom import fingerprint_rom  # noqa: E402
from pokemon_player.skill_execution import (  # noqa: E402
    execute_advance_battle_dialogue,
    execute_advance_dialogue,
    execute_attempt_catch,
    execute_attempt_catch_chain,
    execute_choose_starter,
    execute_close_menu_or_cancel,
    execute_enter_grass_search_loop,
    execute_enter_nickname_text,
    execute_handle_nickname_prompt,
    execute_navigate_within_pallet_region,
    execute_navigate_within_pewter_region,
    execute_navigate_within_viridian_forest_region,
    execute_overworld_rearrange_party,
    execute_purchase_pokemart_item,
    execute_recover_to_overworld,
    execute_run_from_wild_battle,
    execute_switch_party_member,
    execute_use_move,
    execute_walk_local_direction,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a typed skill from a PyBoy state.")
    parser.add_argument(
        "skill",
        choices=[
            "advance_battle_dialogue",
            "advance_dialogue",
            "attempt_catch",
            "choose_starter",
            "close_menu_or_cancel",
            "enter_grass_search_loop",
            "enter_nickname_text",
            "handle_nickname_prompt",
            "navigate_within_pallet_region",
            "navigate_within_pewter_region",
            "navigate_within_viridian_forest_region",
            "overworld_rearrange_party",
            "purchase_pokemart_item",
            "recover_to_overworld",
            "run_from_wild_battle",
            "switch_party_member",
            "use_move",
            "walk_local_direction",
        ],
    )
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state-in", required=True)
    parser.add_argument(
        "--execution-mode",
        choices=["headful", "headless"],
        default="headful",
        help="Headful uses an SDL2 window and rendered ticks; headless uses the null window.",
    )
    parser.add_argument(
        "--run-root",
        default=str(ROOT / "research" / "artifacts" / "skill-runs"),
        help="Directory where run artifacts will be written.",
    )
    parser.add_argument("--window", choices=["auto", "SDL2", "null"], default="auto")
    parser.add_argument(
        "--render",
        choices=["auto", "true", "false"],
        default="auto",
        help="Whether skill execution ticks render frames.",
    )
    parser.add_argument("--post-load-settle-frames", type=int, default=60)
    parser.add_argument("--max-wait-frames", type=int, default=900)
    parser.add_argument(
        "--max-battle-dialogue-inputs",
        type=int,
        default=16,
        help="Maximum bounded A presses for advance_battle_dialogue.",
    )
    parser.add_argument(
        "--throw-executor",
        choices=["battle-menu-controller", "battle-menu-bc", "scripted"],
        default="battle-menu-controller",
        help="Internal executor used by attempt_catch to initiate a ball throw.",
    )
    parser.add_argument(
        "--battle-menu-policy",
        help="Optional .pt behavior-cloned battle-menu policy for --throw-executor battle-menu-bc.",
    )
    parser.add_argument("--battle-menu-max-steps", type=int, default=40)
    parser.add_argument(
        "--max-recovery-inputs",
        type=int,
        default=12,
        help="Maximum bounded A/B inputs for recover_to_overworld.",
    )
    parser.add_argument(
        "--direction",
        choices=["up", "down", "left", "right"],
        default="left",
        help="Cardinal direction for walk_local_direction.",
    )
    parser.add_argument("--move", help="Requested move name or id for use_move, e.g. Water Gun.")
    parser.add_argument("--item", default="Poke Ball", help="Poke Mart item name for purchase_pokemart_item.")
    parser.add_argument("--quantity", type=int, default=1, help="Quantity for purchase_pokemart_item.")
    parser.add_argument(
        "--starter",
        choices=["bulbasaur", "charmander", "squirtle"],
        default="squirtle",
        help="Starter choice for choose_starter.",
    )
    parser.add_argument(
        "--target",
        help="Target party member for switch_party_member or overworld_rearrange_party, either a party slot number or species/nickname.",
    )
    parser.add_argument(
        "--destination-slot",
        type=int,
        default=1,
        help="Destination party slot for overworld_rearrange_party.",
    )
    parser.add_argument(
        "--target-landmark",
        default="forest_grass",
        help="Target landmark for navigation skills, e.g. forest_grass or pallet_grass_entrance.",
    )
    parser.add_argument(
        "--grass-patch",
        default="current_map",
        help="Approved grass patch for enter_grass_search_loop, e.g. current_map or forest_grass.",
    )
    parser.add_argument(
        "--nickname",
        default="ABK",
        help="Uppercase A-Z nickname for enter_nickname_text, or optional starter nickname for choose_starter.",
    )
    parser.add_argument(
        "--nickname-choice",
        choices=["decline", "accept"],
        default="decline",
        help="Choice for handle_nickname_prompt.",
    )
    parser.add_argument(
        "--starter-nickname",
        help="Optional uppercase A-Z nickname for choose_starter. If omitted, starter nickname is declined.",
    )
    parser.add_argument(
        "--max-navigation-inputs",
        type=int,
        default=260,
        help="Maximum route inputs for navigate_within_viridian_forest_region.",
    )
    parser.add_argument(
        "--max-navigation-segment-expansions",
        type=int,
        default=3000,
        help="Maximum emulator-probed same-map nodes per navigation segment.",
    )
    parser.add_argument(
        "--navigation-planner-window",
        choices=["null", "SDL2"],
        default="null",
        help="Window mode for the scratch navigation planner. Use SDL2 only when debugging planner probes.",
    )
    parser.add_argument(
        "--max-grass-search-steps",
        type=int,
        default=160,
        help="Maximum pacing inputs for enter_grass_search_loop.",
    )
    parser.add_argument(
        "--max-grass-entry-expansions",
        type=int,
        default=80,
        help="Maximum emulator-probed nodes when stepping into approved grass.",
    )
    parser.add_argument(
        "--chain-until-caught-or-out-of-balls",
        action="store_true",
        help="Repeat attempt_catch in one emulator session until caught, blocked, or max attempts.",
    )
    parser.add_argument("--max-attempts", type=int, default=5)
    args = parser.parse_args()

    rom = fingerprint_rom(args.rom)
    window = resolve_window(args.execution_mode, args.window)
    render = resolve_render(args.execution_mode, args.render)
    if args.skill == "attempt_catch" and args.throw_executor in {"battle-menu-controller", "battle-menu-bc"} and (
        window != "SDL2" or not render
    ):
        raise SystemExit(
            "Battle-menu throw executors require headful SDL2/rendered execution. "
            "Use --execution-mode headful or --throw-executor scripted for the older path."
        )
    pyboy = open_emulator(rom.path, window=window)
    try:
        if args.skill == "attempt_catch":
            if args.chain_until_caught_or_out_of_balls:
                artifact = execute_attempt_catch_chain(
                    pyboy,
                    state_in=args.state_in,
                    rom=rom,
                    run_root=args.run_root,
                    render=render,
                    post_load_settle_frames=args.post_load_settle_frames,
                    max_attempts=args.max_attempts,
                    max_wait_frames=args.max_wait_frames,
                    throw_executor=args.throw_executor,
                    battle_menu_policy=args.battle_menu_policy,
                    battle_menu_max_steps=args.battle_menu_max_steps,
                )
            else:
                artifact = execute_attempt_catch(
                    pyboy,
                    state_in=args.state_in,
                    rom=rom,
                    run_root=args.run_root,
                    render=render,
                    post_load_settle_frames=args.post_load_settle_frames,
                    max_wait_frames=args.max_wait_frames,
                    throw_executor=args.throw_executor,
                    battle_menu_policy=args.battle_menu_policy,
                    battle_menu_max_steps=args.battle_menu_max_steps,
                )
        elif args.skill == "recover_to_overworld":
            artifact = execute_recover_to_overworld(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_inputs=args.max_recovery_inputs,
            )
        elif args.skill == "run_from_wild_battle":
            artifact = execute_run_from_wild_battle(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_wait_frames=args.max_wait_frames,
            )
        elif args.skill == "advance_dialogue":
            artifact = execute_advance_dialogue(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
            )
        elif args.skill == "advance_battle_dialogue":
            artifact = execute_advance_battle_dialogue(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_inputs=args.max_battle_dialogue_inputs,
            )
        elif args.skill == "close_menu_or_cancel":
            artifact = execute_close_menu_or_cancel(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
            )
        elif args.skill == "choose_starter":
            artifact = execute_choose_starter(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                starter=args.starter,
                nickname=args.starter_nickname,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_wait_frames=args.max_wait_frames,
            )
        elif args.skill == "walk_local_direction":
            artifact = execute_walk_local_direction(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                direction=args.direction,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
            )
        elif args.skill == "navigate_within_viridian_forest_region":
            artifact = execute_navigate_within_viridian_forest_region(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                target=args.target_landmark,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_inputs=args.max_navigation_inputs,
                max_segment_expansions=args.max_navigation_segment_expansions,
                planner_window=args.navigation_planner_window,
            )
        elif args.skill == "navigate_within_pallet_region":
            artifact = execute_navigate_within_pallet_region(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                target=args.target_landmark,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_inputs=args.max_navigation_inputs,
                max_segment_expansions=args.max_navigation_segment_expansions,
                emulation_speed=0 if args.execution_mode == "headless" else 1,
                planner_window=args.navigation_planner_window,
            )
        elif args.skill == "navigate_within_pewter_region":
            artifact = execute_navigate_within_pewter_region(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                target=args.target_landmark,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_inputs=args.max_navigation_inputs,
                max_segment_expansions=args.max_navigation_segment_expansions,
                emulation_speed=0 if args.execution_mode == "headless" else 1,
                planner_window=args.navigation_planner_window,
            )
        elif args.skill == "enter_grass_search_loop":
            artifact = execute_enter_grass_search_loop(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                patch=args.grass_patch,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_steps=args.max_grass_search_steps,
                max_entry_expansions=args.max_grass_entry_expansions,
            )
        elif args.skill == "enter_nickname_text":
            artifact = execute_enter_nickname_text(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                nickname=args.nickname,
            )
        elif args.skill == "handle_nickname_prompt":
            artifact = execute_handle_nickname_prompt(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                choice=args.nickname_choice,
            )
        elif args.skill == "purchase_pokemart_item":
            artifact = execute_purchase_pokemart_item(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                item=args.item,
                quantity=args.quantity,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
            )
        elif args.skill == "use_move":
            if not args.move:
                raise SystemExit("use_move requires --move, e.g. --move \"Water Gun\".")
            artifact = execute_use_move(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                requested_move=args.move,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_wait_frames=args.max_wait_frames,
            )
        elif args.skill == "switch_party_member":
            if not args.target:
                raise SystemExit("switch_party_member requires --target, e.g. --target Squirtle or --target 2.")
            target: str | int = int(args.target) if args.target.isdigit() else args.target
            artifact = execute_switch_party_member(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                target=target,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
                max_wait_frames=args.max_wait_frames,
            )
        elif args.skill == "overworld_rearrange_party":
            if not args.target:
                raise SystemExit(
                    "overworld_rearrange_party requires --target, e.g. --target Squirtle or --target 2."
                )
            target = int(args.target) if args.target.isdigit() else args.target
            artifact = execute_overworld_rearrange_party(
                pyboy,
                state_in=args.state_in,
                rom=rom,
                run_root=args.run_root,
                target=target,
                destination_slot=args.destination_slot,
                render=render,
                post_load_settle_frames=args.post_load_settle_frames,
            )
        else:
            raise ValueError(f"Unsupported skill {args.skill!r}.")
    finally:
        pyboy.stop(False)

    print(f"Skill: {artifact.result.skill_id}")
    print(f"Status: {artifact.result.status}")
    print(f"Summary: {artifact.result.summary}")
    for evidence in artifact.result.evidence:
        print(f"Evidence: {evidence}")
    for warning in artifact.result.warnings:
        print(f"Warning: {warning}")
    print(f"Run dir: {artifact.run_dir}")
    print(f"Report: {artifact.report_path}")
    return 0 if artifact.result.status in {"succeeded", "failed", "blocked", "uncertain"} else 2


def resolve_window(execution_mode: str, window: str) -> str:
    if window != "auto":
        return window
    return "SDL2" if execution_mode == "headful" else "null"


def resolve_render(execution_mode: str, render: str) -> bool:
    if render == "true":
        return True
    if render == "false":
        return False
    return execution_mode == "headful"


if __name__ == "__main__":
    raise SystemExit(main())
