from __future__ import annotations

from pokemon_player.run_interrogation import interrogate_run_report


def base_report() -> dict:
    return {
        "schema": "director_segment_run_v1",
        "finish": {
            "status": "checkpoint",
            "success": False,
            "summary": "Action budget checkpoint reached after 20 actions.",
            "failureCategory": None,
            "stopReason": "action_budget",
        },
        "history": [
            {
                "action": 1,
                "skillId": "navigate_within_pewter_region",
                "args": {"target": "pewter_route2_grass"},
                "result": {"status": "succeeded", "summary": "Reached grass."},
            },
            {
                "action": 2,
                "skillId": "enter_grass_search_loop",
                "args": {"patch": "current_map"},
                "result": {"status": "succeeded", "summary": "Wild battle started."},
            },
        ],
        "chapterTimeline": [
            {
                "action": 2,
                "chapterId": "chapter_7_level_for_brock",
                "success": False,
            }
        ],
        "finalState": "run/final.state",
        "finalScreenshot": "run/final.png",
        "finalSnapshot": {
            "mode": "battle",
            "battle_type_raw": 1,
            "position": {"map_id": 0x0D, "map_name": "Route 2", "x": 7, "y": 2},
            "party": [
                {"species_id": 0xB1, "species_name": "Squirtle", "hp": 14, "max_hp": 22}
            ],
        },
    }


def test_action_budget_checkpoint_is_healthy_continue() -> None:
    checkpoint = interrogate_run_report(base_report())

    assert checkpoint["verdict"] == "healthy_continue"
    assert checkpoint["continueRecommended"] is True
    assert "action_budget_is_checkpoint=true" in checkpoint["evidence"]


def test_legacy_action_budget_failure_category_is_still_checkpoint() -> None:
    report = base_report()
    report["schema"] = "local_gemma_chapter_run_v1"
    report["finish"] = {
        "status": "stopped",
        "success": False,
        "summary": "Action budget exhausted after 20 actions.",
        "failureCategory": "action_budget_exhausted",
    }

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "healthy_continue"
    assert checkpoint["continueRecommended"] is True


def test_operator_stop_is_a_safe_noncontinuing_checkpoint() -> None:
    report = base_report()
    report["finish"] = {
        "status": "checkpoint",
        "success": False,
        "summary": "Operator requested a stop after the completed action.",
        "failureCategory": None,
        "stopReason": "operator_stop_after_action",
    }

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "healthy_needs_review"
    assert checkpoint["continueRecommended"] is False
    assert "operator_stop=operator_stop_after_action" in checkpoint["evidence"]


def test_model_error_is_not_continue_recommended() -> None:
    report = base_report()
    report["finish"] = {
        "status": "stopped",
        "success": False,
        "summary": "Local LM Studio request failed.",
        "failureCategory": "local_llm_request_failed",
    }

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "model_error"
    assert checkpoint["continueRecommended"] is False
    assert checkpoint["fallbackTaken"] == ["retry_once_after_model_health_check_or_pivot"]


def test_execution_error_requires_state_reconciliation() -> None:
    report = base_report()
    report["finish"] = {
        "status": "failed",
        "success": False,
        "summary": "Semantic tool execution failed after invocation.",
        "failureCategory": "execution_error",
        "actionStarted": None,
        "actionStateKnown": False,
    }

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "unsafe_state"
    assert checkpoint["continueRecommended"] is False
    assert "action_state_known=false" in checkpoint["evidence"]
    assert checkpoint["fallbackTaken"] == [
        "reconcile_or_reload_pre_provider_checkpoint"
    ]


def test_no_conscious_party_is_unsafe() -> None:
    report = base_report()
    report["finalSnapshot"]["party"] = [
        {"species_id": 0xB1, "species_name": "Squirtle", "hp": 0, "max_hp": 22}
    ]

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "unsafe_state"
    assert checkpoint["continueRecommended"] is False
    assert any("no_conscious_party_members" in item for item in checkpoint["evidence"])


def test_literal_button_overuse_is_provisional_not_terminal() -> None:
    report = base_report()
    report["history"] = [
        {
            "action": index,
            "skillId": "literal_button_press",
            "result": {"status": "succeeded", "summary": "Pressed A once."},
        }
        for index in range(1, 5)
    ]

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "provisional_continue"
    assert checkpoint["continueRecommended"] is True
    assert checkpoint["reviewItems"][0]["kind"] == "literal_button_overuse"


def test_repeated_blocked_results_are_stalled_loop() -> None:
    report = base_report()
    report["history"] = [
        {
            "action": index,
            "skillId": "use_move",
            "result": {"status": "blocked", "summary": "use_move is not currently enabled."},
        }
        for index in range(1, 6)
    ]

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "stalled_loop"
    assert checkpoint["continueRecommended"] is False


def test_repeated_state_hash_without_progress_is_stalled_loop() -> None:
    report = base_report()
    report["history"] = [
        {
            "action": index,
            "skillId": "observe_checkpoint",
            "result": {"status": "succeeded", "summary": "Observed."},
        }
        for index in range(1, 6)
    ]
    report["progressObservations"] = [
        {
            "action": index,
            "stateHash": "unchanged",
            "chapterId": "chapter_7_level_for_brock",
            "position": {"map_id": 0x0D, "x": 7, "y": 2},
            "party": [{"species_id": 0xB1, "level": 8, "hp": 14}],
            "inventory": [],
            "money": 3000,
        }
        for index in range(1, 6)
    ]

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "stalled_loop"
    assert "loop_reason=repeated_state_hash_without_progress" in checkpoint["evidence"]


def test_repeated_interpretation_warning_is_a_state_gap() -> None:
    report = base_report()
    report["history"] = [
        {
            "action": index,
            "skillId": "advance_dialogue",
            "result": {
                "status": "blocked",
                "summary": "Unknown screen.",
                "warnings": ["unclassified_visual_state"],
            },
        }
        for index in range(1, 4)
    ]

    checkpoint = interrogate_run_report(report)

    assert checkpoint["verdict"] == "state_interpretation_gap"
    assert checkpoint["continueRecommended"] is False


def test_previous_checkpoint_deltas_are_recorded_as_progress() -> None:
    previous = base_report()
    report = base_report()
    report["finalSnapshot"]["position"]["x"] = 8
    report["finalSnapshot"]["party"][0]["hp"] = 16

    checkpoint = interrogate_run_report(report, previous_report=previous)

    assert "position_changes=1" in checkpoint["evidence"]
    assert "resource_changes=1" in checkpoint["evidence"]
