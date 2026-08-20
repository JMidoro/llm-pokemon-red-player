from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from pokemon_player.battle_menu_env import ACTION_NAMES, FACT_VECTOR_LEN


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required for battle-menu behavior cloning. "
            "Install the RL extra with: .\\.venv\\Scripts\\python -m pip install -e .[rl]"
        ) from exc
    return torch


def build_policy(hidden_size: int = 64) -> Any:
    torch = _torch()
    return torch.nn.Sequential(
        torch.nn.Linear(FACT_VECTOR_LEN, hidden_size),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_size, hidden_size),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden_size, len(ACTION_NAMES)),
    )


def state_tensor_from_observation(obs: dict[str, Any]) -> Any:
    torch = _torch()
    state = np.asarray(obs["state"], dtype=np.float32) / 255.0
    return torch.as_tensor(state, dtype=torch.float32).unsqueeze(0)


def predict_action(
    model: Any,
    obs: dict[str, Any],
    *,
    valid_mask: np.ndarray | None = None,
    deterministic: bool = True,
) -> int:
    torch = _torch()
    model.eval()
    with torch.no_grad():
        logits = model(state_tensor_from_observation(obs))[0]
        if valid_mask is not None:
            mask = torch.as_tensor(valid_mask, dtype=torch.bool)
            logits = logits.masked_fill(~mask, -1_000_000.0)
        if deterministic:
            return int(torch.argmax(logits).item())
        distribution = torch.distributions.Categorical(logits=logits)
        return int(distribution.sample().item())


def save_policy(
    path: str | Path,
    model: Any,
    *,
    hidden_size: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    torch = _torch()
    torch.save(
        {
            "schema": "battle_menu_bc_policy_v1",
            "actions": list(ACTION_NAMES),
            "input_size": FACT_VECTOR_LEN,
            "hidden_size": hidden_size,
            "state_dict": model.state_dict(),
            "metadata": metadata or {},
        },
        path,
    )


def load_policy(path: str | Path) -> tuple[Any, dict[str, Any]]:
    torch = _torch()
    checkpoint = torch.load(path, map_location="cpu")
    if checkpoint.get("schema") != "battle_menu_bc_policy_v1":
        raise ValueError(f"Unsupported battle-menu BC policy schema in {path}")
    if checkpoint.get("actions") != list(ACTION_NAMES):
        raise ValueError("Battle-menu BC policy action order does not match this runtime.")
    hidden_size = int(checkpoint.get("hidden_size", 64))
    model = build_policy(hidden_size=hidden_size)
    model.load_state_dict(checkpoint["state_dict"])
    return model, checkpoint
