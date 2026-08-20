from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.battle_menu_env import (  # noqa: E402
    ACTION_NAMES,
    BattleMenuEnvConfig,
    BattleMenuThrowEnv,
)


DEFAULT_STATE = ROOT / "research" / "skill-states" / "local" / "attempt_catch" / "success_before.state"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect battle-menu traces for the throw-ball micro policy."
    )
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state", action="append", dest="states", help="Initial battle state.")
    parser.add_argument(
        "--policy-states-dir",
        default=str(ROOT / "research" / "policy-states" / "local" / "battle_menu_throw"),
        help="Directory of policy-training .state files. Used when --state is omitted.",
    )
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument("--max-steps", type=int, default=48)
    parser.add_argument("--action-frames", type=int, default=48)
    parser.add_argument("--policy", choices=["random", "scripted", "expert"], default="random")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--window", choices=["SDL2", "null"], default="SDL2")
    parser.add_argument("--render", choices=["true", "false"], default="true")
    parser.add_argument(
        "--out",
        default=str(ROOT / "research" / "artifacts" / "battle-menu-traces"),
    )
    args = parser.parse_args()
    require_interactive_battle_window(args.window, args.render)

    states = resolve_states(args.states, Path(args.policy_states_dir))
    missing = [str(path) for path in states if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing state file(s): {missing}")

    run_dir = Path(args.out) / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True)
    config = BattleMenuEnvConfig(
        rom_path=Path(args.rom),
        state_paths=states,
        window=args.window,
        render=args.render == "true",
        action_frames=args.action_frames,
        max_steps=args.max_steps,
        screenshot_root=run_dir / "_screens",
    )
    rng = random.Random(args.seed)
    env = BattleMenuThrowEnv(config)
    summaries = []
    try:
        for episode in range(1, args.episodes + 1):
            _, info = env.reset(seed=rng.randrange(1_000_000))
            terminated = False
            truncated = False
            total_reward = 0.0
            while not (terminated or truncated):
                action = choose_action(args.policy, len(env.trace), rng, env)
                _, reward, terminated, truncated, step_info = env.step(action)
                total_reward += reward
            episode_dir = run_dir / f"episode-{episode:03d}"
            report = env.save_episode(episode_dir)
            summaries.append(
                {
                    "episode": episode,
                    "state_path": info["state_path"],
                    "steps": len(env.trace),
                    "total_reward": total_reward,
                    "terminated": terminated,
                    "truncated": truncated,
                    "throw_initiated": report.get("throw_initiated", False),
                    "final_facts": report["final_facts"],
                    "last_step": step_info,
                    "trace_file": str(episode_dir / "trace.json"),
                }
            )
    finally:
        env.close()

    manifest = {
        "schema": "battle_menu_trace_manifest_v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "policy": args.policy,
        "actions": list(ACTION_NAMES),
        "episodes": summaries,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"Trace run: {run_dir}")
    print(f"Manifest: {manifest_path}")
    for summary in summaries:
        reason = summary["last_step"].get("terminated_reason") if summary["last_step"] else None
        print(
            f"Episode {summary['episode']:03d}: steps={summary['steps']} "
            f"reward={summary['total_reward']:.2f} "
            f"throw_initiated={summary['throw_initiated']} reason={reason or 'truncated'}"
        )
    return 0


def choose_action(policy: str, step_index: int, rng: random.Random, env: BattleMenuThrowEnv) -> int:
    if policy == "random":
        return rng.randrange(len(ACTION_NAMES))
    if policy == "expert":
        from pokemon_player.battle_menu_env import expert_action_for

        facts = env.previous_facts
        if facts is None:
            return ACTION_NAMES.index("a")
        return ACTION_NAMES.index(
            expert_action_for(
                facts,
                item_menu_steps=env._item_menu_steps,
                in_item_flow=env._in_item_flow,
            )
        )
    # Known-good-ish route from a standard battle action menu with cursor at FIGHT:
    # down -> ITEM, A -> bag, A -> choose first item/ball.
    scripted = ["down", "a", "a"]
    name = scripted[min(step_index, len(scripted) - 1)]
    return ACTION_NAMES.index(name)


def require_interactive_battle_window(window: str, render: str) -> None:
    if window != "SDL2" or render != "true":
        raise SystemExit(
            "Battle-menu policy input currently requires --window SDL2 --render true. "
            "PyBoy window=null or render=false can load battle states but does not reliably "
            "deliver menu button presses after savestate load."
        )


def resolve_states(raw_states: list[str] | None, policy_states_dir: Path) -> tuple[Path, ...]:
    if raw_states:
        return tuple(Path(path) for path in raw_states)
    discovered = tuple(sorted(policy_states_dir.glob("*.state")))
    if discovered:
        return discovered
    return (DEFAULT_STATE,)


if __name__ == "__main__":
    raise SystemExit(main())
