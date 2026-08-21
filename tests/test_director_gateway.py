from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pokemon_player.director_providers import ReplayAdapter
from pokemon_player import director_gateway


ROOT = Path(__file__).resolve().parents[1]


class FakeSidecar:
    instances: list[FakeSidecar] = []

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.execute_calls: list[tuple[str, dict[str, Any]]] = []
        self.instances.append(self)

    def status(self, *, fresh: bool) -> dict[str, Any]:
        del fresh
        last_result = None
        if self.execute_calls:
            skill_id, args = self.execute_calls[-1]
            last_result = {
                "skillId": skill_id,
                "args": args,
                "status": "succeeded",
                "summary": "Navigation completed.",
            }
        return {
            "busy": False,
            "snapshotHash": "frozen-hash",
            "session": {"id": "session-test"},
            "snapshot": {
                "mode": "overworld",
                "position": {"map_name": "Viridian City"},
            },
            "signals": [],
            "skills": [
                {
                    "id": "navigate_within_viridian_forest_region",
                    "label": "Navigate",
                    "enabled": True,
                    "params": {"targets": ["forest_grass"]},
                }
            ],
            "lastResult": last_result,
            "history": [],
        }

    def execute_skill(self, skill_id: str, args: dict[str, Any]) -> dict[str, Any]:
        self.execute_calls.append((skill_id, args))
        return self.status(fresh=True)


def make_repo(tmp_path: Path) -> Path:
    capsule_dir = tmp_path / "research" / "capsules"
    capsule_dir.mkdir(parents=True)
    (capsule_dir / "viridian_forest_catching.json").write_text(
        json.dumps(
            {
                "id": "capsule-a",
                "name": "Capsule A",
                "objective": "Catch an allowed encounter.",
                "success_conditions": [],
                "failure_conditions": [],
                "abort_conditions": [],
                "budgets": {},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def successful_replay() -> ReplayAdapter:
    return ReplayAdapter(
        [
            {
                "toolCall": {
                    "name": "execute_skill",
                    "arguments": {
                        "skillId": "navigate_within_viridian_forest_region",
                        "args": {"target": "forest_grass"},
                        "plaintextReasoning": "Direct progress.",
                    },
                }
            }
        ]
    )


def test_browser_gateway_uses_canonical_runtime_and_executes_one_skill(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeSidecar.instances.clear()
    monkeypatch.setattr(director_gateway, "DirectorPlayerHttpClient", FakeSidecar)
    monkeypatch.setattr(director_gateway, "make_provider", lambda *args, **kwargs: successful_replay())

    result = director_gateway.run_browser_director_tick(
        {
            "goal": "Reach forest grass.",
            "provider": "replay",
            "model": "deterministic-replay",
            "tick": 1,
        },
        repo_root=make_repo(tmp_path),
    )

    assert result["schema"] == "director_segment_run_v1"
    assert result["provider"]["provider"] == "replay"
    assert result["requestSummary"]["enabledSkills"] == [
        "navigate_within_viridian_forest_region"
    ]
    assert len(FakeSidecar.instances[0].execute_calls) == 1
    assert Path(result["reportPath"]).is_file()


def test_browser_provider_failure_never_reaches_sidecar_skill_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeSidecar.instances.clear()
    failure = ReplayAdapter(
        [
            {
                "error": {
                    "category": "provider_unavailable",
                    "message": "Hosted provider is unavailable.",
                    "retryable": False,
                }
            }
        ]
    )
    monkeypatch.setattr(director_gateway, "DirectorPlayerHttpClient", FakeSidecar)
    monkeypatch.setattr(director_gateway, "make_provider", lambda *args, **kwargs: failure)

    result = director_gateway.run_browser_director_tick(
        {
            "goal": "Reach forest grass.",
            "provider": "replay",
            "model": "deterministic-replay",
            "tick": 1,
        },
        repo_root=make_repo(tmp_path),
    )

    assert result["status"] == "error"
    assert result["finish"]["failureCategory"] == "provider_unavailable"
    assert result["finish"]["actionStarted"] is False
    assert FakeSidecar.instances[0].execute_calls == []


def test_browser_executor_failure_reports_unknown_action_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeSidecar.instances.clear()

    def fail_after_invocation(
        sidecar: FakeSidecar, skill_id: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        sidecar.execute_calls.append((skill_id, args))
        raise RuntimeError("sidecar response was lost")

    monkeypatch.setattr(FakeSidecar, "execute_skill", fail_after_invocation)
    monkeypatch.setattr(director_gateway, "DirectorPlayerHttpClient", FakeSidecar)
    monkeypatch.setattr(
        director_gateway, "make_provider", lambda *args, **kwargs: successful_replay()
    )

    result = director_gateway.run_browser_director_tick(
        {
            "goal": "Reach forest grass.",
            "provider": "replay",
            "model": "deterministic-replay",
        },
        repo_root=make_repo(tmp_path),
    )

    assert result["status"] == "error"
    assert result["finish"]["failureCategory"] == "execution_error"
    assert result["finish"]["actionStarted"] is None
    assert result["finish"]["actionStateKnown"] is False
    assert result["finish"]["requiresCheckpointReconciliation"] is True
    assert result["errors"][0]["category"] == "execution_error"
    assert len(FakeSidecar.instances[0].execute_calls) == 1


def test_browser_payload_cannot_override_configured_sidecar_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    FakeSidecar.instances.clear()
    monkeypatch.delenv("DIRECTOR_PLAYER_URL", raising=False)
    monkeypatch.setattr(director_gateway, "DirectorPlayerHttpClient", FakeSidecar)
    monkeypatch.setattr(
        director_gateway,
        "make_provider",
        lambda *args, **kwargs: successful_replay(),
    )

    director_gateway.run_browser_director_tick(
        {
            "goal": "Reach forest grass.",
            "provider": "replay",
            "model": "deterministic-replay",
            "directorPlayerUrl": "http://untrusted.invalid:9999",
        },
        repo_root=make_repo(tmp_path),
    )

    assert FakeSidecar.instances[0].base_url == director_gateway.DEFAULT_DIRECTOR_PLAYER_URL


def test_browser_history_is_count_and_size_bounded_in_python() -> None:
    messages = [
        {"role": "user", "content": "x" * 20_000, "kind": "steering"}
        for _ in range(30)
    ]

    sanitized = director_gateway.sanitize_messages(messages, 5, "fallback")

    assert len(sanitized) == 5
    assert all(len(str(message["content"])) == 8_000 for message in sanitized)


def test_typescript_llm_player_route_is_only_a_canonical_runtime_client() -> None:
    source = (ROOT / "apps" / "lab-ui" / "app" / "api" / "llm-player" / "route.ts").read_text(
        encoding="utf-8"
    )

    assert "scripts\", \"run_director_tick.py" in source
    assert len(source.splitlines()) < 180
    for forbidden in (
        "chat/completions",
        '"/responses"',
        "OPENAI_API_KEY",
        "LM_API_TOKEN",
        "tool_choice",
        "plaintextReasoning",
    ):
        assert forbidden not in source
