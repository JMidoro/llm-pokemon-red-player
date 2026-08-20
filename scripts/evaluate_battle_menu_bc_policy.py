from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.battle_menu_bc import load_policy, predict_action  # noqa: E402
from pokemon_player.battle_menu_env import (  # noqa: E402
    BattleMenuEnvConfig,
    BattleMenuThrowEnv,
    valid_action_mask_for,
)


DEFAULT_STATE_DIR = ROOT / "research" / "policy-states" / "local" / "battle_menu_throw"


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a behavior-cloned battle-menu policy.")
    parser.add_argument("model", help="Path to a battle-menu BC .pt model.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state", action="append", dest="states", help="Initial battle state.")
    parser.add_argument("--policy-states-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--episodes-per-state", type=int, default=3)
    parser.add_argument(
        "--mask",
        choices=["true", "false"],
        default="true",
        help="Constrain predictions to valid actions for the current UI state.",
    )
    parser.add_argument(
        "--deterministic",
        choices=["true", "false"],
        default="true",
        help="Use argmax actions. Set false to sample from the cloned policy distribution.",
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--action-frames", type=int, default=48)
    parser.add_argument("--window", choices=["SDL2", "null"], default="SDL2")
    parser.add_argument("--render", choices=["true", "false"], default="true")
    parser.add_argument(
        "--out",
        default=str(ROOT / "research" / "artifacts" / "battle-menu-bc-policy-evals"),
    )
    args = parser.parse_args()
    require_interactive_battle_window(args.window, args.render)

    rng = random.Random(args.seed)
    states = resolve_states(args.states, Path(args.policy_states_dir))
    missing = [str(path) for path in states if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing state file(s): {missing}")

    model, checkpoint = load_policy(args.model)
    run_dir = Path(args.out) / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True)
    env = BattleMenuThrowEnv(
        BattleMenuEnvConfig(
            rom_path=Path(args.rom),
            state_paths=states,
            window=args.window,
            render=args.render == "true",
            action_frames=args.action_frames,
            max_steps=args.max_steps,
            screenshot_root=run_dir / "_screens",
        )
    )
    use_mask = args.mask == "true"
    deterministic = args.deterministic == "true"
    episodes = []
    raw_invalid_predictions = 0
    total_predictions = 0
    try:
        for state in states:
            for index in range(args.episodes_per_state):
                obs, _ = env.reset(
                    options={"state_path": str(state)},
                    seed=rng.randrange(1_000_000),
                )
                terminated = False
                truncated = False
                total_reward = 0.0
                last_info = {}
                while not (terminated or truncated):
                    facts = env.previous_facts
                    if facts is None:
                        break
                    mask = valid_action_mask_for(
                        facts,
                        item_menu_steps=env._item_menu_steps,
                        in_item_flow=env._in_item_flow,
                    )
                    raw_action = predict_action(
                        model,
                        obs,
                        deterministic=deterministic,
                    )
                    raw_invalid_predictions += int(not bool(mask[raw_action]))
                    total_predictions += 1
                    action = predict_action(
                        model,
                        obs,
                        valid_mask=mask if use_mask else None,
                        deterministic=deterministic,
                    )
                    obs, reward, terminated, truncated, last_info = env.step(action)
                    total_reward += reward
                episode_dir = run_dir / state.stem / f"episode-{index + 1:03d}"
                report = env.save_episode(episode_dir)
                episodes.append(
                    {
                        "state": str(state),
                        "episode": index + 1,
                        "steps": len(env.trace),
                        "total_reward": total_reward,
                        "terminated": terminated,
                        "truncated": truncated,
                        "throw_initiated": report.get("throw_initiated", False),
                        "action_counts": count_actions(report["steps"]),
                        "reason": last_info.get("terminated_reason"),
                        "final_facts": report["final_facts"],
                        "trace_file": str(episode_dir / "trace.json"),
                    }
                )
    finally:
        env.close()

    reason_counts = Counter(episode["reason"] or "truncated" for episode in episodes)
    successes = sum(1 for episode in episodes if episode["reason"] == "ball_decreased")
    throws = sum(1 for episode in episodes if episode["throw_initiated"])
    manifest = {
        "schema": "battle_menu_bc_policy_eval_v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "model": str(args.model),
        "model_metadata": checkpoint.get("metadata", {}),
        "mask": use_mask,
        "deterministic": deterministic,
        "seed": args.seed,
        "states": [str(path) for path in states],
        "episodes_per_state": args.episodes_per_state,
        "successes": successes,
        "throws_initiated": throws,
        "raw_invalid_predictions": raw_invalid_predictions,
        "total_predictions": total_predictions,
        "terminal_reasons": dict(sorted(reason_counts.items())),
        "episodes": episodes,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"BC eval run: {run_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Successes: {successes}/{len(episodes)}")
    print(f"Throws initiated: {throws}/{len(episodes)}")
    print(f"Terminal reasons: {dict(sorted(reason_counts.items()))}")
    print(f"Raw invalid predictions: {raw_invalid_predictions}/{total_predictions}")
    for episode in episodes:
        print(
            f"{Path(episode['state']).stem} #{episode['episode']}: "
            f"steps={episode['steps']} reward={episode['total_reward']:.2f} "
            f"throw_initiated={episode['throw_initiated']} "
            f"reason={episode['reason'] or 'truncated'} "
            f"actions={episode['action_counts']}"
        )
    return 0


def resolve_states(raw_states: list[str] | None, policy_states_dir: Path) -> tuple[Path, ...]:
    if raw_states:
        return tuple(Path(path) for path in raw_states)
    discovered = tuple(sorted(policy_states_dir.glob("*.state")))
    if not discovered:
        raise FileNotFoundError(f"No .state files found in {policy_states_dir}")
    return discovered


def require_interactive_battle_window(window: str, render: str) -> None:
    if window != "SDL2" or render != "true":
        raise SystemExit(
            "Battle-menu policy input currently requires --window SDL2 --render true. "
            "PyBoy window=null or render=false can load battle states but does not reliably "
            "deliver menu button presses after savestate load."
        )


def count_actions(steps: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        action_name = str(step.get("action_name", "unknown"))
        counts[action_name] = counts.get(action_name, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
