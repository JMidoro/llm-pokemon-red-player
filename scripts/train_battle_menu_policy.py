from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.battle_menu_env import BattleMenuEnvConfig, BattleMenuThrowEnv  # noqa: E402


DEFAULT_STATE = ROOT / "research" / "skill-states" / "local" / "attempt_catch" / "success_before.state"


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the throw-ball battle-menu micro policy.")
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state", action="append", dest="states", help="Initial battle state.")
    parser.add_argument(
        "--policy-states-dir",
        default=str(ROOT / "research" / "policy-states" / "local" / "battle_menu_throw"),
        help="Directory of policy-training .state files. Used when --state is omitted.",
    )
    parser.add_argument("--timesteps", type=int, default=10_000)
    parser.add_argument("--resume-model", help="Optional SB3 PPO .zip to continue training.")
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--ent-coef", type=float, default=0.03)
    parser.add_argument("--gamma", type=float, default=0.90)
    parser.add_argument("--clip-range", type=float, default=0.2)
    parser.add_argument("--n-steps", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-steps", type=int, default=48)
    parser.add_argument("--action-frames", type=int, default=48)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--window", choices=["SDL2", "null"], default="SDL2")
    parser.add_argument("--render", choices=["true", "false"], default="true")
    parser.add_argument(
        "--out",
        default=str(ROOT / "research" / "artifacts" / "battle-menu-policies"),
    )
    args = parser.parse_args()
    require_interactive_battle_window(args.window, args.render)

    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.monitor import Monitor
        from stable_baselines3.common.utils import get_schedule_fn
    except ImportError as exc:
        raise RuntimeError(
            "RL dependencies are not installed. Run: "
            ".\\.venv\\Scripts\\python -m pip install -e .[rl]"
        ) from exc

    states = resolve_states(args.states, Path(args.policy_states_dir))
    missing = [str(path) for path in states if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing state file(s): {missing}")

    run_dir = Path(args.out) / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True)
    monitor_path = run_dir / "monitor.csv"
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
    monitored = Monitor(
        env,
        filename=str(monitor_path),
        info_keywords=("terminated_reason", "throw_initiated"),
    )
    try:
        if args.resume_model:
            model = PPO.load(args.resume_model, env=monitored, verbose=1)
            model.learning_rate = args.learning_rate
            model.lr_schedule = get_schedule_fn(args.learning_rate)
            model.ent_coef = args.ent_coef
            model.gamma = args.gamma
            model.clip_range = get_schedule_fn(args.clip_range)
            model.learn(total_timesteps=args.timesteps, reset_num_timesteps=False)
        else:
            model = PPO(
                "MultiInputPolicy",
                monitored,
                verbose=1,
                n_steps=args.n_steps,
                batch_size=args.batch_size,
                gamma=args.gamma,
                learning_rate=args.learning_rate,
                ent_coef=args.ent_coef,
                clip_range=args.clip_range,
                seed=args.seed,
            )
            model.learn(total_timesteps=args.timesteps)
        model_path = run_dir / "ppo_battle_menu_throw.zip"
        model.save(model_path)
    finally:
        monitored.close()

    episode_summary = summarize_monitor(monitor_path)

    manifest = {
        "schema": "battle_menu_policy_train_run_v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "model": str(model_path),
        "monitor": str(monitor_path),
        "resume_model": args.resume_model,
        "timesteps": args.timesteps,
        "learning_rate": args.learning_rate,
        "ent_coef": args.ent_coef,
        "gamma": args.gamma,
        "clip_range": args.clip_range,
        "n_steps": args.n_steps,
        "batch_size": args.batch_size,
        "max_steps": args.max_steps,
        "action_frames": args.action_frames,
        "seed": args.seed,
        "window": args.window,
        "render": args.render == "true",
        "states": [str(path) for path in states],
        "episode_summary": episode_summary,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Policy run: {run_dir}")
    print(f"Model: {model_path}")
    print(f"Manifest: {manifest_path}")
    print(
        "Episodes: "
        f"{episode_summary['episodes']} | "
        f"throws={episode_summary['throws_initiated']} | "
        f"mean_reward={episode_summary['mean_reward']:.2f}"
    )
    if episode_summary["terminal_reasons"]:
        print(f"Terminal reasons: {episode_summary['terminal_reasons']}")
    return 0


def summarize_monitor(monitor_path: Path) -> dict[str, object]:
    if not monitor_path.exists():
        return {
            "episodes": 0,
            "throws_initiated": 0,
            "mean_reward": 0.0,
            "terminal_reasons": {},
        }

    rewards: list[float] = []
    throws = 0
    reasons: Counter[str] = Counter()
    with monitor_path.open(newline="", encoding="utf-8") as handle:
        rows = (line for line in handle if not line.startswith("#"))
        for row in csv.DictReader(rows):
            if not row:
                continue
            reward = row.get("r")
            if reward not in (None, ""):
                rewards.append(float(reward))
            if row.get("throw_initiated") == "True":
                throws += 1
            reason = row.get("terminated_reason") or "truncated"
            reasons[str(reason)] += 1

    mean_reward = sum(rewards) / len(rewards) if rewards else 0.0
    return {
        "episodes": len(rewards),
        "throws_initiated": throws,
        "mean_reward": mean_reward,
        "terminal_reasons": dict(sorted(reasons.items())),
    }


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
