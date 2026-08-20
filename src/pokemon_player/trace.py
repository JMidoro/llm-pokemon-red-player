from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pokemon_player.pyboy_lab import ButtonInput


ALLOWED_BUTTONS = {
    "a",
    "b",
    "start",
    "select",
    "up",
    "down",
    "left",
    "right",
}


def button_input_from_dict(raw: dict[str, Any]) -> ButtonInput:
    button = str(raw["button"]).lower()
    if button not in ALLOWED_BUTTONS:
        raise ValueError(f"Unsupported button {button!r}; expected one of {sorted(ALLOWED_BUTTONS)}")

    hold_frames = int(raw.get("hold_frames", 1))
    settle_frames = int(raw.get("settle_frames", 1))
    if hold_frames < 1:
        raise ValueError("hold_frames must be at least 1")
    if settle_frames < 0:
        raise ValueError("settle_frames must be non-negative")
    return ButtonInput(button=button, hold_frames=hold_frames, settle_frames=settle_frames)


def load_trace(path: str | Path) -> list[ButtonInput]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Trace files must contain a JSON list of button steps.")
    return [button_input_from_dict(step) for step in raw]


def dump_trace(trace: list[ButtonInput]) -> str:
    raw = [
        {
            "button": step.button,
            "hold_frames": step.hold_frames,
            "settle_frames": step.settle_frames,
        }
        for step in trace
    ]
    return json.dumps(raw, indent=2)

