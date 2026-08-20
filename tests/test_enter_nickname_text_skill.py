from __future__ import annotations

from pathlib import Path

from pokemon_player.pyboy_lab import open_emulator
from pokemon_player.rom import fingerprint_rom
from pokemon_player.skill_execution import execute_enter_nickname_text, nickname_keyboard_trace
from pokemon_player.skills.enter_nickname_text import enter_nickname_text


ROOT = Path(__file__).resolve().parents[1]
MANUAL_INPUT = ROOT / "research" / "artifacts" / "director-player-runs" / "manual_input"


def test_nickname_keyboard_trace_matches_recent_abk_capture_path() -> None:
    pyboy = open_emulator(ROOT / "research" / "PokemonRed.gb", window="null")
    try:
        state_path = MANUAL_INPUT / "a-20260624T225434930907Z0000" / "before.state"
        with state_path.open("rb") as handle:
            pyboy.load_state(handle)
        pyboy.tick(1, False)

        trace = nickname_keyboard_trace(pyboy, "ABK")
    finally:
        pyboy.stop(False)

    buttons = [step.button for step in trace]
    assert buttons[:5] == ["a", "right", "a", "down", "a"]
    assert buttons[-1] == "a"
    assert buttons.count("a") == 4
    assert any(button in buttons for button in ("left", "right", "up", "down"))


def test_enter_nickname_text_available_on_naming_screen() -> None:
    screenshot = MANUAL_INPUT / "a-20260624T225434930907Z0000" / "before.png"

    result = enter_nickname_text({"mode": "battle", "battle_type_raw": 1}, screenshot_path=screenshot, nickname="ABK")

    assert result.status == "succeeded"


def test_enter_nickname_text_blocks_lowercase_or_symbols() -> None:
    screenshot = MANUAL_INPUT / "a-20260624T225434930907Z0000" / "before.png"

    result = enter_nickname_text({"mode": "battle", "battle_type_raw": 1}, screenshot_path=screenshot, nickname="ab-k")

    assert result.status == "blocked"


def test_enter_nickname_text_handles_z_before_hidden_space(tmp_path: Path) -> None:
    pyboy = open_emulator(ROOT / "research" / "PokemonRed.gb", window="null")
    try:
        artifact = execute_enter_nickname_text(
            pyboy,
            state_in=MANUAL_INPUT / "a-20260624T225434930907Z0000" / "before.state",
            rom=fingerprint_rom(ROOT / "research" / "PokemonRed.gb"),
            run_root=tmp_path,
            nickname="FUZZ",
        )
    finally:
        pyboy.stop(False)

    assert artifact.result.status == "succeeded"
