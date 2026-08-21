from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pokemon_player.director_contracts import (
    DirectorRequest,
    DirectorTickResult,
    JsonObject,
    ProviderUsage,
)
from pokemon_player.director_providers import DirectorProvider


REPORT_SCHEMA = "director_segment_run_v1"


def build_director_report(
    *,
    run_id: str,
    mode: str,
    provider: DirectorProvider,
    model: str,
    goal: str,
    requests: list[DirectorRequest],
    ticks: list[DirectorTickResult],
    finish: JsonObject,
    history: list[JsonObject] | None = None,
    artifacts: JsonObject | None = None,
    context: JsonObject | None = None,
) -> JsonObject:
    usages = [tick.decision.usage for tick in ticks]
    decision_errors = [
        tick.decision.error.to_dict()
        for tick in ticks
        if tick.decision.error is not None
    ]
    execution_errors = [
        tick.execution["error"]
        for tick in ticks
        if isinstance(tick.execution, dict) and isinstance(tick.execution.get("error"), dict)
    ]
    return {
        "schema": REPORT_SCHEMA,
        "createdUtc": datetime.now(UTC).isoformat(),
        "runId": run_id,
        "mode": mode,
        "status": normalized_status(finish),
        "goal": goal,
        "provider": {
            **provider.public_config(),
            "model": model,
        },
        "usage": ProviderUsage.total(usages).to_dict(),
        "latencyMs": round(sum(tick.decision.latency_ms for tick in ticks), 1),
        "finish": finish,
        "requests": [request.summary() for request in requests],
        "ticks": [tick.to_dict() for tick in ticks],
        "history": history or [],
        "errors": [*decision_errors, *execution_errors],
        "artifacts": artifacts or {},
        "context": context or {},
    }


def normalized_status(finish: dict[str, Any]) -> str:
    status = str(finish.get("status") or "stopped")
    if status in {"completed", "checkpoint", "stopped", "failed", "error"}:
        return status
    return "stopped"
