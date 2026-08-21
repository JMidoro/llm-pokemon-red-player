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
from pokemon_player.director_prompting import PreparedDirectorRequest, prepare_director_request
from pokemon_player.director_providers import DirectorProvider, ProviderFailure


ToolExecutor = Callable[[ToolCall], JsonObject]
RETRYABLE_DECISION_CATEGORIES = frozenset(
    {
        "invalid_tool_arguments",
        "missing_tool_call",
        "multiple_tool_calls",
        "unexpected_tool",
        "unavailable_skill",
    }
)
AGENCY_NEUTRAL_SOLE_SKILL_RECOVERY = frozenset(
    {
        "advance_dialogue",
        "resolve_battle_outcome_dialogue_bundle",
    }
)


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
                    if error.category in RETRYABLE_DECISION_CATEGORIES and attempts <= self.max_retries:
                        prepared = append_tool_repair_request(
                            prepared,
                            error,
                            request.enabled_skill_ids(),
                        )
                        if self.retry_backoff_seconds:
                            time.sleep(self.retry_backoff_seconds * attempts)
                        continue
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
    raw_args = (
        dict(arguments["args"])
        if isinstance(arguments.get("args"), dict)
        else direct_skill_args(arguments)
    )
    nested_reasoning = str(raw_args.pop("plaintextReasoning", "") or "")
    if not reasoning:
        reasoning = nested_reasoning
    aliases = {"execute_move": "use_move", "attack": "use_move", "use_attack": "use_move"}
    if skill_id in aliases and aliases[skill_id] in enabled_skill_ids:
        skill_id = aliases[skill_id]
    if skill_id in {"", "execute_skill"}:
        for candidate in (raw_args, arguments):
            if not isinstance(candidate, dict):
                continue
            nested_id = str(candidate.get("skillId") or "")
            nested_id = aliases.get(nested_id, nested_id)
            if nested_id in enabled_skill_ids:
                nested_args = (
                    dict(candidate["args"])
                    if isinstance(candidate.get("args"), dict)
                    else direct_skill_args(candidate)
                )
                candidate_reasoning = str(
                    candidate.get("plaintextReasoning")
                    or nested_args.pop("plaintextReasoning", "")
                    or reasoning
                )
                return nested_id, nested_args, candidate_reasoning
    if not skill_id:
        skill_id = infer_skill_id_from_args(raw_args, enabled_skill_ids)
    if not skill_id and len(enabled_skill_ids) == 1:
        # The chapter policy has already removed every strategic alternative.
        # Recovering the sole semantic id repairs a common small-model schema
        # omission without choosing gameplay strategy on the model's behalf.
        skill_id = enabled_skill_ids[0]
    if (
        skill_id
        and skill_id not in enabled_skill_ids
        and len(enabled_skill_ids) == 1
        and enabled_skill_ids[0] in AGENCY_NEUTRAL_SOLE_SKILL_RECOVERY
    ):
        # Dialogue continuation contains no tactical choice. If a small model
        # repeats its last battle action while this is the sole exposed
        # capability, follow the constrained mechanical surface and discard
        # the irrelevant tactical arguments.
        skill_id = enabled_skill_ids[0]
        raw_args = {}
    return skill_id, raw_args, reasoning


def direct_skill_args(arguments: JsonObject) -> JsonObject:
    return {
        str(key): value
        for key, value in arguments.items()
        if key not in {"args", "skillId", "plaintextReasoning"}
    }


def infer_skill_id_from_args(
    arguments: JsonObject,
    enabled_skill_ids: tuple[str, ...],
) -> str:
    keys = set(arguments)
    candidates: set[str] = set()

    discriminators = {
        "use_move": {"move", "moveId", "moveName", "move_id", "move_name"},
        "handle_nickname_prompt": {"choice", "nicknameChoice", "decision", "answer"},
        "handle_move_learning_prompt": {"choice", "decision", "response", "forgetMove", "forget_move"},
        "handle_trainer_switch_prompt": {"choice", "decision", "response"},
        "enter_nickname_text": {"nickname", "nicknameText", "text"},
        "purchase_pokemart_item": {"item", "quantity"},
        "walk_local_direction": {"direction", "steps"},
        "enter_grass_search_loop": {"patch", "grassPatch"},
    }
    for skill_id, expected_keys in discriminators.items():
        if skill_id in enabled_skill_ids and keys & expected_keys:
            candidates.add(skill_id)

    if keys & {"target", "slot", "species", "nickname"}:
        target_skills = [
            skill_id
            for skill_id in enabled_skill_ids
            if skill_id == "switch_party_member"
            or skill_id == "handle_trainer_switch_prompt"
            or skill_id == "overworld_rearrange_party"
            or skill_id == "talk_to_npc"
            or skill_id.startswith("navigate_within_")
        ]
        if len(target_skills) == 1:
            candidates.add(target_skills[0])

    return next(iter(candidates)) if len(candidates) == 1 else ""


def append_tool_repair_request(
    prepared: PreparedDirectorRequest,
    error: DirectorError,
    enabled_skill_ids: tuple[str, ...],
) -> PreparedDirectorRequest:
    enabled = ", ".join(enabled_skill_ids) or "none"
    content = (
        "Your previous response was rejected before any emulator input was sent: "
        f"{error.message} Retry now with exactly one tool call. The repair tools are named "
        f"directly after the enabled semantic skills: {enabled}. Call the chosen skill tool "
        "and include plaintextReasoning; pass that skill's arguments as top-level fields."
    )
    return replace(
        prepared,
        instructions=(
            prepared.instructions
            + "\nFor this schema-repair response, call one enabled semantic skill tool "
            "directly by name instead of execute_skill."
        ),
        messages=(*prepared.messages, {"role": "user", "content": content}),
        tools=direct_skill_repair_tools(prepared, enabled_skill_ids),
    )


def direct_skill_repair_tools(
    prepared: PreparedDirectorRequest,
    enabled_skill_ids: tuple[str, ...],
) -> tuple[JsonObject, ...]:
    skill_context = {
        str(skill.get("id")): skill
        for skill in prepared.request.enabled_skills
        if isinstance(skill, dict) and skill.get("id")
    }
    tools: list[JsonObject] = []
    for skill_id in enabled_skill_ids:
        skill = skill_context.get(skill_id, {})
        description = str(
            skill.get("reason")
            or skill.get("label")
            or f"Execute the enabled semantic skill {skill_id}."
        )
        tools.append(
            {
                "name": skill_id,
                "description": description,
                "parameters": {
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {
                        "plaintextReasoning": {
                            "type": "string",
                            "description": "Concise reason this skill is appropriate now.",
                        }
                    },
                    "required": ["plaintextReasoning"],
                },
            }
        )
    finish_tool = next(
        (tool for tool in prepared.tools if tool.get("name") == "finish_run"),
        None,
    )
    if finish_tool:
        tools.append(finish_tool)
    return tuple(tools)


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
    elif skill_id == "handle_move_learning_prompt":
        raw = args.get("choice", args.get("decision", args.get("response", "skip")))
        value = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
        args["choice"] = (
            "replace"
            if value in {"replace", "learn", "yes", "accept", "forget"}
            else "skip"
        )
        raw_move = args.get("forgetMove", args.get("forget_move", args.get("move")))
        if isinstance(raw_move, dict):
            raw_move = next(
                (
                    raw_move.get(key)
                    for key in ("name", "moveName", "move_name", "slot", "moveId", "move_id", "id")
                    if raw_move.get(key) is not None
                ),
                None,
            )
        if raw_move is not None:
            args["forgetMove"] = raw_move
    elif skill_id == "handle_trainer_switch_prompt":
        raw = args.get("choice", args.get("decision", args.get("response", "keep")))
        value = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
        args["choice"] = (
            "switch"
            if value in {"switch", "change", "yes", "accept", "switch_pokemon"}
            else "keep"
        )
        if isinstance(args.get("target"), dict):
            target = args["target"]
            args["target"] = target.get("slot") or next(
                (
                    target.get(key)
                    for key in ("nickname", "species", "speciesName", "name")
                    if target.get(key)
                ),
                None,
            )
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
