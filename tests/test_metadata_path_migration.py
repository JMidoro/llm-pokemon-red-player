from __future__ import annotations

import copy

from scripts.migrate_metadata_paths import migrate_record
from scripts.validate_repository import ROOT, validate_metadata


def test_migrate_capture_metadata_paths_is_idempotent() -> None:
    record = {
        "schema": "golden_state_expected_v1",
        "local_state_file": "Z:/retired/research/golden-states/local/example.state",
        "screenshot_file": "Z:/retired/research/golden-states/local/example.png",
        "rom": {"path": "Z:/retired/research/PokemonRed.gb"},
    }

    assert migrate_record(record) is True
    assert record == {
        "schema": "golden_state_expected_v1",
        "local_state_file": "research/golden-states/local/example.state",
        "screenshot_file": "research/golden-states/local/example.png",
        "rom": {"path": "research/PokemonRed.gb"},
    }
    assert migrate_record(record) is False


def test_migrate_skill_catalog_nested_recommended_states() -> None:
    record = {
        "schema": "skill_catalog_v1",
        "skills": [
            {
                "recommended_start_states": [
                    {
                        "state_path": (
                            "Z:/retired/research/skill-states/local/example.state"
                        ),
                        "screenshot_path": (
                            "Z:/retired/research/skill-states/local/example.png"
                        ),
                    }
                ]
            }
        ],
    }

    assert migrate_record(record) is True
    recommended = record["skills"][0]["recommended_start_states"][0]
    assert recommended["state_path"] == "research/skill-states/local/example.state"
    assert recommended["screenshot_path"] == "research/skill-states/local/example.png"


def test_repository_validator_rejects_absolute_durable_metadata_path() -> None:
    record = {
        "schema": "golden_state_expected_v1",
        "local_state_file": "Z:/checkout/research/golden-states/local/example.state",
        "screenshot_file": None,
        "rom": {"path": "research/PokemonRed.gb"},
    }

    issues = validate_metadata(ROOT / "research" / "example.json", copy.deepcopy(record))

    assert any("repository-relative" in issue for issue in issues)
