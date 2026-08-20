from __future__ import annotations

from pathlib import Path

import _path  # noqa: F401

from pokemon_player.golden_state_io import expected_record
from pokemon_player.rom import RomFingerprint
from pokemon_player.skill_state_io import sanitize_id, skill_state_record
from pokemon_player.state_model import GameMode, GameSnapshot, MapPosition


def snapshot() -> GameSnapshot:
    return GameSnapshot(
        mode=GameMode.OVERWORLD,
        position=MapPosition(map_id=0x33, x=3, y=41),
        party=(),
        inventory=(),
        money=0,
        badges=0,
    )


def rom() -> RomFingerprint:
    return RomFingerprint(
        path=Path("PokemonRed.gb"),
        title="POKEMON RED",
        size_bytes=1,
        md5="md5",
        sha256="sha256",
    )


def test_sanitize_id() -> None:
    assert sanitize_id("Detect Wild Battle!") == "detect_wild_battle"


def test_skill_state_record_includes_screenshot_and_expected_result() -> None:
    record = skill_state_record(
        skill_id="detect_wild_battle",
        capture_id="success_wild_battle",
        phase="single",
        expected_status="succeeded",
        expected_reason="wild_battle_detected",
        rom=rom(),
        state_file=Path("state.state"),
        screenshot_file=Path("state.png"),
        snapshot=snapshot(),
    )

    assert record["schema"] == "skill_state_capture_v1"
    assert record["screenshot_file"] == "state.png"
    assert record["expected_status"] == "succeeded"


def test_golden_expected_record_can_include_screenshot() -> None:
    record = expected_record(
        name="viridian_test",
        rom=rom(),
        state_file=Path("state.state"),
        screenshot_file=Path("state.png"),
        snapshot=snapshot(),
    )

    assert record["screenshot_file"] == "state.png"


def test_capture_records_serialize_checkout_paths_as_portable_identifiers() -> None:
    root = Path(__file__).resolve().parents[1]
    state_path = root / "research" / "skill-states" / "local" / "example.state"
    screenshot_path = state_path.with_suffix(".png")

    record = skill_state_record(
        skill_id="detect_wild_battle",
        capture_id="portable_example",
        phase="single",
        expected_status="succeeded",
        expected_reason="wild_battle_detected",
        rom=RomFingerprint(
            path=root / "research" / "PokemonRed.gb",
            title="POKEMON RED",
            size_bytes=1,
            md5="md5",
            sha256="sha256",
        ),
        state_file=state_path,
        screenshot_file=screenshot_path,
        snapshot=snapshot(),
    )

    assert record["rom"]["path"] == "research/PokemonRed.gb"
    assert record["local_state_file"] == "research/skill-states/local/example.state"
    assert record["screenshot_file"] == "research/skill-states/local/example.png"
