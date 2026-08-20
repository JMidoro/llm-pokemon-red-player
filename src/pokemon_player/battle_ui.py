from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from PIL import Image


BattleActionCursor = Literal[
    "fight",
    "item",
    "pkmn",
    "run",
    "move_1",
    "move_2",
    "move_3",
    "move_4",
    "unknown",
]
BattleScreenKind = Literal[
    "action_menu",
    "dialogue",
    "item_menu",
    "move_menu",
    "party_menu",
    "unknown",
]


@dataclass(frozen=True)
class BattleUiState:
    kind: BattleScreenKind
    cursor: BattleActionCursor = "unknown"


def inspect_battle_ui_screenshot(path: str | Path) -> BattleUiState:
    image_path = Path(path)
    stat = image_path.stat()
    return _inspect_battle_ui_screenshot_cached(str(image_path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=128)
def _inspect_battle_ui_screenshot_cached(path: str, mtime_ns: int, size: int) -> BattleUiState:
    del mtime_ns, size
    image = Image.open(path).convert("L")
    if is_battle_party_menu(image):
        return BattleUiState(kind="party_menu")
    cursor = battle_action_cursor(image)
    if cursor != "unknown" and has_battle_action_menu_box(image):
        return BattleUiState(kind="action_menu", cursor=cursor)
    move_cursor = battle_move_cursor(image)
    if move_cursor != "unknown" and has_battle_move_menu_box(image):
        return BattleUiState(kind="move_menu", cursor=move_cursor)
    if is_battle_item_menu(image):
        return BattleUiState(kind="item_menu")
    if has_bottom_dialogue_text(image):
        return BattleUiState(kind="dialogue")
    return BattleUiState(kind="unknown")


def has_bottom_dialogue_text(image: Image.Image) -> bool:
    width, height = image.size
    if width < 120 or height < 120:
        return False
    text_area = image.crop((8, height - 32, min(132, width), height - 6))
    dialogue_box = image.crop((0, height - 40, width, height))
    left_text_area = image.crop((8, height - 32, min(70, width), height - 6))
    return dark_ratio(text_area) > 0.10 or (
        dark_ratio(dialogue_box) > 0.10 and dark_ratio(left_text_area) > 0.045
    )


def is_battle_item_menu(image: Image.Image) -> bool:
    width, height = image.size
    if width < 150 or height < 100:
        return False
    top_border = image.crop((50, 48, 156, 53))
    left_border = image.crop((48, 50, 53, 126))
    return dark_ratio(top_border) > 0.12 and dark_ratio(left_border) > 0.08


def is_battle_party_menu(image: Image.Image) -> bool:
    width, height = image.size
    if width < 150 or height < 130:
        return False
    party_list = image.crop((0, 0, 160, 96))
    party_rows_signature = image.crop((0, 0, 80, 48))
    right_menu = image.crop((104, 100, 160, 144))
    prompt_box = image.crop((0, 104, 64, 142))
    bottom_prompt = image.crop((0, 104, 160, 144))
    has_party_selection_prompt = (
        dark_ratio(party_rows_signature) > 0.19
        and dark_ratio(prompt_box) > 0.12
        and dark_ratio(bottom_prompt) > 0.12
    )
    party_list_ratio = dark_ratio(party_list)
    right_menu_ratio = dark_ratio(right_menu)
    if has_party_selection_prompt:
        return party_list_ratio > 0.08
    return party_list_ratio > 0.12 and right_menu_ratio > 0.17 and dark_ratio(prompt_box) > 0.12


def party_menu_cursor_slot(path: str | Path) -> int | None:
    image_path = Path(path)
    stat = image_path.stat()
    return _party_menu_cursor_slot_cached(str(image_path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=128)
def _party_menu_cursor_slot_cached(path: str, mtime_ns: int, size: int) -> int | None:
    del mtime_ns, size
    image = Image.open(path).convert("L")
    scores = {
        slot: dark_ratio(image.crop((0, y + 1, 8, y + 11)))
        for slot, y in enumerate((0, 16, 32, 48, 64, 80), start=1)
    }
    slot, score = max(scores.items(), key=lambda item: item[1])
    return slot if score > 0.04 else None


def forced_party_selection_prompt_visible(path: str | Path) -> bool:
    image_path = Path(path)
    stat = image_path.stat()
    return _forced_party_selection_prompt_visible_cached(
        str(image_path.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
    )


@lru_cache(maxsize=128)
def _forced_party_selection_prompt_visible_cached(path: str, mtime_ns: int, size: int) -> bool:
    del mtime_ns, size
    image = Image.open(path).convert("L")
    party_rows_signature = image.crop((0, 0, 80, 48))
    prompt_box = image.crop((0, 104, 64, 142))
    bottom_prompt = image.crop((0, 104, 160, 144))
    right_menu = image.crop((104, 100, 160, 144))
    return (
        dark_ratio(party_rows_signature) > 0.19
        and dark_ratio(prompt_box) > 0.12
        and dark_ratio(bottom_prompt) > 0.12
        and dark_ratio(right_menu) < 0.16
    )


def has_battle_action_menu_box(image: Image.Image) -> bool:
    width, height = image.size
    if width < 150 or height < 130:
        return False
    internal_divider = image.crop((104, 104, 110, 142))
    top_edge = image.crop((64, 104, 154, 110))
    command_box = image.crop((64, 104, 154, 142))
    return (
        dark_ratio(internal_divider) > 0.15
        and dark_ratio(top_edge) < 0.05
        and dark_ratio(command_box) > 0.14
    )


def has_battle_move_menu_box(image: Image.Image) -> bool:
    width, height = image.size
    if width < 150 or height < 130:
        return False
    move_top_edge = image.crop((0, 96, 96, 102))
    pp_top_edge = image.crop((96, 96, 160, 102))
    move_box = image.crop((0, 96, 98, 144))
    move_names_area = image.crop((48, 103, 86, 136))
    move_menu_divider = image.crop((32, 102, 38, 144))
    return (
        dark_ratio(move_top_edge) > 0.25
        and dark_ratio(pp_top_edge) > 0.20
        and dark_ratio(move_box) > 0.15
        and dark_ratio(move_names_area) > 0.10
        and dark_ratio(move_menu_divider) > 0.22
    )


def battle_action_cursor(image: Image.Image) -> BattleActionCursor:
    regions: dict[str, tuple[int, int, int, int]] = {
        "fight": (72, 113, 80, 120),
        "item": (72, 129, 80, 136),
        "pkmn": (116, 113, 124, 120),
        "run": (116, 129, 124, 136),
    }
    scores = {cursor: dark_ratio(image.crop(region)) for cursor, region in regions.items()}
    cursor, score = max(scores.items(), key=lambda item: item[1])
    return cursor if score > 0.20 else "unknown"


def battle_move_cursor(image: Image.Image) -> BattleActionCursor:
    regions: dict[str, tuple[int, int, int, int]] = {
        "move_1": (37, 103, 45, 111),
        "move_2": (37, 112, 45, 120),
        "move_3": (37, 121, 45, 129),
        "move_4": (37, 130, 45, 138),
    }
    scores = {cursor: dark_ratio(image.crop(region)) for cursor, region in regions.items()}
    cursor, score = max(scores.items(), key=lambda item: item[1])
    return cursor if score > 0.20 else "unknown"


def dark_ratio(image: Image.Image) -> float:
    histogram = image.histogram()
    dark_pixels = sum(histogram[:80])
    return dark_pixels / (image.width * image.height)
