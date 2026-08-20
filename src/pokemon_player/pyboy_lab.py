from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pokemon_player.state_inspector import StateInspector
from pokemon_player.state_model import GameSnapshot


@dataclass(frozen=True)
class ButtonInput:
    button: str
    hold_frames: int = 1
    settle_frames: int = 1


def require_pyboy():
    try:
        from pyboy import PyBoy
    except ImportError as exc:
        raise RuntimeError(
            "PyBoy is not installed. Create a local environment and install project dependencies."
        ) from exc
    return PyBoy


def open_emulator(rom_path: str | Path, *, window: str = "null", ram_path: str | Path | None = None):
    PyBoy = require_pyboy()
    kwargs = {"window": window, "sound_emulated": False, "no_input": False}
    if ram_path is not None:
        kwargs["ram_file"] = Path(ram_path).open("rb")
    return PyBoy(str(rom_path), **kwargs)


def save_state(pyboy: object, state_path: str | Path) -> None:
    with Path(state_path).open("wb") as handle:
        pyboy.save_state(handle)


def save_screenshot(pyboy: object, image_path: str | Path) -> None:
    image = pyboy.screen.image
    if callable(image):
        image = image()
    Path(image_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(image_path)


def load_state(pyboy: object, state_path: str | Path) -> None:
    with Path(state_path).open("rb") as handle:
        pyboy.load_state(handle)


def run_button_trace(pyboy: object, trace: list[ButtonInput], *, render: bool = False) -> None:
    for step in trace:
        pyboy.button(step.button, step.hold_frames)
        pyboy.tick(step.hold_frames, render)
        if step.settle_frames:
            pyboy.tick(step.settle_frames, render)


def snapshot(pyboy: object) -> GameSnapshot:
    try:
        game_area = pyboy.game_area()
    except Exception:
        game_area = None
    return StateInspector(pyboy.memory).inspect(game_area=game_area)
