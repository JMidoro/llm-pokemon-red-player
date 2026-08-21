from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from pokemon_player.director_contracts import (
    DirectorError,
    DirectorRequest,
    ProviderCapabilities,
    ProviderResponse,
    ProviderUsage,
    ToolCall,
)
from pokemon_player.director_reporting import REPORT_SCHEMA, build_director_report
from pokemon_player.director_runtime import DirectorRuntime
from pokemon_player.director_prompting import prepare_director_request


@dataclass
class SequenceProvider:
    responses: list[ProviderResponse | DirectorError]
    provider_id: str = "test-provider"
    capabilities: ProviderCapabilities = field(
        default_factory=lambda: ProviderCapabilities(
            images=True,
            structured_tools=True,
            reasoning_controls=True,
            streaming=False,
            usage_accounting=True,
        )
    )
    calls: int = 0
    prepared_requests: list[Any] = field(default_factory=list)

    def complete(self, request: Any) -> ProviderResponse:
        from pokemon_player.director_providers import ProviderFailure

        self.prepared_requests.append(request)
        item = self.responses[self.calls]
        self.calls += 1
        if isinstance(item, DirectorError):
            raise ProviderFailure(item)
        return item

    def public_config(self) -> dict[str, object]:
        return {
            "provider": self.provider_id,
            "apiFamily": "test",
            "capabilities": self.capabilities.to_dict(),
        }


def canonical_request() -> DirectorRequest:
    return DirectorRequest(
        goal="Reach the forest grass.",
        model="model-a",
        provider="test-provider",
        enabled_skills=(
            {
                "id": "navigate_within_viridian_forest_region",
                "label": "Navigate",
                "params": {"targets": ["forest_grass"]},
            },
        ),
        context={"snapshot": {"mode": "overworld"}},
        metadata={
            "checkpoint": {
                "statePath": "before.state",
                "snapshotHash": "abc123",
                "actionStarted": False,
            }
        },
    )


def successful_response() -> ProviderResponse:
    return ProviderResponse(
        tool_calls=(
            ToolCall(
                name="execute_skill",
                arguments={
                    "skillId": "navigate_within_viridian_forest_region",
                    "args": {"target": "forest_grass"},
                    "plaintextReasoning": "This directly serves the chapter objective.",
                },
            ),
        ),
        usage=ProviderUsage(input_tokens=100, output_tokens=20, total_tokens=120),
    )


def test_provider_failure_never_calls_executor_and_preserves_checkpoint() -> None:
    provider = SequenceProvider(
        [
            DirectorError(
                category="provider_unavailable",
                message="offline",
                retryable=False,
                provider="test-provider",
            )
        ]
    )
    executor_calls: list[ToolCall] = []
    request = canonical_request()

    tick = DirectorRuntime(provider).run_tick(
        request,
        executor=lambda call: executor_calls.append(call) or {"actionStarted": True},
    )

    assert tick.decision.error is not None
    assert tick.decision.error.category == "provider_unavailable"
    assert tick.execution is None
    assert executor_calls == []
    assert request.summary()["checkpoint"] == {
        "statePath": "before.state",
        "snapshotHash": "abc123",
        "actionStarted": False,
    }


def test_request_provider_must_match_selected_adapter_before_call_or_execution() -> None:
    provider = SequenceProvider([successful_response()], provider_id="hosted-test")
    executor_calls: list[ToolCall] = []

    tick = DirectorRuntime(provider).run_tick(
        canonical_request(),
        executor=lambda call: executor_calls.append(call) or {"actionStarted": True},
    )

    assert tick.decision.error is not None
    assert tick.decision.error.category == "invalid_request"
    assert tick.decision.attempts == 0
    assert provider.calls == 0
    assert executor_calls == []


def test_retry_happens_before_exactly_one_execution() -> None:
    provider = SequenceProvider(
        [
            DirectorError(
                category="timeout",
                message="temporary timeout",
                retryable=True,
                provider="test-provider",
            ),
            successful_response(),
        ]
    )
    executor_calls: list[ToolCall] = []

    tick = DirectorRuntime(provider, max_retries=1, retry_backoff_seconds=0).run_tick(
        canonical_request(),
        executor=lambda call: executor_calls.append(call)
        or {"actionStarted": True, "status": "succeeded"},
    )

    assert tick.decision.error is None
    assert tick.decision.attempts == 2
    assert provider.calls == 2
    assert len(executor_calls) == 1


def test_single_enabled_skill_is_inferred_when_tool_call_omits_skill_id() -> None:
    provider = SequenceProvider(
        [
            ProviderResponse(
                tool_calls=(
                    ToolCall(
                        name="execute_skill",
                        arguments={
                            "args": {"target": "forest_grass"},
                            "plaintextReasoning": "Move toward the only enabled objective.",
                        },
                    ),
                )
            )
        ]
    )

    decision = DirectorRuntime(provider).decide(canonical_request())

    assert decision.error is None
    assert decision.tool_call is not None
    assert decision.tool_call.arguments["skillId"] == "navigate_within_viridian_forest_region"


def test_move_arguments_infer_use_move_among_multiple_tactical_skills() -> None:
    request = replace(
        canonical_request(),
        enabled_skills=(
            {"id": "use_move", "label": "Use Move", "params": {}},
            {"id": "switch_party_member", "label": "Switch", "params": {}},
        ),
    )
    provider = SequenceProvider(
        [
            ProviderResponse(
                tool_calls=(
                    ToolCall(
                        name="execute_skill",
                        arguments={
                            "move": "Bubble",
                            "plaintextReasoning": "Bubble is super effective here.",
                        },
                    ),
                )
            )
        ]
    )

    decision = DirectorRuntime(provider).decide(request)

    assert decision.error is None
    assert decision.tool_call is not None
    assert decision.tool_call.arguments == {
        "skillId": "use_move",
        "args": {"move": "Bubble"},
        "plaintextReasoning": "Bubble is super effective here.",
    }
    assert request.summary()["seed"] is None


def test_nested_sole_skill_id_is_unwrapped_without_leaking_into_args() -> None:
    request = replace(
        canonical_request(),
        enabled_skills=(
            {"id": "switch_party_member", "label": "Switch", "params": {}},
        ),
    )
    provider = SequenceProvider(
        [
            ProviderResponse(
                tool_calls=(
                    ToolCall(
                        name="execute_skill",
                        arguments={"args": {"skillId": "switch_party_member"}},
                    ),
                )
            )
        ]
    )

    decision = DirectorRuntime(provider).decide(request)

    assert decision.error is None
    assert decision.tool_call is not None
    assert decision.tool_call.arguments["skillId"] == "switch_party_member"
    assert decision.tool_call.arguments["args"] == {}


def test_repeated_attack_normalizes_to_sole_agency_neutral_outcome_bundle() -> None:
    request = replace(
        canonical_request(),
        enabled_skills=(
            {
                "id": "resolve_battle_outcome_dialogue_bundle",
                "label": "Resolve Outcome",
                "params": {},
            },
        ),
    )
    provider = SequenceProvider(
        [
            ProviderResponse(
                tool_calls=(
                    ToolCall(
                        name="execute_skill",
                        arguments={
                            "skillId": "use_move",
                            "args": {"move": "Bubble"},
                            "plaintextReasoning": "Continue attacking.",
                        },
                    ),
                )
            )
        ]
    )

    decision = DirectorRuntime(provider).decide(request)

    assert decision.error is None
    assert decision.tool_call is not None
    assert decision.tool_call.arguments["skillId"] == "resolve_battle_outcome_dialogue_bundle"
    assert decision.tool_call.arguments["args"] == {}


def test_invalid_tool_arguments_receive_one_repair_retry_before_execution() -> None:
    request = replace(
        canonical_request(),
        enabled_skills=(
            *canonical_request().enabled_skills,
            {"id": "recover_to_overworld", "label": "Recover", "params": {}},
        ),
    )
    provider = SequenceProvider(
        [
            ProviderResponse(
                tool_calls=(
                    ToolCall(
                        name="execute_skill",
                        arguments={
                            "args": {},
                            "plaintextReasoning": "Malformed first attempt.",
                        },
                    ),
                )
            ),
            successful_response(),
        ]
    )
    executor_calls: list[ToolCall] = []

    tick = DirectorRuntime(provider, max_retries=1, retry_backoff_seconds=0).run_tick(
        request,
        executor=lambda call: executor_calls.append(call)
        or {"actionStarted": True, "status": "succeeded"},
    )

    assert tick.decision.error is None
    assert tick.decision.attempts == 2
    assert provider.calls == 2
    assert len(executor_calls) == 1
    assert "previous response was rejected" in provider.prepared_requests[1].messages[-1]["content"]
    repair_tool_names = [tool["name"] for tool in provider.prepared_requests[1].tools]
    assert "execute_skill" not in repair_tool_names
    assert "navigate_within_viridian_forest_region" in repair_tool_names
    assert "recover_to_overworld" in repair_tool_names


def test_unavailable_skill_is_rejected_before_execution() -> None:
    provider = SequenceProvider(
        [
            ProviderResponse(
                tool_calls=(
                    ToolCall(
                        name="execute_skill",
                        arguments={
                            "skillId": "attempt_catch",
                            "args": {},
                            "plaintextReasoning": "Try a catch.",
                        },
                    ),
                )
            )
        ]
    )
    called = False

    def executor(call: ToolCall) -> dict[str, object]:
        nonlocal called
        called = True
        return {"actionStarted": True, "call": call.to_dict()}

    tick = DirectorRuntime(provider, max_retries=0).run_tick(
        canonical_request(), executor=executor
    )

    assert tick.decision.error is not None
    assert tick.decision.error.category == "unavailable_skill"
    assert called is False


def test_executor_exception_requires_checkpoint_reconciliation() -> None:
    provider = SequenceProvider([successful_response()])

    def fail_after_invocation(call: ToolCall) -> dict[str, object]:
        del call
        raise RuntimeError("sidecar connection dropped")

    tick = DirectorRuntime(provider).run_tick(
        canonical_request(), executor=fail_after_invocation
    )

    assert tick.decision.error is None
    assert tick.execution is not None
    assert tick.execution["status"] == "error"
    assert tick.execution["actionStarted"] is None
    assert tick.execution["actionStateKnown"] is False
    assert tick.execution["requiresCheckpointReconciliation"] is True
    assert tick.execution["error"]["category"] == "execution_error"

    report = build_director_report(
        run_id="execution-error",
        mode="chapter_segment",
        provider=provider,
        model="model-a",
        goal="Reach forest grass.",
        requests=[canonical_request()],
        ticks=[tick],
        finish={"status": "failed", "failureCategory": "execution_error"},
    )
    assert report["errors"][0]["category"] == "execution_error"


def test_reports_share_schema_and_never_serialize_credentials() -> None:
    request = canonical_request()
    reports = []
    for provider_id in ("local-test", "hosted-test"):
        provider = SequenceProvider([successful_response()], provider_id=provider_id)
        provider_request = replace(request, provider=provider_id)
        tick = DirectorRuntime(provider).run_tick(provider_request)
        report = build_director_report(
            run_id=provider_id,
            mode="provider_gate",
            provider=provider,
            model=request.model,
            goal=request.goal,
            requests=[provider_request],
            ticks=[tick],
            finish={"status": "stopped", "success": False},
        )
        reports.append(report)

    assert {report["schema"] for report in reports} == {REPORT_SCHEMA}
    assert reports[0].keys() == reports[1].keys()
    assert reports[0]["provider"]["provider"] == "local-test"
    assert reports[1]["provider"]["provider"] == "hosted-test"
    assert reports[0]["provider"]["model"] == request.model
    assert set(reports[0]["provider"]["capabilities"]) == {
        "images",
        "structuredTools",
        "reasoningControls",
        "streaming",
        "usageAccounting",
    }
    assert reports[0]["usage"]["totalTokens"] == 120
    assert reports[0]["usage"]["estimatedCostUsd"] is None
    assert reports[0]["latencyMs"] >= 0
    serialized = json.dumps(reports)
    assert "apiKey" not in serialized
    assert "apiToken" not in serialized
    assert "Authorization" not in serialized


def test_provider_usage_totals_known_fields_without_inventing_unknowns() -> None:
    total = ProviderUsage.total(
        [
            ProviderUsage(
                input_tokens=10,
                output_tokens=2,
                total_tokens=12,
                estimated_cost_usd=0.001,
            ),
            ProviderUsage(
                input_tokens=20,
                output_tokens=3,
                total_tokens=23,
                estimated_cost_usd=0.002,
            ),
        ]
    )

    assert total.input_tokens == 30
    assert total.output_tokens == 5
    assert total.total_tokens == 35
    assert total.reasoning_tokens is None
    assert total.estimated_cost_usd == 0.003

    partial = ProviderUsage.total(
        [
            ProviderUsage(
                input_tokens=10,
                output_tokens=2,
                total_tokens=12,
                estimated_cost_usd=0.001,
            ),
            ProviderUsage(),
        ]
    )
    assert partial.input_tokens is None
    assert partial.output_tokens is None
    assert partial.total_tokens is None
    assert partial.estimated_cost_usd is None


def test_python_prompting_truncates_messages_and_actions_at_history_boundary() -> None:
    request = replace(
        canonical_request(),
        messages=tuple(
            {"role": "user", "content": f"message-{index}"} for index in range(5)
        ),
        action_history=tuple(
            {"action": index, "skillId": "skill", "result": {"status": "ok"}}
            for index in range(5)
        ),
        max_history=2,
    )

    prepared = prepare_director_request(request, ProviderCapabilities())
    tick_payload = json.loads(prepared.messages[-1]["content"])

    assert [message["content"] for message in prepared.messages[:-1]] == [
        "message-3",
        "message-4",
    ]
    assert [action["action"] for action in tick_payload["recentActions"]] == [3, 4]
    assert request.summary()["messageCount"] == 2
    assert request.summary()["actionHistoryCount"] == 2


def test_zero_history_limit_includes_no_prior_history() -> None:
    request = replace(
        canonical_request(),
        messages=({"role": "user", "content": "old"},),
        action_history=({"action": 1, "skillId": "old"},),
        max_history=0,
    )

    prepared = prepare_director_request(request, ProviderCapabilities())
    tick_payload = json.loads(prepared.messages[-1]["content"])

    assert len(prepared.messages) == 1
    assert tick_payload["recentActions"] == []
    assert request.summary()["messageCount"] == 0
    assert request.summary()["actionHistoryCount"] == 0


def test_navigation_target_plural_normalizes_to_canonical_singular_arg() -> None:
    provider = SequenceProvider(
        [
            ProviderResponse(
                tool_calls=(
                    ToolCall(
                        name="execute_skill",
                        arguments={
                            "skillId": "navigate_within_viridian_forest_region",
                            "args": {"targets": ["forest_grass"]},
                            "plaintextReasoning": "Move toward the named target.",
                        },
                    ),
                )
            )
        ]
    )

    decision = DirectorRuntime(provider).decide(canonical_request())

    assert decision.error is None
    assert decision.tool_call is not None
    assert decision.tool_call.arguments["args"] == {"target": "forest_grass"}
