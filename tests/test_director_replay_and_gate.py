from __future__ import annotations

import json
from pathlib import Path

from pokemon_player.director_contracts import DirectorRequest
from pokemon_player.director_prompting import prepare_director_request
from pokemon_player.director_providers import ReplayAdapter
from pokemon_player.director_runtime import DirectorRuntime
from scripts.evaluate_director_provider_gate import (
    canonical_json_hash,
    request_from_scenario,
    semantic_registry_hash,
)
from scripts.run_chapter_segment import build_parser
from scripts.verify_director_provider_gate import verify_gate_pair


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "research" / "evals" / "provider-neutral-director"


def load_object(path: Path) -> dict[str, object]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def test_replay_adapter_is_deterministic_for_frozen_scenario() -> None:
    scenario = load_object(EVAL_ROOT / "frozen_scenario.json")
    replay = load_object(EVAL_ROOT / "replay_decisions.json")
    request = request_from_scenario(
        scenario,
        provider="replay",
        model="deterministic-replay",
        reasoning_effort="low",
    )

    decisions = replay["decisions"]
    first = DirectorRuntime(ReplayAdapter(list(decisions))).decide(request)
    second = DirectorRuntime(ReplayAdapter(list(decisions))).decide(request)

    assert first.tool_call == second.tool_call
    assert first.assistant_message == second.assistant_message
    assert first.tool_call is not None
    assert first.tool_call.arguments["skillId"] in request.enabled_skill_ids()


def test_frozen_scenario_registry_hash_is_provider_independent() -> None:
    scenario = load_object(EVAL_ROOT / "frozen_scenario.json")
    local = request_from_scenario(
        scenario,
        provider="lmstudio-chat",
        model="google/gemma-4-e4b",
        reasoning_effort="low",
    )
    hosted = request_from_scenario(
        scenario,
        provider="openai-responses",
        model="hosted-comparison",
        reasoning_effort="low",
    )

    assert isinstance(local, DirectorRequest)
    assert local.goal == hosted.goal
    assert local.context == hosted.context
    assert local.enabled_skills == hosted.enabled_skills
    assert semantic_registry_hash(
        {"enabledSkills": list(local.enabled_skills)}
    ) == semantic_registry_hash({"enabledSkills": list(hosted.enabled_skills)})
    assert canonical_json_hash(scenario) == canonical_json_hash(load_object(EVAL_ROOT / "frozen_scenario.json"))

    local_prepared = prepare_director_request(local, ReplayAdapter([]).capabilities)
    hosted_prepared = prepare_director_request(hosted, ReplayAdapter([]).capabilities)
    assert local_prepared.instructions == hosted_prepared.instructions
    assert local_prepared.messages == hosted_prepared.messages
    assert local_prepared.tools == hosted_prepared.tools


def test_local_gemma_wrapper_parser_is_pinned_to_lmstudio() -> None:
    parser = build_parser(forced_provider="lmstudio-chat")

    assert parser.parse_args([]).provider == "lmstudio-chat"
    assert "--provider" not in parser.format_help()


def gate_report(provider: str) -> dict[str, object]:
    return {
        "schema": "director_segment_run_v1",
        "status": "stopped",
        "provider": {"provider": provider},
        "finish": {"actionStarted": False},
        "requests": [
            {
                "enabledSkills": [
                    "navigate_within_viridian_forest_region",
                    "recover_to_overworld",
                ]
            }
        ],
        "ticks": [
            {
                "decision": {
                    "error": None,
                    "toolCall": {
                        "name": "execute_skill",
                        "arguments": {
                            "skillId": "navigate_within_viridian_forest_region",
                            "args": {"target": "forest_grass"},
                        },
                    },
                }
            }
        ],
        "context": {
            "scenarioId": "frozen-v1",
            "scenarioSha256": "scenario-hash",
            "semanticRegistrySha256": "registry-hash",
            "emulatorExecutionEnabled": False,
        },
    }


def test_provider_gate_verifier_accepts_matching_successful_reports() -> None:
    assert verify_gate_pair(
        gate_report("lmstudio-chat"), gate_report("openai-responses")
    ) == []


def test_provider_gate_verifier_rejects_changed_scenario_or_credentials() -> None:
    local = gate_report("lmstudio-chat")
    hosted = gate_report("openai-responses")
    hosted["context"]["scenarioSha256"] = "changed"
    hosted["authorization"] = "Bearer unit-test-credential"

    issues = verify_gate_pair(local, hosted)

    assert "local and hosted scenarioSha256 values differ" in issues
    assert any("credential-like field" in issue for issue in issues)


def test_provider_gate_verifier_does_not_accept_replay_as_hosted_evidence() -> None:
    issues = verify_gate_pair(gate_report("lmstudio-chat"), gate_report("replay"))

    assert "hosted report was not produced by openai-responses" in issues


def test_provider_gate_verifier_rejects_different_semantic_decisions() -> None:
    local = gate_report("lmstudio-chat")
    hosted = gate_report("openai-responses")
    hosted["ticks"][0]["decision"]["toolCall"]["arguments"]["args"] = {
        "target": "viridian_pokecenter"
    }

    issues = verify_gate_pair(local, hosted)

    assert "local and hosted normalized semantic decisions differ" in issues


def test_provider_neutral_runner_and_local_wrapper_keep_provider_logic_out() -> None:
    runner = (ROOT / "scripts" / "run_chapter_segment.py").read_text(encoding="utf-8")
    support = (ROOT / "scripts" / "chapter_segment_support.py").read_text(
        encoding="utf-8"
    )
    wrapper = (ROOT / "scripts" / "run_local_gemma_chapter.py").read_text(
        encoding="utf-8"
    )

    assert "make_provider" in runner
    assert "chat/completions" not in runner + support + wrapper
    assert "OPENAI_API_KEY" not in runner + support + wrapper
    assert "LM_API_TOKEN" not in runner + support + wrapper
    assert 'forced_provider="lmstudio-chat"' in wrapper
    assert len(wrapper.splitlines()) < 50
