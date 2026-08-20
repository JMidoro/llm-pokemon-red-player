from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_player.pyboy_lab import load_state, open_emulator, save_state, snapshot


ROM = Path("research/PokemonRed.gb")


pytestmark = pytest.mark.skipif(not ROM.exists(), reason="local ROM is required")


def test_pyboy_can_snapshot_save_and_reload(tmp_path: Path) -> None:
    pyboy = open_emulator(ROM)
    state_path = tmp_path / "boot.state"
    try:
        pyboy.tick(60, False)
        before = snapshot(pyboy)
        save_state(pyboy, state_path)
        pyboy.tick(10, False)
        load_state(pyboy, state_path)
        after = snapshot(pyboy)
    finally:
        pyboy.stop()

    assert before == after
    assert before.position is not None
