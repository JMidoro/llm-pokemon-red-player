from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_milestone_5_case as case_runner


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_completed_case_is_immutable_except_for_infrastructure_restart(
    tmp_path: Path,
) -> None:
    case_root = tmp_path / "qualification" / "capsule-a-01"
    write_json(
        case_root / "case-summary.json",
        {"status": "completed", "success": False},
    )

    restart, error = case_runner.existing_case_disposition(
        case_root, restart_infrastructure_abort=False
    )

    assert restart is False
    assert error and error["status"] == "case_already_finished"

    write_json(
        case_root / "case-summary.json",
        {"status": "infrastructure_abort", "success": False},
    )
    restart, error = case_runner.existing_case_disposition(
        case_root, restart_infrastructure_abort=True
    )
    assert restart is True
    assert error is None


def test_infrastructure_restart_archives_evidence_instead_of_deleting_it(
    tmp_path: Path,
) -> None:
    results_root = tmp_path / "qualification"
    case_root = results_root / "capsule-a-01"
    evidence = case_root / "case-summary.json"
    write_json(evidence, {"status": "infrastructure_abort"})

    archived = case_runner.archive_infrastructure_abort(case_root, results_root)

    assert not case_root.exists()
    assert (archived / "case-summary.json").is_file()
    assert archived.parent == results_root / "aborted-attempts"


def test_repository_file_falls_back_to_shared_worktree_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "worktree"
    common_root = tmp_path / "main"
    worktree.mkdir()
    (common_root / ".git").mkdir(parents=True)
    shared_file = common_root / ".env"
    shared_file.write_text("TOKEN=value", encoding="utf-8")

    monkeypatch.setattr(
        case_runner.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=str(common_root / ".git")
        ),
    )

    assert case_runner.resolve_repository_file(worktree, Path(".env")) == shared_file


def test_clean_commit_check_includes_untracked_source_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        del kwargs
        calls.append(command)
        return SimpleNamespace(stdout="?? src/uncommitted.py\n")

    monkeypatch.setattr(case_runner.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="clean worktree"):
        case_runner.clean_tested_commit(tmp_path)

    assert calls[0] == [
        "git",
        "status",
        "--porcelain",
        "--untracked-files=normal",
    ]


def test_runtime_dependency_preflight_reports_missing_packages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        case_runner.importlib.util,
        "find_spec",
        lambda module: None if module == "pyboy" else SimpleNamespace(),
    )

    assert case_runner.runtime_dependency_issues() == [
        "Python runtime is missing required package: pyboy"
    ]
