from pathlib import Path

import _path  # noqa: F401

from pokemon_player.generated_state_io import default_report_path, find_report_for_state


def test_default_report_path() -> None:
    assert default_report_path("foo.state") == Path("foo.state.report.json")


def test_find_report_for_state(tmp_path: Path) -> None:
    state_path = tmp_path / "variant.state"
    state_path.write_bytes(b"not a real state")
    report_path = default_report_path(state_path)
    report_path.write_text(
        '{"schema":"generated_state_report_v1","goal":"test goal","approval":{"status":"approved"}}',
        encoding="utf-8",
    )

    report = find_report_for_state(state_path)

    assert report is not None
    assert report.goal == "test goal"
    assert report.approval_status == "approved"
