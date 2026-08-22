from __future__ import annotations

from pokemon_player.director_contracts import DirectorRequest
from pokemon_player.director_prompting import prepare_director_request
from pokemon_player.director_reporting import build_director_report
from pokemon_player.director_providers import (
    OpenAICompatibleChatAdapter,
    OpenAIResponsesAdapter,
    ProviderFailure,
    ReplayAdapter,
    error_for_http_status,
    normalize_chat_completions_response,
    normalize_responses_response,
    sanitize_public_url,
)


def request() -> DirectorRequest:
    return DirectorRequest(
        goal="Reach forest grass.",
        provider="test",
        model="same-model",
        enabled_skills=(
            {
                "id": "navigate_within_viridian_forest_region",
                "label": "Navigate",
                "params": {"targets": ["forest_grass"]},
            },
        ),
        context={"snapshot": {"mode": "overworld"}},
        messages=({"role": "user", "content": "Continue safely."},),
        reasoning_effort="low",
        seed=5001,
    )


def test_adapters_report_effective_capability_flags() -> None:
    local = OpenAICompatibleChatAdapter("http://local/v1", "token")
    hosted = OpenAIResponsesAdapter("token")
    replay = ReplayAdapter([])

    assert local.capabilities.to_dict() == {
        "images": True,
        "structuredTools": True,
        "reasoningControls": False,
        "streaming": False,
        "usageAccounting": True,
    }
    assert hosted.capabilities.to_dict() == {
        "images": True,
        "structuredTools": True,
        "reasoningControls": True,
        "streaming": False,
        "usageAccounting": True,
    }
    assert replay.capabilities.to_dict() == {
        "images": False,
        "structuredTools": True,
        "reasoningControls": False,
        "streaming": False,
        "usageAccounting": True,
    }


def test_chat_and_responses_adapters_receive_same_canonical_tools_and_prompt() -> None:
    captured_chat: dict[str, object] = {}
    captured_responses: dict[str, object] = {}

    def chat_transport(url, payload, headers, timeout):
        captured_chat.update(payload)
        assert "secret-local" in headers["Authorization"]
        assert url.endswith("/chat/completions")
        assert timeout == 9
        return {
            "id": "chat-1",
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "execute_skill",
                                    "arguments": '{"skillId":"navigate_within_viridian_forest_region","args":{"target":"forest_grass"},"plaintextReasoning":"direct"}',
                                },
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 40, "completion_tokens": 5, "total_tokens": 45},
        }

    def responses_transport(url, payload, headers, timeout):
        captured_responses.update(payload)
        assert "secret-hosted" in headers["Authorization"]
        assert url.endswith("/responses")
        assert timeout == 9
        return {
            "id": "resp-1",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "execute_skill",
                    "arguments": '{"skillId":"navigate_within_viridian_forest_region","args":{"target":"forest_grass"},"plaintextReasoning":"direct"}',
                }
            ],
            "usage": {"input_tokens": 40, "output_tokens": 5, "total_tokens": 45},
        }

    canonical = request()
    chat = OpenAICompatibleChatAdapter(
        "http://local/v1",
        "secret-local",
        timeout_seconds=9,
        transport=chat_transport,
    )
    responses = OpenAIResponsesAdapter(
        "secret-hosted",
        timeout_seconds=9,
        transport=responses_transport,
    )
    chat_result = chat.complete(prepare_director_request(canonical, chat.capabilities))
    responses_result = responses.complete(
        prepare_director_request(canonical, responses.capabilities)
    )

    chat_tools = [item["function"] for item in captured_chat["tools"]]
    assert chat_tools == [
        {
            "name": item["name"],
            "description": item["description"],
            "parameters": item["parameters"],
        }
        for item in captured_responses["tools"]
    ]
    assert captured_chat["messages"][0]["content"] == captured_responses["instructions"]
    assert captured_chat["seed"] == 5001
    assert "seed" not in captured_responses
    assert chat_result.tool_calls[0].to_dict() == responses_result.tool_calls[0].to_dict()
    assert chat_result.usage.total_tokens == responses_result.usage.total_tokens == 45


def test_provider_specific_usage_normalizes_to_canonical_fields() -> None:
    chat = normalize_chat_completions_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "finish_run",
                                    "arguments": '{"status":"stopped","success":false,"summary":"done","failureCategory":null,"plaintextReasoning":"safe"}',
                                }
                            }
                        ]
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 4,
                "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
        },
        provider="chat",
    )
    responses = normalize_responses_response(
        {
            "output": [
                {
                    "type": "function_call",
                    "name": "finish_run",
                    "arguments": '{"status":"stopped","success":false,"summary":"done","failureCategory":null,"plaintextReasoning":"safe"}',
                }
            ],
            "usage": {
                "input_tokens": 11,
                "output_tokens": 4,
                "total_tokens": 15,
                "input_tokens_details": {"cached_tokens": 3},
                "output_tokens_details": {"reasoning_tokens": 2},
            },
        },
        provider="responses",
    )

    assert chat.usage.to_dict()["cachedInputTokens"] == 3
    assert responses.usage.to_dict()["reasoningTokens"] == 2
    assert chat.tool_calls[0].name == responses.tool_calls[0].name == "finish_run"


def test_both_network_adapters_preserve_normalized_error_category() -> None:
    def unavailable_transport(url, payload, headers, timeout):
        del url, payload, headers, timeout
        raise ProviderFailure(error_for_http_status(503, "temporarily unavailable"))

    canonical = request()
    adapters = [
        OpenAICompatibleChatAdapter("http://local/v1", "token", transport=unavailable_transport),
        OpenAIResponsesAdapter("token", transport=unavailable_transport),
    ]

    for adapter in adapters:
        try:
            adapter.complete(prepare_director_request(canonical, adapter.capabilities))
        except ProviderFailure as exc:
            assert exc.error.category == "provider_unavailable"
            assert exc.error.retryable is True
            assert exc.error.provider == adapter.provider_id
        else:
            raise AssertionError("Expected normalized provider failure.")


def test_public_provider_url_strips_credentials_query_and_fragment() -> None:
    assert sanitize_public_url("https://user:secret@example.com/v1?token=secret#debug") == (
        "https://example.com/v1"
    )


def test_hosted_report_public_config_never_contains_adapter_credentials() -> None:
    adapter = OpenAIResponsesAdapter(
        "unit-test-credential",
        base_url="https://user:password@example.com/v1?token=hidden#debug",
    )
    report = build_director_report(
        run_id="credential-test",
        mode="provider_gate",
        provider=adapter,
        model="hosted-model",
        goal="Stop safely.",
        requests=[],
        ticks=[],
        finish={"status": "stopped", "success": False},
    )

    serialized = str(report)
    assert "unit-test-credential" not in serialized
    assert "password" not in serialized
    assert "token=hidden" not in serialized
    assert report["provider"]["baseUrl"] == "https://example.com/v1"


def test_adapter_redacts_credentials_echoed_by_provider_errors() -> None:
    secret = "unit-test-credential"

    def unsafe_transport(url, payload, headers, timeout):
        del url, payload, headers, timeout
        raise ProviderFailure(
            error_for_http_status(401, f"Rejected Authorization: Bearer {secret}")
        )

    adapter = OpenAIResponsesAdapter(secret, transport=unsafe_transport)

    try:
        adapter.complete(prepare_director_request(request(), adapter.capabilities))
    except ProviderFailure as exc:
        assert secret not in exc.error.message
        assert "Bearer [REDACTED]" in exc.error.message
    else:
        raise AssertionError("Expected a redacted provider failure.")


def test_replay_provider_redacts_credential_like_error_fixtures() -> None:
    replay = ReplayAdapter(
        [
            {
                "error": {
                    "category": "authentication",
                    "message": "Rejected Bearer unit-test-credential",
                }
            }
        ]
    )

    try:
        replay.complete(prepare_director_request(request(), replay.capabilities))
    except ProviderFailure as exc:
        assert "unit-test-credential" not in exc.error.message
        assert "Bearer [REDACTED]" in exc.error.message
    else:
        raise AssertionError("Expected a redacted replay provider failure.")


def test_estimated_cost_uses_configured_per_million_rates() -> None:
    response = normalize_responses_response(
        {
            "output": [
                {
                    "type": "function_call",
                    "name": "finish_run",
                    "arguments": '{"status":"stopped","success":false,"summary":"done","failureCategory":null,"plaintextReasoning":"safe"}',
                }
            ],
            "usage": {"input_tokens": 1_000_000, "output_tokens": 500_000},
        },
        provider="responses",
        input_cost_per_million=2.0,
        output_cost_per_million=8.0,
    )

    assert response.usage.estimated_cost_usd == 6.0
