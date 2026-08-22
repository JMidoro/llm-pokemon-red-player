from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class ProviderCapabilities:
    images: bool = False
    structured_tools: bool = True
    reasoning_controls: bool = False
    streaming: bool = False
    usage_accounting: bool = False

    def to_dict(self) -> JsonObject:
        return {
            "images": self.images,
            "structuredTools": self.structured_tools,
            "reasoningControls": self.reasoning_controls,
            "streaming": self.streaming,
            "usageAccounting": self.usage_accounting,
        }


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: JsonObject = field(default_factory=dict)
    call_id: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "callId": self.call_id,
        }


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_input_tokens: int | None = None
    estimated_cost_usd: float | None = None

    def to_dict(self) -> JsonObject:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "totalTokens": self.total_tokens,
            "reasoningTokens": self.reasoning_tokens,
            "cachedInputTokens": self.cached_input_tokens,
            "estimatedCostUsd": self.estimated_cost_usd,
        }

    @classmethod
    def total(cls, usages: list[ProviderUsage]) -> ProviderUsage:
        def add_optional(attribute: str) -> int | None:
            values = [getattr(usage, attribute) for usage in usages]
            known_values = [value for value in values if value is not None]
            if not values or len(known_values) != len(values):
                return None
            return sum(known_values)

        costs = [usage.estimated_cost_usd for usage in usages]
        known_costs = [cost for cost in costs if cost is not None]
        total_cost = None
        if costs and len(known_costs) == len(costs):
            total_cost = round(sum(known_costs), 8)
        return cls(
            input_tokens=add_optional("input_tokens"),
            output_tokens=add_optional("output_tokens"),
            total_tokens=add_optional("total_tokens"),
            reasoning_tokens=add_optional("reasoning_tokens"),
            cached_input_tokens=add_optional("cached_input_tokens"),
            estimated_cost_usd=total_cost,
        )


@dataclass(frozen=True)
class DirectorError:
    category: str
    message: str
    retryable: bool = False
    provider: str | None = None
    status_code: int | None = None

    def to_dict(self) -> JsonObject:
        return {
            "category": self.category,
            "message": self.message,
            "retryable": self.retryable,
            "provider": self.provider,
            "statusCode": self.status_code,
        }


@dataclass(frozen=True)
class DirectorRequest:
    goal: str
    model: str
    enabled_skills: tuple[JsonObject, ...]
    context: JsonObject
    provider: str
    messages: tuple[JsonObject, ...] = ()
    action_history: tuple[JsonObject, ...] = ()
    screenshot_path: Path | None = None
    capsule: JsonObject | None = None
    tick: int = 0
    max_history: int = 20
    reasoning_effort: str | None = None
    temperature: float | None = None
    seed: int | None = None
    max_output_tokens: int = 1400
    runtime_instructions: tuple[str, ...] = ()
    metadata: JsonObject = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid4().hex)

    def enabled_skill_ids(self) -> tuple[str, ...]:
        return tuple(
            str(skill.get("id"))
            for skill in self.enabled_skills
            if isinstance(skill, dict) and skill.get("id")
        )

    def summary(self) -> JsonObject:
        history_limit = max(self.max_history, 0)
        return {
            "requestId": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "goal": self.goal,
            "tick": self.tick,
            "enabledSkills": list(self.enabled_skill_ids()),
            "messageCount": min(len(self.messages), history_limit),
            "actionHistoryCount": min(len(self.action_history), history_limit),
            "imageRequested": self.screenshot_path is not None,
            "reasoningEffort": self.reasoning_effort,
            "seed": self.seed,
            "maxOutputTokens": self.max_output_tokens,
            "checkpoint": self.metadata.get("checkpoint"),
        }


@dataclass(frozen=True)
class DirectorDecision:
    request_id: str
    provider: str
    model: str
    capabilities: ProviderCapabilities
    tool_call: ToolCall | None = None
    assistant_message: str = ""
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    latency_ms: float = 0.0
    attempts: int = 1
    response_id: str | None = None
    finish_reason: str | None = None
    error: DirectorError | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.tool_call is not None

    def to_dict(self) -> JsonObject:
        return {
            "requestId": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "capabilities": self.capabilities.to_dict(),
            "toolCall": self.tool_call.to_dict() if self.tool_call else None,
            "assistantMessage": self.assistant_message,
            "usage": self.usage.to_dict(),
            "latencyMs": round(self.latency_ms, 1),
            "attempts": self.attempts,
            "responseId": self.response_id,
            "finishReason": self.finish_reason,
            "error": self.error.to_dict() if self.error else None,
        }


@dataclass(frozen=True)
class ProviderResponse:
    tool_calls: tuple[ToolCall, ...] = ()
    assistant_message: str = ""
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    response_id: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class DirectorTickResult:
    decision: DirectorDecision
    execution: JsonObject | None = None

    def to_dict(self) -> JsonObject:
        return {
            "decision": self.decision.to_dict(),
            "execution": self.execution,
        }
