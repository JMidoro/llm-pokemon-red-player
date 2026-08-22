from __future__ import annotations

import json
from pathlib import Path

from scripts import run_milestone_5_qualification as qualification


def write_summary(root: Path, case_id: str, status: str) -> None:
    path = root / case_id / "case-summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": status}), encoding="utf-8")


def test_case_disposition_only_resumes_completed_or_exact_infrastructure_case() -> None:
    assert qualification.case_disposition(
        {}, case_id="case-1", restart_case=None
    ) == "pending"
    assert qualification.case_disposition(
        {"status": "completed"}, case_id="case-1", restart_case=None
    ) == "completed"
    assert qualification.case_disposition(
        {"status": "infrastructure_abort"},
        case_id="case-1",
        restart_case=None,
    ) == "infrastructure_abort"
    assert qualification.case_disposition(
        {"status": "infrastructure_abort"},
        case_id="case-1",
        restart_case="case-1",
    ) == "restart"
    assert qualification.case_disposition(
        {"status": "incomplete"}, case_id="case-1", restart_case=None
    ) == "invalid_terminal"


def test_completed_case_count_excludes_incomplete_and_infrastructure_artifacts(
    tmp_path: Path,
) -> None:
    paths = qualification.QualificationPaths(tmp_path)
    cases = [("capsuleA", "case-1"), ("capsuleA", "case-2"), ("capsuleA", "case-3")]
    write_summary(tmp_path, "case-1", "completed")
    write_summary(tmp_path, "case-2", "infrastructure_abort")
    write_summary(tmp_path, "case-3", "incomplete")

    assert qualification.completed_case_ids(paths, cases) == ["case-1"]
