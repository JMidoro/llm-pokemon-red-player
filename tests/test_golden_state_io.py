import pytest

import _path  # noqa: F401

from pokemon_player.golden_state_io import sanitize_state_name


def test_sanitize_state_name() -> None:
    assert sanitize_state_name("Pallet Overworld Started!") == "pallet_overworld_started"


def test_sanitize_state_name_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        sanitize_state_name("!!!")
