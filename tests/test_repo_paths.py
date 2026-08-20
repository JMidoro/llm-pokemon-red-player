from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_player.repo_paths import find_repo_root, portable_repo_path, resolve_repo_path


ROOT = Path(__file__).resolve().parents[1]


def test_find_repo_root_is_independent_of_working_directory() -> None:
    assert find_repo_root(ROOT / "apps" / "lab-ui") == ROOT


def test_portable_repo_path_serializes_current_checkout_path() -> None:
    value = ROOT / "research" / "golden-states" / "local" / "example.state"

    assert portable_repo_path(value, repo_root=ROOT) == (
        "research/golden-states/local/example.state"
    )


def test_resolve_repo_path_maps_legacy_windows_checkout_suffix(tmp_path: Path) -> None:
    expected = tmp_path / "research" / "golden-states" / "local" / "example.state"
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"state")
    legacy = "Z:\\retired-checkout\\research\\golden-states\\local\\example.state"

    assert resolve_repo_path(legacy, repo_root=tmp_path) == expected


def test_portable_repo_path_migrates_legacy_windows_checkout_suffix(tmp_path: Path) -> None:
    legacy = "Z:\\retired-checkout\\research\\PokemonRed.gb"

    assert portable_repo_path(legacy, repo_root=tmp_path) == "research/PokemonRed.gb"


def test_resolve_repo_path_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        resolve_repo_path("", repo_root=ROOT)


def test_portable_repo_path_rejects_parent_traversal() -> None:
    with pytest.raises(ValueError, match="cannot escape"):
        portable_repo_path("../outside.state", repo_root=ROOT)
