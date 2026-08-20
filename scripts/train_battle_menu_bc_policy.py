from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.battle_menu_bc import build_policy, save_policy  # noqa: E402
from pokemon_player.battle_menu_env import (  # noqa: E402
    ACTION_NAMES,
    BattleMenuEnvConfig,
    BattleMenuThrowEnv,
    expert_action_for,
)


DEFAULT_STATE = ROOT / "research" / "skill-states" / "local" / "attempt_catch" / "success_before.state"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train a behavior-cloned throw-ball battle-menu policy from expert traces."
    )
    parser.add_argument("--rom", default=str(ROOT / "research" / "PokemonRed.gb"))
    parser.add_argument("--state", action="append", dest="states", help="Initial battle state.")
    parser.add_argument(
        "--policy-states-dir",
        default=str(ROOT / "research" / "policy-states" / "local" / "battle_menu_throw"),
        help="Directory of policy-training .state files. Used when --state is omitted.",
    )
    parser.add_argument("--rollouts-per-state", type=int, default=8)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--action-frames", type=int, default=48)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--window", choices=["SDL2", "null"], default="SDL2")
    parser.add_argument("--render", choices=["true", "false"], default="true")
    parser.add_argument(
        "--out",
        default=str(ROOT / "research" / "artifacts" / "battle-menu-bc-policies"),
    )
    args = parser.parse_args()
    require_interactive_battle_window(args.window, args.render)

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required. Install RL dependencies with: "
            ".\\.venv\\Scripts\\python -m pip install -e .[rl]"
        ) from exc

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

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

    samples, labels, trace_summary = collect_expert_samples(
        config,
        states=states,
        rollouts_per_state=args.rollouts_per_state,
        seed=args.seed,
    )
    if len(labels) == 0:
        raise RuntimeError("No expert samples were collected.")

    model = build_policy(hidden_size=args.hidden_size)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    loss_fn = torch.nn.CrossEntropyLoss()
    x = torch.as_tensor(samples, dtype=torch.float32)
    y = torch.as_tensor(labels, dtype=torch.long)

    losses: list[float] = []
    for _epoch in range(args.epochs):
        order = torch.randperm(len(y))
        epoch_losses: list[float] = []
        for start in range(0, len(y), args.batch_size):
            batch = order[start : start + args.batch_size]
            logits = model(x[batch])
            loss = loss_fn(logits, y[batch])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_losses.append(float(loss.item()))
        losses.append(sum(epoch_losses) / len(epoch_losses))

    with torch.no_grad():
        train_predictions = torch.argmax(model(x), dim=1)
        train_accuracy = float((train_predictions == y).float().mean().item())

    model_path = run_dir / "bc_battle_menu_throw.pt"
    metadata = {
        "created_utc": datetime.now(UTC).isoformat(),
        "states": [str(path) for path in states],
        "rollouts_per_state": args.rollouts_per_state,
        "max_steps": args.max_steps,
        "action_frames": args.action_frames,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "seed": args.seed,
        "train_accuracy": train_accuracy,
    }
    save_policy(model_path, model, hidden_size=args.hidden_size, metadata=metadata)

    action_counts = Counter(ACTION_NAMES[int(label)] for label in labels)
    manifest = {
        "schema": "battle_menu_bc_policy_train_run_v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "model": str(model_path),
        "states": [str(path) for path in states],
        "samples": int(len(labels)),
        "action_counts": dict(sorted(action_counts.items())),
        "trace_summary": trace_summary,
        "epochs": args.epochs,
        "final_loss": losses[-1],
        "train_accuracy": train_accuracy,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(f"BC policy run: {run_dir}")
    print(f"Model: {model_path}")
    print(f"Manifest: {manifest_path}")
    print(
        f"Samples: {len(labels)} | train_accuracy={train_accuracy:.3f} "
        f"| final_loss={losses[-1]:.4f}"
    )
    print(f"Expert action counts: {dict(sorted(action_counts.items()))}")
    print(f"Expert terminal reasons: {trace_summary['terminal_reasons']}")
    return 0


def collect_expert_samples(
    config: BattleMenuEnvConfig,
    *,
    states: tuple[Path, ...],
    rollouts_per_state: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    rng = random.Random(seed)
    sample_rows: list[np.ndarray] = []
    labels: list[int] = []
    terminal_reasons: Counter[str] = Counter()
    throws = 0
    env = BattleMenuThrowEnv(config)
    try:
        for state in states:
            for _ in range(rollouts_per_state):
                obs, _info = env.reset(options={"state_path": str(state)}, seed=rng.randrange(1_000_000))
                terminated = False
                truncated = False
                last_info = {}
                while not (terminated or truncated):
                    facts = env.previous_facts
                    if facts is None:
                        break
                    action_name = expert_action_for(
                        facts,
                        item_menu_steps=env._item_menu_steps,
                        in_item_flow=env._in_item_flow,
                    )
                    action = ACTION_NAMES.index(action_name)
                    sample_rows.append(np.asarray(obs["state"], dtype=np.float32) / 255.0)
                    labels.append(action)
                    obs, _reward, terminated, truncated, last_info = env.step(action)
                if env._throw_initiated:
                    throws += 1
                terminal_reasons[last_info.get("terminated_reason") or "truncated"] += 1
    finally:
        env.close()

    return (
        np.vstack(sample_rows),
        np.asarray(labels, dtype=np.int64),
        {
            "episodes": sum(terminal_reasons.values()),
            "throws_initiated": throws,
            "terminal_reasons": dict(sorted(terminal_reasons.items())),
        },
    )


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
