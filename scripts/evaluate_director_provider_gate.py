from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pokemon_player.director_contracts import DirectorRequest, JsonObject  # noqa: E402
from pokemon_player.director_provider_factory import make_provider  # noqa: E402
from pokemon_player.director_reporting import build_director_report  # noqa: E402
from pokemon_player.director_runtime import DirectorRuntime  # noqa: E402


DEFAULT_SCENARIO = (
    ROOT / "research" / "evals" / "provider-neutral-director" / "frozen_scenario.json"
)
DEFAULT_REPLAY = (
    ROOT / "research" / "evals" / "provider-neutral-director" / "replay_decisions.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen provider-neutral Director gate.")
    parser.add_argument(
        "--provider",
        choices=("lmstudio-chat", "openai-responses", "replay"),
        required=True,
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--scenario", default=str(DEFAULT_SCENARIO))
    parser.add_argument("--replay-path", default=str(DEFAULT_REPLAY))
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-token", default=None)
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--request-timeout-seconds", type=int, default=180)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    scenario = load_object(Path(args.scenario))
    provider = make_provider(
        args.provider,
        env_path=ROOT / ".env",
        base_url=args.base_url,
        api_token=args.api_token,
        timeout_seconds=args.request_timeout_seconds,
        replay_path=Path(args.replay_path) if args.provider == "replay" else None,
    )
    request = request_from_scenario(
        scenario,
        provider=args.provider,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
    )
    tick = DirectorRuntime(provider, max_retries=args.max_retries).run_tick(request)
    if tick.decision.error:
        finish = {
            "status": "error",
            "success": False,
            "summary": tick.decision.error.message,
            "failureCategory": tick.decision.error.category,
            "actionStarted": False,
        }
    else:
        finish = {
            "status": "stopped",
            "success": False,
            "summary": "Frozen decision completed without emulator execution.",
            "failureCategory": None,
            "actionStarted": False,
        }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_director_report(
        run_id=f"provider-gate-{args.provider}",
        mode="provider_gate",
        provider=provider,
        model=args.model,
        goal=request.goal,
        requests=[request],
        ticks=[tick],
        finish=finish,
        context={
            "scenarioId": scenario.get("id"),
            "scenarioSha256": canonical_json_hash(scenario),
            "semanticRegistrySha256": semantic_registry_hash(scenario),
            "emulatorExecutionEnabled": False,
        },
    )
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(output_path.resolve()),
                "schema": report["schema"],
                "provider": args.provider,
                "model": args.model,
                "scenarioId": scenario.get("id"),
                "scenarioSha256": report["context"]["scenarioSha256"],
                "semanticRegistrySha256": report["context"]["semanticRegistrySha256"],
                "decision": tick.decision.to_dict(),
            },
            indent=2,
        )
    )
    return 1 if tick.decision.error else 0


def request_from_scenario(
    scenario: JsonObject,
    *,
    provider: str,
    model: str,
    reasoning_effort: str,
) -> DirectorRequest:
    skills = scenario.get("enabledSkills")
    messages = scenario.get("messages")
    return DirectorRequest(
        goal=str(scenario.get("goal") or ""),
        model=model,
        provider=provider,
        enabled_skills=tuple(item for item in skills if isinstance(item, dict))
        if isinstance(skills, list)
        else (),
        context=scenario.get("context") if isinstance(scenario.get("context"), dict) else {},
        messages=tuple(item for item in messages if isinstance(item, dict))
        if isinstance(messages, list)
        else (),
        tick=int(scenario.get("tick") or 0),
        reasoning_effort=reasoning_effort,
        temperature=0.0,
        runtime_instructions=(
            "This is a frozen provider-comparison scenario; do not change its chapter or skills.",
        ),
        metadata={
            "checkpoint": {
                "kind": "frozen_scenario",
                "scenarioId": scenario.get("id"),
                "actionStarted": False,
            }
        },
    )


def semantic_registry_hash(scenario: JsonObject) -> str:
    return canonical_json_hash(scenario.get("enabledSkills") or [])


def canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_object(path: Path) -> JsonObject:
    parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
