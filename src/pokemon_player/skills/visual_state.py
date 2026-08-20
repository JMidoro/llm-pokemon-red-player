from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from pokemon_player.battle_ui import dark_ratio


@dataclass(frozen=True)
class UiVisualState:
    bottom_text_box: bool
    upper_menu: bool


def inspect_ui_visual_state(path: str | Path | None) -> UiVisualState:
    if path is None:
        return UiVisualState(bottom_text_box=False, upper_menu=False)
    image_path = Path(path)
    if not image_path.exists():
        return UiVisualState(bottom_text_box=False, upper_menu=False)

    stat = image_path.stat()
    return _inspect_ui_visual_state_cached(str(image_path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=128)
def _inspect_ui_visual_state_cached(path: str, mtime_ns: int, size: int) -> UiVisualState:
    del mtime_ns, size
    image = Image.open(path).convert("L")
    width, height = image.size
    if width < 160 or height < 144:
        return UiVisualState(bottom_text_box=False, upper_menu=False)

    return UiVisualState(
        bottom_text_box=_has_bottom_text_box(image),
        upper_menu=_has_upper_menu_box(image),
    )


def _has_bottom_text_box(image: Image.Image) -> bool:
    top = dark_ratio(image.crop((0, 94, 160, 103)))
    left = dark_ratio(image.crop((0, 96, 8, 144)))
    right = dark_ratio(image.crop((152, 96, 160, 144)))
    bottom = dark_ratio(image.crop((0, 136, 160, 144)))
    inner = dark_ratio(image.crop((8, 104, 152, 136)))
    return top > 0.30 and left > 0.20 and right > 0.20 and bottom > 0.30 and inner < 0.18


def _has_upper_menu_box(image: Image.Image) -> bool:
    right_edge = dark_ratio(image.crop((150, 12, 160, 136)))
    top_edge = dark_ratio(image.crop((75, 12, 160, 22)))
    left_edge = dark_ratio(image.crop((75, 12, 84, 136)))
    return right_edge > 0.20 and top_edge > 0.18 and left_edge > 0.15
