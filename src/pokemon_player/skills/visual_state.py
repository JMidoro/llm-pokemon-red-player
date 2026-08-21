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
    compact_choice: bool = False


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
        compact_choice=_has_compact_upper_left_choice(image),
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
    right_interior = dark_ratio(image.crop((84, 22, 150, 128)))
    right_box = (
        right_edge > 0.20
        and top_edge > 0.18
        and left_edge > 0.15
        and right_interior < 0.30
    )

    # Choice surfaces such as the PC menu use a wide box on the upper left.
    # Detect that layout separately instead of allowing dark map borders to
    # masquerade as a menu. Real menu interiors are predominantly light;
    # Pewter Gym's top/right walls satisfy the old edge ratios but not this
    # interior check.
    left_right_edge = dark_ratio(image.crop((120, 0, 130, 80)))
    left_top_edge = dark_ratio(image.crop((0, 0, 128, 10)))
    left_edge = dark_ratio(image.crop((0, 0, 10, 80)))
    left_interior = dark_ratio(image.crop((8, 8, 120, 72)))
    left_box = (
        left_right_edge > 0.20
        and left_top_edge > 0.18
        and left_edge > 0.15
        and left_interior < 0.20
    )

    return right_box or left_box or _has_compact_upper_left_choice(image)


def _has_compact_upper_left_choice(image: Image.Image) -> bool:
    # Trainer Shift and move-learning prompts use a compact YES/NO box in the
    # upper left while keeping the ordinary battle dialogue box along the bottom.
    choice_right_edge = dark_ratio(image.crop((48, 48, 58, 97)))
    choice_top_edge = dark_ratio(image.crop((0, 48, 56, 58)))
    choice_left_edge = dark_ratio(image.crop((0, 48, 10, 97)))
    choice_bottom_edge = dark_ratio(image.crop((0, 88, 56, 98)))
    choice_interior = dark_ratio(image.crop((8, 58, 48, 88)))
    compact_left = (
        _has_bottom_text_box(image)
        and choice_right_edge > 0.05
        and choice_top_edge > 0.06
        and choice_left_edge > 0.15
        and choice_bottom_edge > 0.18
        and choice_interior < 0.30
    )

    right_edge = dark_ratio(image.crop((152, 48, 160, 102)))
    top_edge = dark_ratio(image.crop((112, 48, 160, 58)))
    left_edge = dark_ratio(image.crop((112, 48, 120, 102)))
    bottom_edge = dark_ratio(image.crop((112, 92, 160, 102)))
    interior = dark_ratio(image.crop((120, 58, 152, 92)))
    compact_right = (
        _has_bottom_text_box(image)
        and right_edge > 0.18
        and 0.003 < top_edge < 0.05
        and left_edge > 0.18
        and bottom_edge > 0.25
        and interior < 0.30
    )
    return compact_left or compact_right
