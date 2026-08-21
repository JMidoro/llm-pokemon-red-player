from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pokemon_player.durable_io import utc_now
from pokemon_player.segment_supervisor import SegmentExecution, SegmentRequest


@dataclass
class FixtureSegmentRunner:
    project_root: Path
    operations_dir: Path
    outcome: str = "healthy"
    duration_seconds: float = 30.0
    action_seconds: float = 0.25
    provider_healthy: bool = True
    poll_seconds: float = 0.1

    def run(
        self,
        request: SegmentRequest,
        *,
        on_started: Callable[[int | None], None],
        on_poll: Callable[[], None],
    ) -> SegmentExecution:
        stdout_path = request.segment_dir.parent / f".{request.segment_id}.stdout.log"
        stderr_path = request.segment_dir.parent / f".{request.segment_id}.stderr.log"
        command = [
            sys.executable,
            str(self.project_root / "scripts" / "supervisor_fixture_segment.py"),
            "--run-root",
            str(request.segment_dir.parent),
            "--run-id",
            request.segment_id,
            "--state-in",
            str(request.input_state),
            "--operations-dir",
            str(self.operations_dir),
            "--duration-seconds",
            str(self.duration_seconds),
            "--action-seconds",
            str(self.action_seconds),
            "--outcome",
            self.outcome,
        ]
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            process = subprocess.Popen(
                command,
                cwd=self.project_root,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                creationflags=creation_flags,
                start_new_session=os.name != "nt",
            )
            on_started(process.pid)
            while process.poll() is None:
                on_poll()
                time.sleep(max(self.poll_seconds, 0.02))
        return SegmentExecution(
            report_path=request.report_path,
            return_code=int(process.returncode or 0),
            child_pid=process.pid,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    def health_check(self) -> dict[str, Any]:
        return {
            "schema": "provider_health_v1",
            "provider": "fixture",
            "healthy": self.provider_healthy,
            "checkedUtc": utc_now(),
            "detail": "Injected deterministic fixture health result.",
        }
