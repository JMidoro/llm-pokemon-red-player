from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


CAPSULE_SCHEMA = "scenario_capsule_v1"
CAPSULE_MANIFEST_SCHEMA = "scenario_capsule_manifest_v1"


@dataclass(frozen=True)
class CapsuleValidationIssue:
    capsule_id: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class StateRecord:
    state_id: str
    source: str
    status: str
    metadata_path: str
    state_path: str | None
    snapshot_hash: str
    snapshot: dict[str, Any]
    capsule_id: str | None = None
    variant_kind: str | None = None

    @property
    def usable_for_capsule(self) -> bool:
        if self.source == "golden":
            return self.status == "human_verified"
        if self.source == "generated":
            return self.status == "approved"
        return False


def validate_capsule_spec(spec: dict[str, Any]) -> list[CapsuleValidationIssue]:
    capsule_id = str(spec.get("id", "<missing>"))
    issues: list[CapsuleValidationIssue] = []

    required = [
        "schema",
        "id",
        "name",
        "objective",
        "base_state_ids",
        "start_state_policy",
        "allowed_randomization",
        "valid_start_requirements",
        "success_conditions",
        "failure_conditions",
        "abort_conditions",
        "budgets",
        "required_logged_events",
        "relevant_state_fields",
    ]
    for key in required:
        if key not in spec:
            issues.append(CapsuleValidationIssue(capsule_id, f"Missing required field {key!r}."))

    if spec.get("schema") != CAPSULE_SCHEMA:
        issues.append(
            CapsuleValidationIssue(
                capsule_id,
                f"Unexpected schema {spec.get('schema')!r}; expected {CAPSULE_SCHEMA}.",
            )
        )

    base_state_ids = spec.get("base_state_ids", [])
    if not isinstance(base_state_ids, list) or not base_state_ids:
        issues.append(CapsuleValidationIssue(capsule_id, "base_state_ids must be a non-empty list."))

    budgets = spec.get("budgets", {})
    for key in ("max_button_actions", "max_emulator_frames"):
        value = budgets.get(key)
        if not isinstance(value, int) or value <= 0:
            issues.append(CapsuleValidationIssue(capsule_id, f"budgets.{key} must be positive."))

    split = spec.get("start_state_policy", {}).get("split", {})
    tuning = split.get("tuning")
    holdout = split.get("holdout")
    if not isinstance(tuning, int | float) or not isinstance(holdout, int | float):
        issues.append(CapsuleValidationIssue(capsule_id, "start_state_policy.split needs tuning and holdout ratios."))
    elif abs((float(tuning) + float(holdout)) - 1.0) > 0.001:
        issues.append(CapsuleValidationIssue(capsule_id, "tuning and holdout split ratios must sum to 1.0."))

    for list_key in (
        "valid_start_requirements",
        "success_conditions",
        "failure_conditions",
        "abort_conditions",
        "required_logged_events",
        "relevant_state_fields",
    ):
        value = spec.get(list_key)
        if not isinstance(value, list) or not value:
            issues.append(CapsuleValidationIssue(capsule_id, f"{list_key} must be a non-empty list."))

    return issues


def assign_split(
    *,
    capsule_id: str,
    state_ids: list[str],
    seed: str,
    holdout_ratio: float,
) -> dict[str, str]:
    if not state_ids:
        return {}
    ranked = sorted(state_ids, key=lambda state_id: split_key(seed, capsule_id, state_id))
    holdout_count = max(1, round(len(ranked) * holdout_ratio)) if len(ranked) > 1 else 0
    holdout_ids = set(ranked[:holdout_count])
    return {
        state_id: "holdout" if state_id in holdout_ids else "tuning"
        for state_id in sorted(state_ids)
    }


def split_key(seed: str, capsule_id: str, state_id: str) -> str:
    raw = f"{seed}:{capsule_id}:{state_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
