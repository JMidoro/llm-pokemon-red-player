from __future__ import annotations

from pathlib import Path

from pokemon_player import skill_execution
from pokemon_player.battle_ui import BattleUiState
from pokemon_player.skills.visual_state import UiVisualState


class FakePyBoy:
    def __init__(self) -> None:
        self.ticks: list[tuple[int, bool]] = []

    def tick(self, frames: int, render: bool) -> None:
        self.ticks.append((frames, render))


def test_unknown_settle_polls_do_not_consume_battle_dialogue_input_budget(
    monkeypatch,
    tmp_path: Path,
) -> None:
    pyboy = FakePyBoy()
    trace = []
    ui_states = iter(
        [
            BattleUiState(kind="unknown"),
            BattleUiState(kind="unknown"),
            BattleUiState(kind="unknown"),
            BattleUiState(kind="unknown"),
            BattleUiState(kind="dialogue"),
        ]
    )
    monkeypatch.setattr(skill_execution, "snapshot", lambda _pyboy: object())
    monkeypatch.setattr(
        skill_execution,
        "snapshot_to_dict",
        lambda _snapshot: {"mode": "battle", "battle_type_raw": 2},
    )
    monkeypatch.setattr(skill_execution, "save_screenshot", lambda *_args: None)
    monkeypatch.setattr(
        skill_execution,
        "inspect_battle_ui_screenshot",
        lambda _path: next(ui_states),
    )
    monkeypatch.setattr(skill_execution, "run_timed_trace", lambda *_args, **_kwargs: None)

    skill_execution.run_advance_battle_dialogue_inputs(
        pyboy,
        trace=trace,
        screenshot_path=tmp_path / "battle.png",
        render=False,
        max_inputs=1,
    )

    assert pyboy.ticks.count((60, False)) == 4
    assert pyboy.ticks.count((1, True)) == 5
    assert [step.button for step in trace] == ["a"]


def test_battle_dialogue_bundle_stops_before_compact_choice(
    monkeypatch,
    tmp_path: Path,
) -> None:
    pyboy = FakePyBoy()
    trace = []
    monkeypatch.setattr(skill_execution, "snapshot", lambda _pyboy: object())
    monkeypatch.setattr(
        skill_execution,
        "snapshot_to_dict",
        lambda _snapshot: {"mode": "battle", "battle_type_raw": 2},
    )
    monkeypatch.setattr(skill_execution, "save_screenshot", lambda *_args: None)
    monkeypatch.setattr(
        skill_execution,
        "inspect_battle_ui_screenshot",
        lambda _path: BattleUiState(kind="dialogue"),
    )
    monkeypatch.setattr(
        skill_execution,
        "inspect_ui_visual_state",
        lambda _path: UiVisualState(
            bottom_text_box=True,
            upper_menu=True,
            compact_choice=True,
        ),
    )

    skill_execution.run_advance_battle_dialogue_inputs(
        pyboy,
        trace=trace,
        screenshot_path=tmp_path / "battle.png",
        render=False,
        max_inputs=32,
    )

    assert trace == []
