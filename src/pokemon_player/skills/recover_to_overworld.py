from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

from pokemon_player.battle_ui import dark_ratio, has_bottom_dialogue_text
from pokemon_player.skill_result import SkillResult


SKILL_ID = "recover_to_overworld"
RECOVERABLE_MODES = {"menu", "dialogue", "menu_or_dialogue_uncertain"}


def recover_to_overworld(
    snapshot: Mapping[str, Any],
    *,
    before_snapshot: Mapping[str, Any] | None = None,
    screenshot_path: str | Path | None = None,
) -> SkillResult:
    mode = str(snapshot.get("mode", "unknown"))
    battle_type_raw = snapshot.get("battle_type_raw")
    warnings = tuple(str(item) for item in snapshot.get("warnings", ()))
    position = snapshot.get("position")
    map_name = position.get("map_name") if isinstance(position, Mapping) else "unknown"
    evidence = [
        f"mode={mode}",
        f"battle_type_raw={battle_type_raw}",
        f"map_name={map_name}",
    ]

    if before_snapshot is not None:
        before_mode = str(before_snapshot.get("mode", "unknown"))
        before_battle_type = before_snapshot.get("battle_type_raw")
        evidence.extend(
            [
                f"before_mode={before_mode}",
                f"before_battle_type_raw={before_battle_type}",
            ]
        )
        if before_mode in RECOVERABLE_MODES and mode == "overworld" and battle_type_raw == 0:
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Recovered from menu/dialogue drift to overworld.",
                evidence=tuple(evidence),
                warnings=warnings,
            )

    if battle_type_raw not in {None, 0} or mode == "battle":
        return SkillResult(
            skill_id=SKILL_ID,
            status="blocked",
            summary="Battle is active; route through a battle-specific skill instead.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    if mode == "overworld":
        if screenshot_path and screenshot_has_overworld_ui_overlay(screenshot_path):
            evidence.append("screenshot=overworld_ui_overlay")
            return SkillResult(
                skill_id=SKILL_ID,
                status="succeeded",
                summary="Overworld-like state has visible UI drift that recovery can clear.",
                evidence=tuple(evidence),
                warnings=warnings,
            )
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Already in overworld; recovery is a no-op success.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    if mode in RECOVERABLE_MODES:
        if screenshot_path and screenshot_has_overworld_ui_overlay(screenshot_path):
            evidence.append("screenshot=overworld_ui_overlay")
        return SkillResult(
            skill_id=SKILL_ID,
            status="succeeded",
            summary="Menu/dialogue state is recoverable to overworld with bounded cancel/advance inputs.",
            evidence=tuple(evidence),
            warnings=warnings,
        )

    return SkillResult(
        skill_id=SKILL_ID,
        status="uncertain",
        summary="State is not clearly overworld, recoverable UI drift, or battle.",
        evidence=tuple(evidence),
        warnings=warnings,
    )


def screenshot_has_overworld_ui_overlay(path: str | Path) -> bool:
    image = _load_recovery_screenshot(path)
    if image is None:
        return False

    return has_bottom_dialogue_text(image) or _has_upper_menu_overlay(image)


def screenshot_has_dialogue_overlay(path: str | Path) -> bool:
    image = _load_recovery_screenshot(path)
    return bool(image is not None and has_bottom_dialogue_text(image))


def _load_recovery_screenshot(path: str | Path) -> Image.Image | None:
    image_path = Path(path)
    if not image_path.exists():
        return None

    stat = image_path.stat()
    return _load_recovery_screenshot_cached(str(image_path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=128)
def _load_recovery_screenshot_cached(path: str, mtime_ns: int, size: int) -> Image.Image | None:
    del mtime_ns, size
    image = Image.open(path).convert("L")
    width, height = image.size
    if width < 120 or height < 120:
        return None

    return image


def _has_upper_menu_overlay(image: Image.Image) -> bool:
    width, height = image.size
    top_right = image.crop((max(0, width - 72), 0, width, min(80, height)))
    top_left = image.crop((0, 0, min(88, width), min(80, height)))
    return dark_ratio(top_right) > 0.12 or dark_ratio(top_left) > 0.16
