from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from pokemon_player.director_player import skill_availability
from pokemon_player.skills.handle_move_learning_prompt import (
    handle_move_learning_prompt,
    screenshot_has_move_learning_prompt,
)


def move_snapshot(*, moves: list[dict] | None = None) -> dict:
    member = {
        "slot": 1,
        "species_name": "Nidoran M",
        "nickname": "NIDORAN",
        "hp": 26,
        "moves": moves
        or [
            {"move_id": 43, "move_name": "Leer", "pp": 30},
            {"move_id": 33, "move_name": "Tackle", "pp": 32},
            {"move_id": 10, "move_name": "Scratch", "pp": 35},
            {"move_id": 45, "move_name": "Growl", "pp": 40},
        ],
    }
    return {
        "mode": "battle",
        "battle_type_raw": 1,
        "enemy": {"species_name": "Weedle", "hp": 0},
        "active_party_slot": 1,
        "active_party_member": member,
        "party": [member],
        "warnings": [],
    }


def draw_move_prompt(path: Path) -> None:
    image = Image.new("L", (160, 144), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 96, 159, 143), outline=0, width=8)
    draw.text((8, 112), "MAKE ROOM FOR MOVE?", fill=0)
    draw.line((114, 57, 118, 57), fill=0, width=1)
    draw.line((114, 58, 114, 98), fill=0, width=4)
    draw.line((156, 58, 156, 98), fill=0, width=4)
    draw.line((114, 98, 159, 98), fill=0, width=4)
    draw.text((122, 64), "YES", fill=0)
    draw.text((122, 80), "NO", fill=0)
    image.save(path)


def by_id(items: list[dict], identifier: str) -> dict:
    return next(item for item in items if item["id"] == identifier)


def test_detects_four_move_overwrite_prompt(tmp_path: Path) -> None:
    screenshot = tmp_path / "move-prompt.png"
    draw_move_prompt(screenshot)

    assert screenshot_has_move_learning_prompt(move_snapshot(), screenshot)
    three_moves = move_snapshot(moves=move_snapshot()["party"][0]["moves"][:3])
    assert not screenshot_has_move_learning_prompt(three_moves, screenshot)


def test_replace_choice_requires_current_move(tmp_path: Path) -> None:
    screenshot = tmp_path / "move-prompt.png"
    draw_move_prompt(screenshot)

    missing = handle_move_learning_prompt(move_snapshot(), choice="replace", screenshot_path=screenshot)
    viable = handle_move_learning_prompt(
        move_snapshot(), choice="replace", forget_move="Growl", screenshot_path=screenshot
    )

    assert missing.status == "blocked"
    assert viable.status == "succeeded"


def test_move_learning_result_verifies_replaced_move() -> None:
    before = move_snapshot()
    after = move_snapshot(
        moves=[
            {"move_id": 43, "move_name": "Leer", "pp": 30},
            {"move_id": 33, "move_name": "Tackle", "pp": 32},
            {"move_id": 10, "move_name": "Scratch", "pp": 35},
            {"move_id": 30, "move_name": "Horn Attack", "pp": 25},
        ]
    )

    result = handle_move_learning_prompt(
        after,
        before_snapshot=before,
        choice="replace",
        forget_move="Growl",
    )

    assert result.status == "succeeded"
    assert "Horn Attack" in result.summary


def test_director_exposes_semantic_move_learning_choice(tmp_path: Path) -> None:
    screenshot = tmp_path / "move-prompt.png"
    draw_move_prompt(screenshot)

    skills = skill_availability(move_snapshot(), screenshot)
    handler = by_id(skills, "handle_move_learning_prompt")

    assert handler["enabled"] is True
    assert handler["params"]["exampleArgs"] == {"choice": "skip"}
    assert handler["params"]["exampleReplaceArgs"] == {"choice": "replace", "forgetMove": "Leer"}
    assert by_id(skills, "resolve_battle_outcome_dialogue_bundle")["enabled"] is False
    assert by_id(skills, "literal_button_press")["enabled"] is False
