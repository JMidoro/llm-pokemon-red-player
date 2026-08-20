from pathlib import Path

import pytest

import _path  # noqa: F401

from pokemon_player.trace import button_input_from_dict, load_trace


def test_button_input_from_dict_validates_button() -> None:
    step = button_input_from_dict({"button": "A", "hold_frames": 2, "settle_frames": 0})

    assert step.button == "a"
    assert step.hold_frames == 2
    assert step.settle_frames == 0


def test_button_input_rejects_unknown_button() -> None:
    with pytest.raises(ValueError, match="Unsupported button"):
        button_input_from_dict({"button": "jump"})


def test_load_trace_requires_list(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text('{"button": "a"}', encoding="utf-8")

    with pytest.raises(ValueError, match="JSON list"):
        load_trace(trace_path)
