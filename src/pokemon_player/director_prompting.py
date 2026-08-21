from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from pokemon_player.director_contracts import (
    DirectorRequest,
    JsonObject,
    ProviderCapabilities,
)


@dataclass(frozen=True)
class PreparedDirectorRequest:
    request: DirectorRequest
    instructions: str
    messages: tuple[JsonObject, ...]
    tools: tuple[JsonObject, ...]
    image_data_url: str | None


def prepare_director_request(
    request: DirectorRequest,
    capabilities: ProviderCapabilities,
) -> PreparedDirectorRequest:
    if not request.goal.strip():
        raise ValueError("DirectorRequest.goal must not be empty.")
    if not request.model.strip():
        raise ValueError("DirectorRequest.model must not be empty.")
    image_data_url = None
    if capabilities.images and request.screenshot_path and request.screenshot_path.exists():
        encoded = base64.b64encode(request.screenshot_path.read_bytes()).decode("ascii")
        image_data_url = f"data:image/png;base64,{encoded}"

    history_limit = max(request.max_history, 0)
    recent_messages = (
        tuple(request.messages[-history_limit:]) if history_limit else ()
    )
    tick = {
        "goal": request.goal,
        "tick": request.tick,
        "environment": compact_for_prompt(request.context),
        "enabledSkills": [compact_skill(skill) for skill in request.enabled_skills],
        "recentActions": compact_action_history(
            list(request.action_history[-history_limit:]) if history_limit else []
        ),
        "rules": [
            "Call exactly one tool.",
            "Only execute_skill with an id listed in enabledSkills.",
            "Use args allowed by that skill's params.",
            "Use finish_run only when the stated goal is complete or safely blocked.",
        ],
    }
    if request.capsule:
        tick["capsule"] = compact_for_prompt(request.capsule)

    messages: list[JsonObject] = []
    for message in recent_messages:
        role = str(message.get("role") or "user")
        if role not in {"user", "assistant", "tool"}:
            role = "user"
        messages.append({"role": role, "content": str(message.get("content") or "")})
    messages.append({"role": "user", "content": json.dumps(tick, indent=2)})

    return PreparedDirectorRequest(
        request=request,
        instructions=build_director_instructions(request),
        messages=tuple(messages),
        tools=tuple(build_director_tools(request.enabled_skill_ids())),
        image_data_url=image_data_url,
    )


def build_director_instructions(request: DirectorRequest) -> str:
    lines = [
        "You are the LLM Director for a Pokemon Red research agent.",
        "Choose high-level semantic Pokemon skills; do not emit raw controller sequences.",
        "Preserve strategic agency while obeying the supplied safety and rules context.",
        "Never invent skills or arguments that are not present in enabledSkills.",
        "Prefer semantic skills over literal_button_press whenever a semantic option exists.",
        "Every execute_skill call must include concise plaintextReasoning.",
        "For use_move pass a move name or id, not the full option object.",
        "For switch_party_member pass a slot, nickname, or species, not an option object.",
        "For handle_nickname_prompt pass choice=accept or choice=decline.",
        "For handle_move_learning_prompt pass choice=skip, or choice=replace with forgetMove.",
        "For handle_trainer_switch_prompt pass choice=keep, or choice=switch with a target party member.",
        "For enter_nickname_text pass uppercase A-Z text of at most ten characters.",
    ]
    lines.extend(instruction for instruction in request.runtime_instructions if instruction.strip())
    return "\n".join(lines)


def build_director_tools(enabled_skill_ids: tuple[str, ...]) -> list[JsonObject]:
    tools: list[JsonObject] = []
    if enabled_skill_ids:
        tools.append(
            {
                "name": "execute_skill",
                "description": "Execute one currently enabled semantic Pokemon player skill.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "skillId": {"type": "string", "enum": list(enabled_skill_ids)},
                        "args": {"type": "object", "additionalProperties": True},
                        "plaintextReasoning": {
                            "type": "string",
                            "description": "Concise reason this skill is appropriate now.",
                        },
                    },
                    "required": ["skillId", "args", "plaintextReasoning"],
                },
            }
        )
    tools.append(
        {
            "name": "finish_run",
            "description": "Stop because the goal is complete or safely blocked.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["completed", "stopped", "failed"],
                    },
                    "success": {"type": "boolean"},
                    "summary": {"type": "string"},
                    "failureCategory": {"type": ["string", "null"]},
                    "plaintextReasoning": {"type": "string"},
                },
                "required": [
                    "status",
                    "success",
                    "summary",
                    "failureCategory",
                    "plaintextReasoning",
                ],
            },
        }
    )
    return tools


def compact_skill(skill: JsonObject) -> JsonObject:
    return {
        "id": skill.get("id"),
        "label": skill.get("label"),
        "reason": skill.get("reason"),
        "params": compact_for_prompt(skill.get("params") or {}),
    }


def compact_action_history(history: list[JsonObject]) -> list[JsonObject]:
    compacted: list[JsonObject] = []
    for item in history:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        compacted.append(
            {
                "action": item.get("action"),
                "skillId": item.get("skillId"),
                "args": compact_for_prompt(item.get("args") or {}),
                "status": result.get("status"),
                "summary": result.get("summary"),
                "warnings": result.get("warnings") or [],
            }
        )
    return compacted


def compact_for_prompt(value: Any) -> Any:
    if isinstance(value, list):
        return [
            compacted
            for item in value
            if not is_empty_prompt_value(compacted := compact_for_prompt(item))
        ]
    if not isinstance(value, dict):
        return value
    omitted = {
        "createdUtc",
        "eventLogPath",
        "manifestPath",
        "path",
        "reportPath",
        "runDir",
        "screenshotPath",
        "screenshot_file",
        "statePath",
        "state_path",
        "tracePath",
        "url",
    }
    output: JsonObject = {}
    for key, raw in value.items():
        if key in omitted:
            continue
        compacted = compact_for_prompt(raw)
        if not is_empty_prompt_value(compacted):
            output[str(key)] = compacted
    return output


def is_empty_prompt_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
