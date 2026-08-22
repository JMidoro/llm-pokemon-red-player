from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from pokemon_player.skills.talk_to_npc import (
    default_interaction_target,
    interaction_buttons,
    interaction_options,
    talk_to_npc,
)
from pokemon_player.skills.visual_state import UiVisualState


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "research" / "golden-states"


def load_snapshot(name: str) -> dict:
    record = json.loads((GOLDEN / f"{name}.expected.json").read_text(encoding="utf-8"))
    return record["snapshot"]


def test_brock_interaction_is_semantic_and_position_scoped() -> None:
    snapshot = load_snapshot("pewter_gym_brock_pre_battle")

    result = talk_to_npc(snapshot, target="brock")

    assert result.status == "succeeded"
    assert "buttons_hidden_by_semantic_skill=true" in result.evidence
    assert default_interaction_target(snapshot) == "brock"
    assert interaction_options(snapshot) == [{"id": "brock", "label": "Brock"}]
    assert interaction_buttons("brock") == ("left", "a")


def test_npc_interaction_blocks_wrong_position_or_active_battle() -> None:
    wrong_position = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x36, "x": 4, "y": 1},
    }
    battle = {
        "mode": "battle",
        "battle_type_raw": 2,
        "position": {"map_id": 0x36, "x": 5, "y": 1},
    }

    assert talk_to_npc(wrong_position, target="brock").status == "blocked"
    assert talk_to_npc(battle, target="brock").status == "blocked"
    assert interaction_options(battle) == []


def test_npc_interaction_blocks_when_dialogue_is_already_visible() -> None:
    snapshot = load_snapshot("pewter_gym_brock_pre_battle")
    with patch(
        "pokemon_player.skills.talk_to_npc.inspect_ui_visual_state",
        return_value=UiVisualState(bottom_text_box=True, upper_menu=False),
    ):
        result = talk_to_npc(snapshot, target="brock", screenshot_path="dialogue.png")

    assert result.status == "blocked"
    assert "already active" in result.summary


def test_npc_interaction_critic_requires_dialogue_battle_or_story_change() -> None:
    before = load_snapshot("pewter_gym_brock_pre_battle")
    unchanged = dict(before)
    battle = dict(before)
    battle["mode"] = "battle"
    battle["battle_type_raw"] = 2

    failed = talk_to_npc(unchanged, target="brock", before_snapshot=before)
    succeeded = talk_to_npc(battle, target="brock", before_snapshot=before)

    assert failed.status == "failed"
    assert succeeded.status == "succeeded"


def test_story_interaction_targets_cover_mart_and_oak_checkpoints() -> None:
    mart = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x2A, "x": 2, "y": 5},
    }
    oak = {
        "mode": "overworld",
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": 5, "y": 3},
    }

    assert default_interaction_target(mart) == "viridian_mart_clerk"
    assert interaction_buttons("viridian_mart_clerk") == ("left", "a")
    assert default_interaction_target(oak) == "professor_oak"
    assert interaction_buttons("oak") == ("up", "a")
