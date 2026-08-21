from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from pokemon_player.director_contracts import (
    DirectorDecision,
    DirectorError,
    DirectorRequest,
    DirectorTickResult,
    JsonObject,
    ToolCall,
)
from pokemon_player.director_prompting import prepare_director_request
from pokemon_player.director_providers import DirectorProvider, ProviderFailure


ToolExecutor = Callable[[ToolCall], JsonObject]


class DirectorRuntime:
    def __init__(
        self,
        provider: DirectorProvider,
        *,
        max_retries: int = 1,
        retry_backoff_seconds: float = 0.25,
    ) -> None:
        self.provider = provider
        self.max_retries = max(max_retries, 0)
        self.retry_backoff_seconds = max(retry_backoff_seconds, 0.0)

    def decide(self, request: DirectorRequest) -> DirectorDecision:
        started = time.perf_counter()
        attempts = 0
        prepared = None
        if request.provider != self.provider.provider_id:
            return self._error_decision(
                request,
                DirectorError(
                    category="invalid_request",
                    message=(
                        f"DirectorRequest provider {request.provider!r} does not match "
                        f"adapter {self.provider.provider_id!r}."
                    ),
                    retryable=False,
                    provider=self.provider.provider_id,
                ),
                latency_ms=(time.perf_counter() - started) * 1000,
                attempts=attempts,
            )
        try:
            prepared = prepare_director_request(request, self.provider.capabilities)
        except (OSError, ValueError) as exc:
            return self._error_decision(
                request,
                DirectorError(
                    category="invalid_request",
                    message=str(exc),
                    retryable=False,
                    provider=self.provider.provider_id,
                ),
                latency_ms=(time.perf_counter() - started) * 1000,
                attempts=attempts,
            )

        while attempts <= self.max_retries:
            attempts += 1
            try:
                response = self.provider.complete(prepared)
                latency_ms = (time.perf_counter() - started) * 1000
                normalized, error = normalize_provider_tool_calls(
                    response.tool_calls,
                    request.enabled_skill_ids(),
                    provider=self.provider.provider_id,
                )
                if error:
                    return self._error_decision(
                        request,
                        error,
                        latency_ms=latency_ms,
                        attempts=attempts,
                        assistant_message=response.assistant_message,
                    )
                return DirectorDecision(
                    request_id=request.request_id,
                    provider=self.provider.provider_id,
                    model=request.model,
                    capabilities=self.provider.capabilities,
                    tool_call=normalized,
                    assistant_message=response.assistant_message,
                    usage=response.usage,
                    latency_ms=latency_ms,
                    attempts=attempts,
                    response_id=response.response_id,
                    finish_reason=response.finish_reason,
                )
            except ProviderFailure as exc:
                if exc.error.retryable and attempts <= self.max_retries:
                    if self.retry_backoff_seconds:
                        time.sleep(self.retry_backoff_seconds * attempts)
                    continue
                return self._error_decision(
                    request,
                    exc.error,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    attempts=attempts,
                )
            except Exception as exc:
                return self._error_decision(
                    request,
                    DirectorError(
                        category="provider_error",
                        message=f"Provider adapter failed: {exc}",
                        retryable=False,
                        provider=self.provider.provider_id,
                    ),
                    latency_ms=(time.perf_counter() - started) * 1000,
                    attempts=attempts,
                )
        raise AssertionError("Director retry loop terminated unexpectedly.")

    def run_tick(
        self,
        request: DirectorRequest,
        executor: ToolExecutor | None = None,
    ) -> DirectorTickResult:
        decision = self.decide(request)
        if decision.error or not decision.tool_call:
            return DirectorTickResult(decision=decision, execution=None)
        if decision.tool_call.name == "finish_run":
            arguments = decision.tool_call.arguments
            return DirectorTickResult(
                decision=decision,
                execution={
                    "actionStarted": False,
                    "status": str(arguments.get("status") or "stopped"),
                    "success": bool(arguments.get("success")),
                    "summary": str(arguments.get("summary") or "Director stopped the run."),
                    "failureCategory": arguments.get("failureCategory"),
                    "plaintextReasoning": arguments.get("plaintextReasoning"),
                },
            )
        if executor is None:
            return DirectorTickResult(
                decision=decision,
                execution={
                    "actionStarted": False,
                    "status": "selected",
                    "summary": "Tool selected but no executor was supplied.",
                    "toolCall": decision.tool_call.to_dict(),
                },
            )
        try:
            result = executor(decision.tool_call)
            return DirectorTickResult(decision=decision, execution=result)
        except Exception as exc:
            return DirectorTickResult(
                decision=decision,
                execution={
                    "actionStarted": None,
                    "actionStateKnown": False,
                    "requiresCheckpointReconciliation": True,
                    "status": "error",
                    "summary": (
                        "Tool execution failed after invocation; reconcile the emulator from "
                        f"the saved checkpoint before continuing: {exc}"
                    ),
                    "error": DirectorError(
                        category="execution_error",
                        message=(
                            "Semantic tool execution failed after invocation; action state is "
                            f"unknown: {exc}"
                        ),
                        retryable=False,
                    ).to_dict(),
                },
            )

    def _error_decision(
        self,
        request: DirectorRequest,
        error: DirectorError,
        *,
        latency_ms: float,
        attempts: int,
        assistant_message: str = "",
    ) -> DirectorDecision:
        if not error.provider:
            error = replace(error, provider=self.provider.provider_id)
        return DirectorDecision(
            request_id=request.request_id,
            provider=self.provider.provider_id,
            model=request.model,
            capabilities=self.provider.capabilities,
            assistant_message=assistant_message,
            latency_ms=latency_ms,
            attempts=attempts,
            error=error,
        )


def normalize_provider_tool_calls(
    calls: tuple[ToolCall, ...],
    enabled_skill_ids: tuple[str, ...],
    *,
    provider: str,
) -> tuple[ToolCall | None, DirectorError | None]:
    if not calls:
        return None, DirectorError(
            category="missing_tool_call",
            message="Provider returned no semantic tool call.",
            retryable=False,
            provider=provider,
        )
    if len(calls) != 1:
        return None, DirectorError(
            category="multiple_tool_calls",
            message="Provider returned more than one tool call for a single-action tick.",
            retryable=False,
            provider=provider,
        )
    call = calls[0]
    normalized = normalize_tool_call(call, enabled_skill_ids)
    if normalized.name not in {"execute_skill", "finish_run"}:
        return None, DirectorError(
            category="unexpected_tool",
            message=f"Provider selected unsupported tool {normalized.name!r}.",
            retryable=False,
            provider=provider,
        )
    if normalized.name == "execute_skill":
        skill_id = str(normalized.arguments.get("skillId") or "")
        if not skill_id:
            return None, DirectorError(
                category="invalid_tool_arguments",
                message="execute_skill did not include skillId.",
                retryable=False,
                provider=provider,
            )
        if skill_id not in enabled_skill_ids:
            return None, DirectorError(
                category="unavailable_skill",
                message=f"{skill_id} is not currently enabled.",
                retryable=False,
                provider=provider,
            )
    return normalized, None


def normalize_tool_call(call: ToolCall, enabled_skill_ids: tuple[str, ...]) -> ToolCall:
    name = call.name.strip()
    arguments = dict(call.arguments)
    aliases = {"execute_move": "use_move", "attack": "use_move", "use_attack": "use_move"}
    if name in aliases and aliases[name] in enabled_skill_ids:
        arguments = {
            "skillId": aliases[name],
            "args": arguments,
            "plaintextReasoning": arguments.pop("plaintextReasoning", ""),
        }
        name = "execute_skill"
    elif name in enabled_skill_ids:
        arguments = {
            "skillId": name,
            "args": arguments,
            "plaintextReasoning": arguments.pop("plaintextReasoning", ""),
        }
        name = "execute_skill"

    if name != "execute_skill":
        return ToolCall(name=name, arguments=arguments, call_id=call.call_id)

    skill_id, skill_args, reasoning = unwrap_execute_skill(arguments, enabled_skill_ids)
    normalized_args = normalize_skill_args(skill_id, skill_args)
    return ToolCall(
        name="execute_skill",
        arguments={
            "skillId": skill_id,
            "args": normalized_args,
            "plaintextReasoning": reasoning,
        },
        call_id=call.call_id,
    )


def unwrap_execute_skill(
    arguments: JsonObject,
    enabled_skill_ids: tuple[str, ...],
) -> tuple[str, JsonObject, str]:
    reasoning = str(arguments.get("plaintextReasoning") or "")
    skill_id = str(arguments.get("skillId") or "")
    raw_args = arguments.get("args") if isinstance(arguments.get("args"), dict) else {}
    aliases = {"execute_move": "use_move", "attack": "use_move", "use_attack": "use_move"}
    if skill_id in aliases and aliases[skill_id] in enabled_skill_ids:
        skill_id = aliases[skill_id]
    if skill_id == "execute_skill":
        for candidate in (raw_args, arguments):
            if not isinstance(candidate, dict):
                continue
            nested_id = str(candidate.get("skillId") or "")
            nested_id = aliases.get(nested_id, nested_id)
            if nested_id in enabled_skill_ids:
                nested_args = (
                    candidate.get("args") if isinstance(candidate.get("args"), dict) else {}
                )
                nested_reasoning = str(candidate.get("plaintextReasoning") or reasoning)
                return nested_id, nested_args, nested_reasoning
    return skill_id, raw_args, reasoning


def normalize_skill_args(skill_id: str, arguments: JsonObject) -> JsonObject:
    args = dict(arguments)
    if skill_id.startswith("navigate_within_"):
        raw_target: Any = args.get("target", args.get("targets"))
        if isinstance(raw_target, list):
            raw_target = raw_target[0] if raw_target else None
        if isinstance(raw_target, dict):
            raw_target = next(
                (
                    raw_target.get(key)
                    for key in ("target", "id", "name", "value")
                    if raw_target.get(key) is not None
                ),
                None,
            )
        args.pop("targets", None)
        if raw_target is not None:
            args["target"] = str(raw_target)
    elif skill_id == "handle_nickname_prompt":
        raw = args.get("choice", args.get("nicknameChoice", args.get("decision", "decline")))
        if isinstance(raw, bool):
            choice = "accept" if raw else "decline"
        else:
            choice = (
                "accept"
                if str(raw).strip().lower()
                in {"accept", "yes", "y", "true", "nickname", "name"}
                else "decline"
            )
        args["choice"] = choice
    elif skill_id == "enter_nickname_text":
        raw: Any = args.get("nickname", args.get("nicknameText", args.get("text", "")))
        if isinstance(raw, dict):
            raw = raw.get("nickname", raw.get("text", raw.get("name", "")))
        nickname = "".join(char for char in str(raw).upper() if "A" <= char <= "Z")[:10]
        args["nickname"] = nickname
    elif skill_id == "switch_party_member" and isinstance(args.get("target"), dict):
        target = args["target"]
        args["target"] = target.get("slot") or next(
            (
                target.get(key)
                for key in ("nickname", "species", "speciesName", "name")
                if target.get(key)
            ),
            None,
        )
    elif skill_id == "use_move" and isinstance(args.get("move"), dict):
        move = args["move"]
        args["move"] = next(
            (
                move.get(key)
                for key in ("name", "moveName", "move_name", "moveId", "move_id", "id")
                if move.get(key) is not None
            ),
            None,
        )
    return args
