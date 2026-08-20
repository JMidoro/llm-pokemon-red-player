from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_player.pyboy_lab import load_state, open_emulator, snapshot
from pokemon_player.rom import fingerprint_rom
from pokemon_player.snapshot_io import snapshot_hash
from pokemon_player.state_model import GameMode


ROOT = Path(__file__).resolve().parents[1]
ROM = ROOT / "research" / "PokemonRed.gb"
EXPECTED_FILES = sorted((ROOT / "research" / "golden-states").glob("*.expected.json"))


pytestmark = pytest.mark.skipif(not ROM.exists(), reason="local ROM is required")


def load_available_records() -> list[tuple[Path, dict]]:
    records: list[tuple[Path, dict]] = []
    for expected_path in EXPECTED_FILES:
        record = json.loads(expected_path.read_text(encoding="utf-8"))
        if Path(record["local_state_file"]).exists():
            records.append((expected_path, record))
    return records


@pytest.mark.skipif(not EXPECTED_FILES, reason="golden-state metadata is not available")
def test_all_golden_states_are_human_verified() -> None:
    for expected_path, record in load_available_records():
        assert record["human_verified"], expected_path.name


@pytest.mark.skipif(not EXPECTED_FILES, reason="golden-state metadata is not available")
def test_all_golden_states_reload_to_expected_snapshot_hash() -> None:
    rom = fingerprint_rom(ROM)
    for expected_path, record in load_available_records():
        assert record["rom"]["sha256"] == rom.sha256

        state_path = Path(record["local_state_file"])
        assert state_path.exists(), state_path

        pyboy = open_emulator(rom.path)
        try:
            load_state(pyboy, state_path)
            actual = snapshot(pyboy)
        finally:
            pyboy.stop(False)

        assert snapshot_hash(actual) == record["snapshot_hash"], expected_path.name


@pytest.mark.skipif(not EXPECTED_FILES, reason="golden-state metadata is not available")
def test_golden_states_cover_phase_1_modes_and_progression() -> None:
    records = [record for _, record in load_available_records()]
    names = {record["name"] for record in records}
    modes = {record["snapshot"]["mode"] for record in records}
    badge_values = {record["snapshot"]["badges"] for record in records}

    required_names = {
        "pallet_overworld_started",
        "pallet_journey_started_post_pokedex",
        "viridian_forest_grass",
        "viridian_forest_wild_battle_pikachu_weakened",
        "menu_open_bag_state",
        "dialogue_textbox_open",
        "cerulean_city_overworld",
        "cerulean_gym_overworld",
        "mid_misty_battle",
        "post_misty_badge",
    }
    assert required_names <= names
    assert {GameMode.OVERWORLD.value, GameMode.BATTLE.value, GameMode.MENU.value, GameMode.DIALOGUE.value} <= modes
    assert 0 in badge_values
    assert any(value and value & 0b00000001 for value in badge_values)
    assert any(value and value & 0b00000010 for value in badge_values)
