from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from pokemon_player.director_player import skill_availability
from pokemon_player.skills.handle_trainer_switch_prompt import (
    handle_trainer_switch_prompt,
    screenshot_has_trainer_switch_prompt,
)


def trainer_snapshot(*, options_raw: int = 3, active_slot: int = 1) -> dict:
    party = [
        {"slot": 1, "species_name": "Squirtle", "nickname": "SQUIRTLE", "hp": 41},
        {"slot": 2, "species_name": "Pikachu", "nickname": "PIKACHU", "hp": 29},
    ]
    return {
        "mode": "battle",
        "battle_type_raw": 2,
        "options_raw": options_raw,
        "enemy": {"species_name": "Onix", "hp": 36},
        "active_party_slot": active_slot,
        "active_party_member": party[active_slot - 1],
        "party": party,
        "warnings": [],
    }


def by_id(items: list[dict], identifier: str) -> dict:
    return next(item for item in items if item["id"] == identifier)


def draw_switch_prompt(path: Path) -> None:
    image = Image.new("L", (160, 144), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 48, 56, 96), outline=0, width=8)
    draw.text((12, 60), "YES", fill=0)
    draw.text((12, 76), "NO", fill=0)
    draw.rectangle((0, 96, 159, 143), outline=0, width=8)
    draw.text((10, 110), "CHANGE POKEMON?", fill=0)
    image.save(path)


def test_detects_shift_trainer_prompt_but_not_set_mode(tmp_path: Path) -> None:
    screenshot = tmp_path / "switch-prompt.png"
    draw_switch_prompt(screenshot)

    assert screenshot_has_trainer_switch_prompt(trainer_snapshot(), screenshot)
    assert not screenshot_has_trainer_switch_prompt(trainer_snapshot(options_raw=67), screenshot)


def test_switch_choice_requires_a_viable_target(tmp_path: Path) -> None:
    screenshot = tmp_path / "switch-prompt.png"
    draw_switch_prompt(screenshot)

    missing = handle_trainer_switch_prompt(
        trainer_snapshot(), choice="switch", screenshot_path=screenshot
    )
    viable = handle_trainer_switch_prompt(
        trainer_snapshot(), choice="switch", target=2, screenshot_path=screenshot
    )

    assert missing.status == "blocked"
    assert viable.status == "succeeded"


def test_director_exposes_only_semantic_trainer_prompt_response(tmp_path: Path) -> None:
    screenshot = tmp_path / "switch-prompt.png"
    draw_switch_prompt(screenshot)

    skills = skill_availability(trainer_snapshot(), screenshot)
    handler = by_id(skills, "handle_trainer_switch_prompt")

    assert handler["enabled"] is True
    assert handler["params"]["exampleArgs"] == {"choice": "keep"}
    assert handler["params"]["exampleSwitchArgs"] == {"choice": "switch", "target": 2}
    assert by_id(skills, "resolve_battle_outcome_dialogue_bundle")["enabled"] is False
    assert by_id(skills, "literal_button_press")["enabled"] is False
