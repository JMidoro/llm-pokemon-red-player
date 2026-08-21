from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA = "director_segment_run_v1"
REQUIRED_CONTEXT_FIELDS = (
    "scenarioId",
    "scenarioSha256",
    "semanticRegistrySha256",
)
FORBIDDEN_CREDENTIAL_KEYS = {
    "apikey",
    "apitoken",
    "authorization",
    "credential",
    "credentials",
    "lmstudiotoken",
    "openaikey",
    "openaiapikey",
    "password",
    "secret",
    "token",
}
SECRET_VALUE_PATTERNS = (
    re.compile(r"\b(?:sk-proj|sk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]{8,}"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the local/hosted Milestone 2 frozen provider gate."
    )
    parser.add_argument("--local", required=True)
    parser.add_argument("--hosted", required=True)
    args = parser.parse_args(argv)

    local = load_object(Path(args.local))
    hosted = load_object(Path(args.hosted))
    issues = verify_gate_pair(local, hosted)
    summary = {
        "gate": "milestone_2_provider_neutral_director",
        "passed": not issues,
        "localProvider": nested(local, "provider", "provider"),
        "hostedProvider": nested(hosted, "provider", "provider"),
        "schema": local.get("schema"),
        "scenarioId": nested(local, "context", "scenarioId"),
        "scenarioSha256": nested(local, "context", "scenarioSha256"),
        "semanticRegistrySha256": nested(
            local, "context", "semanticRegistrySha256"
        ),
        "issues": issues,
    }
    print(json.dumps(summary, indent=2))
    return 0 if not issues else 1


def verify_gate_pair(local: dict[str, Any], hosted: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for label, report in (("local", local), ("hosted", hosted)):
        issues.extend(verify_gate_report(label, report))

    if local.keys() != hosted.keys():
        issues.append("local and hosted reports do not share the same top-level schema")
    for field in REQUIRED_CONTEXT_FIELDS:
        local_value = nested(local, "context", field)
        hosted_value = nested(hosted, "context", field)
        if local_value != hosted_value:
            issues.append(f"local and hosted {field} values differ")
    local_skills = request_enabled_skills(local)
    hosted_skills = request_enabled_skills(hosted)
    if local_skills != hosted_skills:
        issues.append("local and hosted semantic skill registries differ")
    if decision_signature(local) != decision_signature(hosted):
        issues.append("local and hosted normalized semantic decisions differ")
    if nested(local, "provider", "provider") != "lmstudio-chat":
        issues.append("local report was not produced by lmstudio-chat")
    if nested(hosted, "provider", "provider") != "openai-responses":
        issues.append("hosted report was not produced by openai-responses")
    return issues


def verify_gate_report(label: str, report: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if report.get("schema") != EXPECTED_SCHEMA:
        issues.append(f"{label} report does not use {EXPECTED_SCHEMA}")
    if report.get("status") == "error":
        issues.append(f"{label} provider gate ended in error")
    context = report.get("context") if isinstance(report.get("context"), dict) else {}
    for field in REQUIRED_CONTEXT_FIELDS:
        if not context.get(field):
            issues.append(f"{label} report is missing context.{field}")
    if context.get("emulatorExecutionEnabled") is not False:
        issues.append(f"{label} gate did not explicitly disable emulator execution")
    finish = report.get("finish") if isinstance(report.get("finish"), dict) else {}
    if finish.get("actionStarted") is not False:
        issues.append(f"{label} gate does not prove actionStarted=false")
    ticks = report.get("ticks") if isinstance(report.get("ticks"), list) else []
    if len(ticks) != 1 or not isinstance(ticks[0], dict):
        issues.append(f"{label} gate must contain exactly one canonical tick")
    else:
        decision = ticks[0].get("decision")
        decision = decision if isinstance(decision, dict) else {}
        if decision.get("error") is not None:
            issues.append(f"{label} decision contains a normalized provider error")
        tool_call = decision.get("toolCall")
        if not isinstance(tool_call, dict) or not tool_call.get("name"):
            issues.append(f"{label} decision contains no normalized tool call")
    issues.extend(credential_issues(label, report))
    return issues


def credential_issues(label: str, report: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if normalized in FORBIDDEN_CREDENTIAL_KEYS:
                    issues.append(f"{label} report contains credential-like field {path}.{key}")
                visit(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(report, label)
    serialized = json.dumps(report, sort_keys=True)
    if any(pattern.search(serialized) for pattern in SECRET_VALUE_PATTERNS):
        issues.append(f"{label} report contains a credential-like value")
    return issues


def request_enabled_skills(report: dict[str, Any]) -> list[str] | None:
    requests = report.get("requests") if isinstance(report.get("requests"), list) else []
    if len(requests) != 1 or not isinstance(requests[0], dict):
        return None
    skills = requests[0].get("enabledSkills")
    return [str(item) for item in skills] if isinstance(skills, list) else None


def decision_signature(report: dict[str, Any]) -> tuple[Any, Any, Any] | None:
    ticks = report.get("ticks") if isinstance(report.get("ticks"), list) else []
    if len(ticks) != 1 or not isinstance(ticks[0], dict):
        return None
    decision = ticks[0].get("decision")
    decision = decision if isinstance(decision, dict) else {}
    call = decision.get("toolCall")
    if not isinstance(call, dict):
        return None
    arguments = call.get("arguments")
    arguments = arguments if isinstance(arguments, dict) else {}
    return (call.get("name"), arguments.get("skillId"), arguments.get("args"))


def nested(value: dict[str, Any], key: str, nested_key: str) -> Any:
    item = value.get(key)
    return item.get(nested_key) if isinstance(item, dict) else None


def load_object(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
