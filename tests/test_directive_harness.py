from __future__ import annotations

import json
from pathlib import Path

import _path  # noqa: F401

from pokemon_player.config import load_dotenv, load_openai_config
from pokemon_player.directive_eval import (
    DirectiveEvalThresholds,
    compute_kpis,
    evaluate_directive_deck,
)
from pokemon_player.directive_model import (
    DirectiveCategory,
    DirectiveDecision,
    DirectiveRisk,
    DirectorContext,
    DirectorDecision,
)
from pokemon_player.directive_prompt import build_director_input
from pokemon_player.directive_rules import classify_directive_offline
from pokemon_player.director_client import OfflineDirectorClient


ROOT = Path(__file__).resolve().parents[1]


def test_director_decision_round_trip() -> None:
    decision = DirectorDecision(
        directive="Catch Pikachu",
        category=DirectiveCategory.STRATEGIC,
        risk=DirectiveRisk.LOW,
        decision=DirectiveDecision.ACCEPT,
        explanation="State has Poke Balls.",
        bounded_goal="catch_pikachu",
    )

    raw = json.loads(decision.to_json())
    restored = DirectorDecision.from_dict(raw, directive="Catch Pikachu")

    assert restored.category == DirectiveCategory.STRATEGIC
    assert restored.decision == DirectiveDecision.ACCEPT


def test_build_director_input_contains_state_objective_and_directive() -> None:
    text = build_director_input(
        DirectorContext(state_summary="Location: Viridian Forest", objective="Catch a Pokemon"),
        "Catch Pikachu",
    )

    assert "Location: Viridian Forest" in text
    assert "Catch a Pokemon" in text
    assert "Catch Pikachu" in text


def test_offline_director_rejects_destructive_directive() -> None:
    decision = classify_directive_offline(
        DirectorContext(state_summary="Party: PIKACHU", objective="Prepare for Misty"),
        "Release Pikachu",
    )

    assert decision.category == DirectiveCategory.DESTRUCTIVE
    assert decision.decision == DirectiveDecision.REJECT


def test_directive_deck_shape() -> None:
    deck = json.loads((ROOT / "research" / "directives" / "v0_directive_deck.json").read_text())

    assert deck["schema"] == "directive_deck_v1"
    assert len(deck["cases"]) >= 100
    for case in deck["cases"]:
        assert case["id"]
        assert case["state_summary"]
        assert case["objective"]
        assert case["directive"]
        assert case["expected"]["category"]
        assert case["expected"]["decision"]


def test_load_dotenv_does_not_override_existing_env(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_DIRECTOR_MODEL=from_file\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_DIRECTOR_MODEL", "from_env")

    load_dotenv(env_path)

    assert load_openai_config(env_path).director_model == "from_env"


def test_directive_eval_report_captures_verdicts_and_metrics() -> None:
    deck = json.loads((ROOT / "research" / "directives" / "v0_directive_deck.json").read_text())

    report = evaluate_directive_deck(
        deck=deck,
        client=OfflineDirectorClient(),
        mode="offline",
        deck_path=ROOT / "research" / "directives" / "v0_directive_deck.json",
        thresholds=DirectiveEvalThresholds(target_case_count=20),
    )

    assert report["schema"] == "directive_eval_report_v1"
    assert report["metrics"]["total_cases"] == len(deck["cases"])
    assert report["metrics"]["label_accuracy"] == 1.0
    assert report["metrics"]["accepted_destructive_count"] == 0
    assert report["kpis"]["overall_passed"] is True
    assert report["cases"][0]["actual"]["decision"]
    assert report["cases"][0]["matches"]["label"] is True


def test_directive_eval_kpi_flags_case_count_gap() -> None:
    metrics = {
        "total_cases": 20,
        "label_accuracy": 1.0,
        "accepted_destructive_count": 0,
        "accepted_compilation_rate": 1.0,
        "explanation_present_rate": 1.0,
    }

    kpis = compute_kpis(metrics, DirectiveEvalThresholds(target_case_count=100))

    assert kpis["case_count"]["passed"] is False
    assert kpis["overall_passed"] is False
