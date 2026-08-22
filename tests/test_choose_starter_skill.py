from __future__ import annotations

from pokemon_player.skills.choose_starter import choose_starter


def snapshot(*, x: int, y: int, mode: str = "overworld") -> dict[str, object]:
    return {
        "mode": mode,
        "battle_type_raw": 0,
        "position": {"map_id": 0x28, "x": x, "y": y},
        "party": [],
        "warnings": [],
    }


def completed_snapshot(*, got_starter: bool) -> dict[str, object]:
    value = snapshot(x=7, y=4)
    value["party"] = [{"species_name": "Squirtle"}]
    value["story_events"] = {"got_starter": got_starter}
    return value


def test_choose_starter_is_enabled_only_at_stable_starter_table_handoff() -> None:
    result = choose_starter(snapshot(x=5, y=3), starter="squirtle")

    assert result.status == "succeeded"
    assert "starter-table handoff" in result.summary


def test_choose_starter_blocks_oak_escort_dialogue_at_lab_entrance() -> None:
    result = choose_starter(snapshot(x=5, y=11, mode="dialogue"), starter="squirtle")

    assert result.status == "blocked"
    assert "x=5, y=3" in result.summary


def test_choose_starter_blocks_stable_overworld_away_from_handoff() -> None:
    result = choose_starter(snapshot(x=5, y=5), starter="squirtle")

    assert result.status == "blocked"
    assert "required_position=map=0x28,x=5,y=3" in result.evidence


def test_choose_starter_does_not_succeed_before_oaks_scripted_handoff_finishes() -> None:
    result = choose_starter(
        completed_snapshot(got_starter=False),
        before_snapshot=snapshot(x=5, y=3),
        starter="squirtle",
    )

    assert result.status == "uncertain"
    assert "still active" in result.summary


def test_choose_starter_succeeds_after_oaks_scripted_handoff_finishes() -> None:
    result = choose_starter(
        completed_snapshot(got_starter=True),
        before_snapshot=snapshot(x=5, y=3),
        starter="squirtle",
    )

    assert result.status == "succeeded"
    assert "handoff completed" in result.summary
