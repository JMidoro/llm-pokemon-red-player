from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pokemon_player.director_contracts import DirectorRequest, JsonObject, ToolCall
from pokemon_player.director_provider_factory import canonical_provider_id, make_provider
from pokemon_player.director_reporting import build_director_report
from pokemon_player.director_runtime import DirectorRuntime


DEFAULT_DIRECTOR_PLAYER_URL = "http://127.0.0.1:8765"


def run_browser_director_tick(body: JsonObject, *, repo_root: Path) -> JsonObject:
    goal = str(body.get("goal") or "").strip()
    if not goal:
        raise ValueError("goal is required")
    provider_id = canonical_provider_id(
        str(body.get("provider") or os.environ.get("LLM_PLAYER_PROVIDER") or "openai-responses")
    )
    model = selected_model(body.get("model"), provider_id)
    reasoning_effort = sanitize_reasoning_effort(body.get("reasoningEffort"))
    message_limit = sanitize_message_limit(body.get("messageLimit"))
    messages = sanitize_messages(body.get("messages"), message_limit, goal)
    tick_index = safe_int(body.get("tick"), 0)
    sidecar_url = os.environ.get("DIRECTOR_PLAYER_URL") or DEFAULT_DIRECTOR_PLAYER_URL
    provider = make_provider(
        provider_id,
        env_path=repo_root / ".env",
        timeout_seconds=safe_int(os.environ.get("DIRECTOR_PROVIDER_TIMEOUT_SECONDS"), 180),
        replay_path=Path(os.environ["DIRECTOR_REPLAY_PATH"])
        if provider_id == "replay" and os.environ.get("DIRECTOR_REPLAY_PATH")
        else None,
    )
    runtime = DirectorRuntime(
        provider,
        max_retries=safe_int(os.environ.get("DIRECTOR_PROVIDER_MAX_RETRIES"), 1),
    )
    sidecar = DirectorPlayerHttpClient(sidecar_url)
    player_status_raw = sidecar.status(fresh=True)
    player_status = compact_player_status(player_status_raw)
    capsule = load_capsule(repo_root)
    screenshot_path = safe_screenshot_path(player_status_raw.get("screenshotPath"), repo_root)
    checkpoint = {
        "kind": "pre_provider_observation",
        "snapshotHash": player_status_raw.get("snapshotHash"),
        "screenshotPath": str(screenshot_path) if screenshot_path else None,
        "sidecarSessionId": nested_value(player_status_raw, "session", "id"),
        "actionStarted": False,
    }
    request = DirectorRequest(
        goal=goal,
        model=model,
        provider=provider_id,
        enabled_skills=tuple(enabled_skills(player_status)),
        context=player_status,
        messages=tuple(messages),
        screenshot_path=screenshot_path,
        capsule=capsule,
        tick=tick_index,
        max_history=message_limit,
        reasoning_effort=reasoning_effort,
        runtime_instructions=(
            "The current capsule spec and environment are authoritative for this tick.",
            "If the player is busy or no safe skill is enabled, use finish_run instead of guessing.",
            "A finish decision does not itself declare capsule success; observed evidence remains authoritative.",
        ),
        metadata={"checkpoint": checkpoint},
    )

    def execute(call: ToolCall) -> JsonObject:
        arguments = call.arguments
        skill_id = str(arguments.get("skillId") or "")
        skill_args = arguments.get("args") if isinstance(arguments.get("args"), dict) else {}
        before = sidecar.status(fresh=False)
        current_enabled = {
            str(skill.get("id"))
            for skill in before.get("skills", [])
            if isinstance(skill, dict) and skill.get("enabled") is True
        }
        if skill_id not in current_enabled:
            return {
                "actionStarted": False,
                "status": "blocked",
                "summary": f"{skill_id} is no longer enabled.",
                "skillId": skill_id,
                "args": skill_args,
                "plaintextReasoning": arguments.get("plaintextReasoning"),
                "playerStatus": compact_player_status(before),
            }
        status = sidecar.execute_skill(skill_id, skill_args)
        last_result = status.get("lastResult")
        last_result = last_result if isinstance(last_result, dict) else {}
        return {
            "actionStarted": True,
            "status": str(last_result.get("status") or "unknown"),
            "summary": str(last_result.get("summary") or f"Executed {skill_id}."),
            "skillId": skill_id,
            "args": skill_args,
            "plaintextReasoning": arguments.get("plaintextReasoning"),
            "lastResult": last_result,
            "playerStatus": compact_player_status(status),
        }

    tick_result = runtime.run_tick(request, executor=execute)
    execution = tick_result.execution or {}
    latest_status = execution.get("playerStatus")
    if not isinstance(latest_status, dict):
        latest_status = player_status
    finish = finish_for_browser_tick(tick_result)
    run_id = timestamp_for_path()
    run_dir = repo_root / "research" / "artifacts" / "llm-director-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "report.json"
    report = build_director_report(
        run_id=run_id,
        mode="browser_tick",
        provider=provider,
        model=model,
        goal=goal,
        requests=[request],
        ticks=[tick_result],
        finish=finish,
        history=[],
        artifacts={
            "reportPath": str(report_path),
            "preProviderCheckpoint": checkpoint,
            "screenshotPath": str(screenshot_path) if screenshot_path else None,
        },
        context={"tick": tick_index, "messageLimit": message_limit},
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    assistant_message = browser_narration(tick_result)
    result_messages = [
        *messages,
        {
            "role": "assistant",
            "content": assistant_message,
            "createdUtc": datetime.now(UTC).isoformat(),
            "kind": "llm_director_result",
        },
    ][-message_limit:]
    response: JsonObject = {
        **report,
        "assistantMessage": assistant_message,
        "messages": result_messages,
        "steps": browser_steps(tick_result),
        "reportPath": str(report_path),
        "playerStatus": latest_status,
        "tick": tick_index,
        "envSnapshot": player_status,
        "screenshotPath": str(screenshot_path) if screenshot_path else None,
        "screenshotSent": bool(screenshot_path and provider.capabilities.images),
        "messageLimit": message_limit,
        "requestMessages": messages,
        "requestSummary": request.summary(),
        "reasoningEffort": reasoning_effort,
        "model": model,
    }
    if tick_result.decision.error:
        response["error"] = tick_result.decision.error.message
    elif finish.get("status") == "error":
        response["error"] = finish.get("summary")
    return response


class DirectorPlayerHttpClient:
    def __init__(self, base_url: str, timeout_seconds: int = 310) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def status(self, *, fresh: bool) -> JsonObject:
        suffix = "/status?" + urlencode({"fresh": 1}) if fresh else "/status"
        return self._request(suffix, method="GET")

    def execute_skill(self, skill_id: str, args: JsonObject) -> JsonObject:
        return self._request(
            "/skill",
            method="POST",
            body={"skillId": skill_id, "args": args},
        )

    def _request(
        self,
        endpoint: str,
        *,
        method: str,
        body: JsonObject | None = None,
    ) -> JsonObject:
        request = Request(
            self.base_url + endpoint,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Director player HTTP {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Director player is unavailable: {exc.reason}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Director player returned a non-object response.")
        return parsed


def compact_player_status(status: JsonObject) -> JsonObject:
    snapshot = status.get("snapshot") if isinstance(status.get("snapshot"), dict) else {}
    history = status.get("history") if isinstance(status.get("history"), list) else []
    return {
        "busy": status.get("busy"),
        "snapshotHash": status.get("snapshotHash"),
        "screenshotPath": status.get("screenshotPath"),
        "snapshot": {
            "mode": snapshot.get("mode"),
            "position": snapshot.get("position"),
            "party": snapshot.get("party"),
            "inventory": snapshot.get("inventory"),
            "enemy": snapshot.get("enemy"),
            "active_party_member": snapshot.get("active_party_member"),
            "plaintext_summary": snapshot.get("plaintext_summary"),
        },
        "signals": [
            {"label": signal.get("label"), "value": signal.get("value")}
            for signal in status.get("signals", [])
            if isinstance(signal, dict)
        ],
        "skills": [
            {
                "id": skill.get("id"),
                "label": skill.get("label"),
                "reason": skill.get("reason"),
                "params": skill.get("params") or {},
                "enabled": True,
            }
            for skill in status.get("skills", [])
            if isinstance(skill, dict) and skill.get("enabled") is True
        ],
        "observations": [
            {
                "summary": item.get("summary"),
                "evidence": item.get("evidence") or [],
            }
            for item in history[:8]
            if isinstance(item, dict)
            and (item.get("skillId") == "observation" or item.get("status") == "info")
        ],
        "lastResult": status.get("lastResult") if isinstance(status.get("lastResult"), dict) else None,
    }


def enabled_skills(status: JsonObject) -> list[JsonObject]:
    skills = status.get("skills") if isinstance(status.get("skills"), list) else []
    return [skill for skill in skills if isinstance(skill, dict) and skill.get("enabled") is True]


def sanitize_messages(value: Any, limit: int, goal: str) -> list[JsonObject]:
    raw = value if isinstance(value, list) else []
    messages: list[JsonObject] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        if role not in {"user", "assistant", "tool"}:
            continue
        messages.append(
            {
                "role": role,
                "content": str(item.get("content") or "")[:8_000],
                "createdUtc": item.get("createdUtc"),
                "kind": item.get("kind"),
            }
        )
    if not messages:
        messages.append(
            {
                "role": "user",
                "content": goal[:8_000],
                "createdUtc": datetime.now(UTC).isoformat(),
                "kind": "goal",
            }
        )
    return messages[-limit:]


def finish_for_browser_tick(tick_result: Any) -> JsonObject:
    if tick_result.decision.error:
        return {
            "status": "error",
            "success": False,
            "summary": tick_result.decision.error.message,
            "failureCategory": tick_result.decision.error.category,
            "actionStarted": False,
        }
    execution = tick_result.execution or {}
    if execution.get("status") == "error":
        error = execution.get("error") if isinstance(execution.get("error"), dict) else {}
        action_started = execution.get("actionStarted")
        return {
            "status": "error",
            "success": False,
            "summary": str(execution.get("summary") or "Semantic tool execution failed."),
            "failureCategory": str(error.get("category") or "execution_error"),
            "actionStarted": action_started if isinstance(action_started, bool) else None,
            "actionStateKnown": bool(execution.get("actionStateKnown")),
            "requiresCheckpointReconciliation": True,
        }
    if tick_result.decision.tool_call and tick_result.decision.tool_call.name == "finish_run":
        return dict(execution)
    return {
        "status": "stopped",
        "success": False,
        "summary": str(execution.get("summary") or "Director tick completed."),
        "failureCategory": None,
        "actionStarted": bool(execution.get("actionStarted")),
    }


def browser_narration(tick_result: Any) -> str:
    decision = tick_result.decision
    if decision.error:
        return f"Director request failed safely: {decision.error.message}"
    execution = tick_result.execution or {}
    if decision.assistant_message:
        return decision.assistant_message
    reasoning = ""
    if decision.tool_call:
        reasoning = str(decision.tool_call.arguments.get("plaintextReasoning") or "").strip()
    summary = str(execution.get("summary") or "Director tick completed.")
    return f"{reasoning}\n\nTool result: {summary}".strip()


def browser_steps(tick_result: Any) -> list[JsonObject]:
    decision = tick_result.decision
    if not decision.tool_call:
        return []
    execution = tick_result.execution or {}
    return [
        {
            "kind": "tool",
            "name": decision.tool_call.name,
            "args": decision.tool_call.arguments,
            "status": str(execution.get("status") or "unknown"),
            "summary": str(execution.get("summary") or decision.tool_call.name),
            "plaintextReasoning": decision.tool_call.arguments.get("plaintextReasoning"),
            "result": execution,
        }
    ]


def selected_model(value: Any, provider_id: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if provider_id == "lmstudio-chat":
        return os.environ.get("LMSTUDIO_MODEL", "google/gemma-4-e4b")
    return os.environ.get("OPENAI_LLM_PLAYER_MODEL", "gpt-5.4-nano")


def sanitize_reasoning_effort(value: Any) -> str:
    effort = str(value or os.environ.get("OPENAI_REASONING_EFFORT") or "low").strip()
    return effort if effort in {"minimal", "low", "medium", "high"} else "low"


def sanitize_message_limit(value: Any) -> int:
    return max(1, min(safe_int(value, 20), 100))


def safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_screenshot_path(value: Any, repo_root: Path) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value).resolve()
    try:
        candidate.relative_to((repo_root / "research").resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def load_capsule(repo_root: Path) -> JsonObject:
    path = repo_root / "research" / "capsules" / "viridian_forest_catching.json"
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Capsule spec is not a JSON object: {path}")
    return {
        key: parsed.get(key)
        for key in (
            "id",
            "name",
            "objective",
            "success_conditions",
            "failure_conditions",
            "abort_conditions",
            "budgets",
        )
    }


def nested_value(value: JsonObject, key: str, nested_key: str) -> Any:
    nested = value.get(key)
    return nested.get(nested_key) if isinstance(nested, dict) else None


def timestamp_for_path() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
