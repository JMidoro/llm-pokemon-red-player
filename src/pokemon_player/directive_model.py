from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class DirectiveCategory(StrEnum):
    STRATEGIC = "strategic"
    COSMETIC = "cosmetic"
    CONSTRAINT = "constraint"
    PLAYFUL = "playful"
    AMBIGUOUS = "ambiguous"
    IMPOSSIBLE = "impossible"
    DESTRUCTIVE = "destructive"
    DERAILING = "derailing"


class DirectiveRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DirectiveDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"
    REINTERPRET = "reinterpret"
    ASK_CLARIFICATION = "ask_clarification"


@dataclass(frozen=True)
class DirectorContext:
    state_summary: str
    objective: str
    safety_rules: tuple[str, ...] = ()
    allowed_fun: tuple[str, ...] = ()


@dataclass(frozen=True)
class DirectorDecision:
    directive: str
    category: DirectiveCategory
    risk: DirectiveRisk
    decision: DirectiveDecision
    explanation: str
    bounded_goal: str | None = None
    constraints: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    raw_model_output: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["category"] = self.category.value
        raw["risk"] = self.risk.value
        raw["decision"] = self.decision.value
        return raw

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, directive: str) -> "DirectorDecision":
        return cls(
            directive=directive,
            category=DirectiveCategory(raw["category"]),
            risk=DirectiveRisk(raw["risk"]),
            decision=DirectiveDecision(raw["decision"]),
            explanation=str(raw["explanation"]),
            bounded_goal=raw.get("bounded_goal"),
            constraints=tuple(raw.get("constraints", ())),
            warnings=tuple(raw.get("warnings", ())),
            raw_model_output=dict(raw),
        )


DIRECTOR_DECISION_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "category": {"type": "string", "enum": [item.value for item in DirectiveCategory]},
        "risk": {"type": "string", "enum": [item.value for item in DirectiveRisk]},
        "decision": {"type": "string", "enum": [item.value for item in DirectiveDecision]},
        "explanation": {"type": "string"},
        "bounded_goal": {"type": ["string", "null"]},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "category",
        "risk",
        "decision",
        "explanation",
        "bounded_goal",
        "constraints",
        "warnings",
    ],
}

