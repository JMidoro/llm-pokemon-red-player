from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


SkillStatus = Literal["succeeded", "failed", "blocked", "uncertain"]


@dataclass(frozen=True)
class SkillResult:
    skill_id: str
    status: SkillStatus
    summary: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "skill_id": self.skill_id,
            "status": self.status,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "warnings": list(self.warnings),
        }
