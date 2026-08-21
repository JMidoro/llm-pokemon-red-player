from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pokemon_player.durable_io import (
    artifact_record,
    atomic_write_json,
    read_json,
    require_safe_component,
    utc_now,
)
from pokemon_player.run_interrogation import interrogate_run_report


SUPERVISOR_STATES = {
    "idle",
    "starting",
    "running",
    "checkpointing",
    "waiting_review",
    "paused",
    "blocked",
    "completed",
    "failed",
}
ACTIVE_STATES = {"starting", "running", "checkpointing"}
CONTINUE_VERDICTS = {"healthy_continue"}
REVIEWABLE_VERDICTS = {
    "provisional_continue",
    "healthy_needs_review",
    "stalled_loop",
    "skill_gap",
    "state_interpretation_gap",
}


class LeaseBusyError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupervisorPaths:
    root: Path
    lineage_id: str

    def __post_init__(self) -> None:
        require_safe_component(self.lineage_id, label="lineage id")

    @property
    def lineage_root(self) -> Path:
        return self.root / "lineages" / self.lineage_id

    @property
    def state(self) -> Path:
        return self.lineage_root / "state.json"

    @property
    def heartbeat(self) -> Path:
        return self.lineage_root / "heartbeat.json"

    @property
    def lease_lock(self) -> Path:
        return self.lineage_root / "lease.lock"

    @property
    def lease_record(self) -> Path:
        return self.lineage_root / "lease.json"

    @property
    def manifest(self) -> Path:
        return self.lineage_root / "manifest.json"

    @property
    def final_checkpoint(self) -> Path:
        return self.lineage_root / "final-checkpoint.json"

    @property
    def operator_stop(self) -> Path:
        return self.lineage_root / "operator-stop.json"

    @property
    def segments(self) -> Path:
        return self.lineage_root / "segments"

    @property
    def reviews(self) -> Path:
        return self.lineage_root / "review-queue"

    @property
    def failures(self) -> Path:
        return self.lineage_root / "failures"

    @property
    def events(self) -> Path:
        return self.lineage_root / "events"


@dataclass(frozen=True)
class SegmentRequest:
    lineage_id: str
    segment_id: str
    sequence: int
    attempt: int
    input_state: Path
    segment_dir: Path

    @property
    def report_path(self) -> Path:
        return self.segment_dir / "report.json"


@dataclass(frozen=True)
class SegmentExecution:
    report_path: Path
    return_code: int
    child_pid: int | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None


class SegmentRunner(Protocol):
    def run(
        self,
        request: SegmentRequest,
        *,
        on_started: Callable[[int | None], None],
        on_poll: Callable[[], None],
    ) -> SegmentExecution: ...

    def health_check(self) -> dict[str, Any]: ...


@dataclass
class LineageLease:
    paths: SupervisorPaths
    owner_id: str
    ttl_seconds: float = 30.0
    _handle: Any = field(default=None, init=False, repr=False)
    _renew_lock: threading.RLock = field(
        default_factory=threading.RLock,
        init=False,
        repr=False,
    )

    def acquire(self) -> None:
        self.paths.lineage_root.mkdir(parents=True, exist_ok=True)
        handle = self.paths.lease_lock.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            _lock_file(handle)
        except OSError as exc:
            handle.close()
            current = read_json(self.paths.lease_record) or {}
            owner = current.get("ownerId") or "another supervisor"
            raise LeaseBusyError(
                f"Save lineage {self.paths.lineage_id} is leased by {owner}."
            ) from exc
        self._handle = handle
        self.renew(state="starting", current_segment=None)

    def renew(self, *, state: str, current_segment: str | None) -> None:
        with self._renew_lock:
            now = datetime.now(UTC)
            atomic_write_json(
                self.paths.lease_record,
                {
                    "schema": "segment_supervisor_lease_v1",
                    "lineageId": self.paths.lineage_id,
                    "ownerId": self.owner_id,
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "state": state,
                    "currentSegment": current_segment,
                    "renewedUtc": now.isoformat(),
                    "expiresUtc": (now + timedelta(seconds=self.ttl_seconds)).isoformat(),
                },
            )

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            _unlock_file(self._handle)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> LineageLease:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


@dataclass
class SubprocessSegmentRunner:
    project_root: Path
    provider: str
    model: str | None = None
    base_url: str | None = None
    replay_path: Path | None = None
    goal: str | None = None
    max_actions: int = 100
    max_tokens: int = 2048
    reasoning_effort: str = "low"
    request_timeout_seconds: int = 180
    no_image: bool = False
    no_video: bool = False
    video_output_dir: Path | None = None
    operations_dir: Path | None = None
    extra_args: tuple[str, ...] = ()
    poll_seconds: float = 0.5

    def run(
        self,
        request: SegmentRequest,
        *,
        on_started: Callable[[int | None], None],
        on_poll: Callable[[], None],
    ) -> SegmentExecution:
        request.segment_dir.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = request.segment_dir.parent / f".{request.segment_id}.stdout.log"
        stderr_path = request.segment_dir.parent / f".{request.segment_id}.stderr.log"
        command = self._command(request)
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
            )
            on_started(process.pid)
            while process.poll() is None:
                on_poll()
                time.sleep(max(self.poll_seconds, 0.05))
            return_code = int(process.returncode or 0)
        return SegmentExecution(
            report_path=request.report_path,
            return_code=return_code,
            child_pid=process.pid,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )

    def health_check(self) -> dict[str, Any]:
        if self.provider == "replay":
            return {
                "schema": "provider_health_v1",
                "healthy": True,
                "provider": self.provider,
                "checkedUtc": utc_now(),
                "detail": "Deterministic replay provider is locally available.",
            }
        base = self.base_url
        if not base:
            base = (
                os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
                if self.provider == "lmstudio-chat"
                else os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            )
        endpoint = base.rstrip("/") + "/models"
        headers = {"Accept": "application/json"}
        token = None
        if self.provider == "openai-responses":
            token = os.environ.get("OPENAI_API_KEY")
        elif self.provider == "lmstudio-chat":
            token = os.environ.get("LM_API_TOKEN") or os.environ.get("LMSTUDIO_API_KEY")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(endpoint, headers=headers)
        try:
            with urlopen(request, timeout=min(self.request_timeout_seconds, 10)) as response:
                healthy = 200 <= int(response.status) < 300
            detail = "Provider endpoint responded." if healthy else "Provider endpoint was not ready."
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            healthy = False
            detail = f"Provider health check failed: {exc.__class__.__name__}."
        return {
            "schema": "provider_health_v1",
            "healthy": healthy,
            "provider": self.provider,
            "checkedUtc": utc_now(),
            "detail": detail,
        }

    def _command(self, request: SegmentRequest) -> list[str]:
        command = [
            sys.executable,
            str(self.project_root / "scripts" / "run_chapter_segment.py"),
            "--provider",
            self.provider,
            "--state-in",
            str(request.input_state),
            "--run-root",
            str(request.segment_dir.parent),
            "--run-id",
            request.segment_id,
            "--max-actions",
            str(self.max_actions),
            "--max-tokens",
            str(self.max_tokens),
            "--reasoning-effort",
            self.reasoning_effort,
            "--request-timeout-seconds",
            str(self.request_timeout_seconds),
        ]
        if self.model:
            command.extend(("--model", self.model))
        if self.base_url:
            command.extend(("--base-url", self.base_url))
        if self.replay_path:
            command.extend(("--replay-path", str(self.replay_path)))
        if self.goal:
            command.extend(("--goal", self.goal))
        if self.no_image:
            command.append("--no-image")
        if self.no_video:
            command.append("--no-video")
        if self.video_output_dir:
            command.extend(("--video-output-dir", str(self.video_output_dir)))
        if self.operations_dir:
            command.extend(("--operations-dir", str(self.operations_dir)))
        command.extend(self.extra_args)
        return command


@dataclass
class SupervisorConfig:
    paths: SupervisorPaths
    initial_state: Path | None = None
    operations_control_path: Path | None = None
    allow_provisional_continue: bool = True
    heartbeat_seconds: float = 5.0
    lease_ttl_seconds: float = 30.0
    min_free_bytes: int = 1024 * 1024 * 1024
    max_segments: int | None = None
    adopt_poll_seconds: float = 0.25


class DurableSegmentSupervisor:
    def __init__(self, config: SupervisorConfig, runner: SegmentRunner) -> None:
        self.config = config
        self.paths = config.paths
        self.runner = runner
        self.owner_id = uuid.uuid4().hex
        self.lease = LineageLease(
            self.paths,
            self.owner_id,
            ttl_seconds=config.lease_ttl_seconds,
        )
        self._state_lock = threading.RLock()
        self._heartbeat_write_lock = threading.RLock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def run(self) -> dict[str, Any]:
        with self.lease:
            self._ensure_layout()
            self._start_heartbeat()
            try:
                recovered = self._recover_interrupted_segment()
                if recovered:
                    outcome = self._apply_checkpoint_policy(recovered)
                    if outcome != "continue":
                        return self._stop_result()
                return self._run_loop()
            except Exception as exc:
                self._record_event(
                    "supervisor_exception",
                    {"errorType": exc.__class__.__name__, "summary": str(exc)[:500]},
                )
                self._transition("failed", reason="supervisor_exception")
                self._write_final_checkpoint("supervisor_exception")
                raise
            finally:
                self._stop_heartbeat()

    def _run_loop(self) -> dict[str, Any]:
        while True:
            control = self._control_signal()
            if control == "pause":
                self._transition("paused", reason="operator_pause")
                while self._control_signal() == "pause":
                    self._heartbeat_once()
                    time.sleep(max(self.config.adopt_poll_seconds, 0.05))
                self._transition("idle", reason="operator_resumed")
                continue
            if control in {"emergency_stop", "stop_after_action"}:
                self._transition("paused", reason=f"operator_{control}")
                self._write_final_checkpoint(f"operator_{control}")
                return self._stop_result()
            if not self._disk_ready():
                self._transition("failed", reason="insufficient_disk_space")
                self._write_final_checkpoint("insufficient_disk_space")
                return self._stop_result()

            manifest = self._manifest()
            completed_count = len(manifest.get("segments", []))
            if self.config.max_segments is not None and completed_count >= self.config.max_segments:
                self._transition("completed", reason="segment_limit_reached")
                self._write_final_checkpoint("segment_limit_reached")
                return self._stop_result()

            sequence = int(manifest.get("nextSequence") or 1)
            input_state = self._last_safe_state(manifest)
            if input_state is None or not input_state.is_file():
                self._transition("failed", reason="missing_safe_input_state")
                self._write_final_checkpoint("missing_safe_input_state")
                return self._stop_result()

            segment = self._execute_segment(sequence, 1, input_state)
            outcome = self._apply_checkpoint_policy(segment)
            if outcome == "retry_model":
                segment = self._execute_segment(sequence, 2, input_state)
                outcome = self._apply_checkpoint_policy(segment)
            if outcome != "continue":
                return self._stop_result()

    def _execute_segment(
        self,
        sequence: int,
        attempt: int,
        input_state: Path,
    ) -> dict[str, Any]:
        segment_id = f"segment-{sequence:06d}-a{attempt}"
        segment_dir = self.paths.segments / segment_id
        request = SegmentRequest(
            lineage_id=self.paths.lineage_id,
            segment_id=segment_id,
            sequence=sequence,
            attempt=attempt,
            input_state=input_state.resolve(),
            segment_dir=segment_dir,
        )
        registration = {
            "schema": "segment_artifact_manifest_v1",
            "lineageId": self.paths.lineage_id,
            "segmentId": segment_id,
            "sequence": sequence,
            "attempt": attempt,
            "status": "registered",
            "registeredUtc": utc_now(),
            "inputState": str(input_state.resolve()),
            "childPid": None,
            "childStartedEpoch": None,
            "artifacts": {},
        }
        segment_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(segment_dir / "manifest.json", registration)
        self._transition("starting", reason="segment_registered", current_segment=segment_id)

        child_started_epoch: float | None = None

        def on_started(pid: int | None) -> None:
            nonlocal child_started_epoch
            child_started_epoch = _process_started_epoch(pid) if pid else None
            current = read_json(segment_dir / "manifest.json") or registration
            current.update(
                {
                    "status": "running",
                    "startedUtc": utc_now(),
                    "childPid": pid,
                    "childStartedEpoch": child_started_epoch,
                }
            )
            atomic_write_json(segment_dir / "manifest.json", current)
            self._transition(
                "running",
                reason="segment_process_started",
                current_segment=segment_id,
                child_pid=pid,
                child_started_epoch=child_started_epoch,
            )

        execution = self.runner.run(
            request,
            on_started=on_started,
            on_poll=self._heartbeat_once,
        )
        self._transition(
            "checkpointing",
            reason="segment_process_exited",
            current_segment=segment_id,
            child_pid=execution.child_pid,
            child_started_epoch=child_started_epoch,
        )
        return self._finalize_segment(request, execution)

    def _finalize_segment(
        self,
        request: SegmentRequest,
        execution: SegmentExecution,
    ) -> dict[str, Any]:
        report = read_json(execution.report_path)
        if report is None:
            return self._finalize_missing_report(request, execution)
        previous_report = self._previous_report()
        checkpoint = interrogate_run_report(report, previous_report=previous_report)
        report["checkpoint"] = checkpoint
        atomic_write_json(request.segment_dir / "checkpoint.json", checkpoint)
        atomic_write_json(execution.report_path, report)
        video_path = self._bundle_video(request.segment_dir, report)
        artifacts = self._artifact_manifest(
            request.segment_dir,
            report,
            execution,
            video_path=video_path,
        )
        finish = report.get("finish") if isinstance(report.get("finish"), dict) else {}
        manifest = read_json(request.segment_dir / "manifest.json") or {}
        manifest.update(
            {
                "status": "checkpointed",
                "completedUtc": utc_now(),
                "returnCode": execution.return_code,
                "finish": finish,
                "checkpoint": checkpoint,
                "artifacts": artifacts,
                "diagnostic": self._diagnostic_summary(report, checkpoint, artifacts),
            }
        )
        atomic_write_json(request.segment_dir / "manifest.json", manifest)
        self._register_segment(manifest)
        return manifest

    def _finalize_missing_report(
        self,
        request: SegmentRequest,
        execution: SegmentExecution,
    ) -> dict[str, Any]:
        checkpoint = {
            "schema": "checkpoint_interrogation_v1",
            "verdict": "supervisor_error",
            "confidence": "high",
            "continueRecommended": False,
            "summary": "Segment process exited without a stable report; the prior safe state was preserved.",
            "evidence": [
                f"return_code={execution.return_code}",
                "report_exists=false",
                "rollback=previous_safe_state",
            ],
            "reviewItems": [],
            "fallbackTaken": ["preserve_previous_safe_state"],
        }
        atomic_write_json(request.segment_dir / "checkpoint.json", checkpoint)
        artifacts = self._artifact_manifest(
            request.segment_dir,
            {},
            execution,
            video_path=None,
        )
        manifest = read_json(request.segment_dir / "manifest.json") or {}
        manifest.update(
            {
                "status": "failed",
                "completedUtc": utc_now(),
                "returnCode": execution.return_code,
                "finish": {
                    "status": "failed",
                    "failureCategory": "segment_report_missing",
                    "stopReason": "segment_process_exit",
                },
                "checkpoint": checkpoint,
                "artifacts": artifacts,
                "diagnostic": {
                    "needsDiagnosis": True,
                    "diagnosable": True,
                    "reason": "return code and captured process logs identify the missing report",
                },
            }
        )
        atomic_write_json(request.segment_dir / "manifest.json", manifest)
        self._register_segment(manifest)
        return manifest

    def _apply_checkpoint_policy(self, segment: dict[str, Any]) -> str:
        checkpoint = segment.get("checkpoint") if isinstance(segment.get("checkpoint"), dict) else {}
        finish = segment.get("finish") if isinstance(segment.get("finish"), dict) else {}
        verdict = str(checkpoint.get("verdict") or "supervisor_error")
        stop_reason = str(finish.get("stopReason") or "")

        if stop_reason in {"operator_stop_after_action", "operator_emergency_stop"}:
            if self._segment_has_safe_state(segment):
                self._promote_safe_state(segment)
            self._transition("paused", reason=stop_reason)
            self._write_final_checkpoint(stop_reason, segment=segment)
            return "stop"
        if finish.get("success") is True:
            if self._segment_has_safe_state(segment):
                self._promote_safe_state(segment)
            self._transition("completed", reason="chapter_success")
            self._write_final_checkpoint("chapter_success", segment=segment)
            return "stop"
        if verdict in CONTINUE_VERDICTS:
            if not self._segment_has_safe_state(segment):
                self._quarantine_failure(segment)
                self._transition("failed", reason="missing_final_safe_state")
                self._write_final_checkpoint("missing_final_safe_state", segment=segment)
                return "stop"
            self._promote_safe_state(segment)
            self._advance_sequence(segment)
            return "continue"
        if verdict == "provisional_continue" or (
            verdict == "healthy_needs_review" and checkpoint.get("continueRecommended") is True
        ):
            self._queue_review(segment)
            if self.config.allow_provisional_continue and self._segment_has_safe_state(segment):
                self._promote_safe_state(segment)
                self._advance_sequence(segment)
                return "continue"
            self._transition("waiting_review", reason=verdict)
            self._write_final_checkpoint(verdict, segment=segment)
            return "stop"
        if verdict == "model_error" and int(segment.get("attempt") or 1) == 1:
            health = self.runner.health_check()
            segment["providerHealth"] = health
            atomic_write_json(
                self.paths.segments / str(segment["segmentId"]) / "manifest.json",
                segment,
            )
            if health.get("healthy") is True:
                self._record_event("model_retry_authorized", {"segmentId": segment["segmentId"]})
                return "retry_model"
        if verdict in REVIEWABLE_VERDICTS:
            self._queue_review(segment)
        self._quarantine_failure(segment)
        state = "blocked" if verdict != "supervisor_error" else "failed"
        self._transition(state, reason=verdict)
        self._write_final_checkpoint(verdict, segment=segment)
        return "stop"

    def _register_segment(self, segment: dict[str, Any]) -> None:
        manifest = self._manifest()
        summaries = [
            item
            for item in manifest.get("segments", [])
            if isinstance(item, dict) and item.get("segmentId") != segment.get("segmentId")
        ]
        summaries.append(
            {
                "segmentId": segment.get("segmentId"),
                "sequence": segment.get("sequence"),
                "attempt": segment.get("attempt"),
                "status": segment.get("status"),
                "completedUtc": segment.get("completedUtc"),
                "verdict": (segment.get("checkpoint") or {}).get("verdict"),
                "manifestPath": f"segments/{segment.get('segmentId')}/manifest.json",
                "diagnosable": (segment.get("diagnostic") or {}).get("diagnosable"),
            }
        )
        manifest["segments"] = sorted(
            summaries,
            key=lambda item: (int(item.get("sequence") or 0), int(item.get("attempt") or 0)),
        )
        manifest["updatedUtc"] = utc_now()
        atomic_write_json(self.paths.manifest, manifest)

    def _advance_sequence(self, segment: dict[str, Any]) -> None:
        manifest = self._manifest()
        manifest["nextSequence"] = max(
            int(manifest.get("nextSequence") or 1),
            int(segment.get("sequence") or 0) + 1,
        )
        manifest["updatedUtc"] = utc_now()
        atomic_write_json(self.paths.manifest, manifest)
        self._transition("idle", reason="continuation_approved", current_segment=None)

    def _promote_safe_state(self, segment: dict[str, Any]) -> None:
        artifact = (segment.get("artifacts") or {}).get("finalState") or {}
        relative = artifact.get("relativePath")
        if not relative:
            return
        path = self.paths.lineage_root / str(relative)
        if not path.is_file():
            return
        manifest = self._manifest()
        manifest["lastSafeState"] = {
            "path": str(path.resolve()),
            "sha256": artifact.get("sha256"),
            "segmentId": segment.get("segmentId"),
            "updatedUtc": utc_now(),
        }
        manifest["updatedUtc"] = utc_now()
        atomic_write_json(self.paths.manifest, manifest)

    def _segment_has_safe_state(self, segment: dict[str, Any]) -> bool:
        final_state = (segment.get("artifacts") or {}).get("finalState") or {}
        return bool(final_state.get("exists") and final_state.get("sha256"))

    def _artifact_manifest(
        self,
        segment_dir: Path,
        report: dict[str, Any],
        execution: SegmentExecution,
        *,
        video_path: Path | None,
    ) -> dict[str, Any]:
        final_state = _report_path(report, "finalState")
        final_screenshot = _report_path(report, "finalScreenshot")
        records = {
            "report": artifact_record(
                execution.report_path,
                base=self.paths.lineage_root,
                required=True,
                kind="report",
            ),
            "checkpoint": artifact_record(
                segment_dir / "checkpoint.json",
                base=self.paths.lineage_root,
                required=True,
                kind="checkpoint",
            ),
            "finalState": artifact_record(
                final_state,
                base=self.paths.lineage_root,
                required=True,
                kind="emulator_state",
            ),
            "screenshot": artifact_record(
                final_screenshot,
                base=self.paths.lineage_root,
                required=True,
                kind="screenshot",
            ),
            "video": artifact_record(
                video_path,
                base=self.paths.lineage_root,
                required=False,
                kind="video",
            ),
            "stdout": artifact_record(
                execution.stdout_path,
                base=self.paths.lineage_root,
                required=False,
                kind="process_stdout",
            ),
            "stderr": artifact_record(
                execution.stderr_path,
                base=self.paths.lineage_root,
                required=False,
                kind="process_stderr",
            ),
        }
        records["complete"] = all(
            record.get("exists") for record in records.values() if record.get("required")
        )
        return records

    def _bundle_video(self, segment_dir: Path, report: dict[str, Any]) -> Path | None:
        video = report.get("video") if isinstance(report.get("video"), dict) else {}
        raw = video.get("bundlePath") or video.get("localVideoPath") or video.get("dropboxPath")
        if not raw:
            return None
        source = Path(str(raw)).resolve()
        if not source.is_file():
            return None
        destination = segment_dir / "segment.mp4"
        if source != destination.resolve():
            shutil.copy2(source, destination)
        return destination

    def _diagnostic_summary(
        self,
        report: dict[str, Any],
        checkpoint: dict[str, Any],
        artifacts: dict[str, Any],
    ) -> dict[str, Any]:
        finish = report.get("finish") if isinstance(report.get("finish"), dict) else {}
        history = report.get("history") if isinstance(report.get("history"), list) else []
        evidence = checkpoint.get("evidence") if isinstance(checkpoint.get("evidence"), list) else []
        verdict = str(checkpoint.get("verdict") or "")
        needs_diagnosis = verdict in {
            "stalled_loop",
            "skill_gap",
            "state_interpretation_gap",
            "model_error",
            "unsafe_state",
            "supervisor_error",
        }
        has_reason = bool(
            finish.get("failureCategory")
            or finish.get("stopReason")
            or checkpoint.get("summary")
        )
        required_artifacts = all(
            (artifacts.get(name) or {}).get("exists")
            for name in ("checkpoint", "report")
        )
        diagnosable = bool(evidence and has_reason and required_artifacts)
        return {
            "needsDiagnosis": needs_diagnosis,
            "diagnosable": diagnosable,
            "verdict": verdict,
            "failureCategory": finish.get("failureCategory"),
            "stopReason": finish.get("stopReason"),
            "actionCount": len(history),
            "evidenceCount": len(evidence),
            "summary": str(checkpoint.get("summary") or "")[:500],
        }

    def _queue_review(self, segment: dict[str, Any]) -> None:
        checkpoint = segment.get("checkpoint") if isinstance(segment.get("checkpoint"), dict) else {}
        raw_items = checkpoint.get("reviewItems") if isinstance(checkpoint.get("reviewItems"), list) else []
        if not raw_items:
            raw_items = [{"kind": checkpoint.get("verdict"), "summary": checkpoint.get("summary")}]
        for index, item in enumerate(raw_items, start=1):
            item = item if isinstance(item, dict) else {"summary": str(item)}
            identifier = f"{segment.get('segmentId')}-{index:02d}"
            atomic_write_json(
                self.paths.reviews / f"{identifier}.json",
                {
                    "schema": "supervisor_review_item_v1",
                    "id": identifier,
                    "lineageId": self.paths.lineage_id,
                    "segmentId": segment.get("segmentId"),
                    "createdUtc": utc_now(),
                    "status": "queued",
                    "kind": item.get("kind") or checkpoint.get("verdict"),
                    "summary": item.get("summary") or checkpoint.get("summary"),
                    "evidence": checkpoint.get("evidence") or [],
                    "manifestPath": f"segments/{segment.get('segmentId')}/manifest.json",
                },
            )

    def _quarantine_failure(self, segment: dict[str, Any]) -> None:
        identifier = str(segment.get("segmentId") or uuid.uuid4().hex)
        atomic_write_json(
            self.paths.failures / f"{identifier}.json",
            {
                "schema": "supervisor_failure_v1",
                "lineageId": self.paths.lineage_id,
                "segmentId": segment.get("segmentId"),
                "createdUtc": utc_now(),
                "checkpoint": segment.get("checkpoint"),
                "finish": segment.get("finish"),
                "diagnostic": segment.get("diagnostic"),
                "lastSafeState": self._manifest().get("lastSafeState"),
                "manifestPath": f"segments/{identifier}/manifest.json",
            },
        )

    def _recover_interrupted_segment(self) -> dict[str, Any] | None:
        state = read_json(self.paths.state) or {}
        if str(state.get("state") or "idle") not in ACTIVE_STATES:
            return None
        segment_id = str(state.get("currentSegment") or "")
        if not segment_id:
            self._transition("idle", reason="recovered_missing_segment_reference")
            return None
        require_safe_component(segment_id, label="segment id")
        segment_dir = self.paths.segments / segment_id
        registration = read_json(segment_dir / "manifest.json") or {}
        sequence = int(registration.get("sequence") or 0)
        attempt = int(registration.get("attempt") or 1)
        input_state = Path(str(registration.get("inputState") or ""))
        if not input_state.is_file():
            input_state = self._last_safe_state(self._manifest()) or input_state
        pid = state.get("childPid") or registration.get("childPid")
        child_started_epoch = state.get("childStartedEpoch") or registration.get(
            "childStartedEpoch"
        )
        if pid:
            self._record_event("adopting_interrupted_segment", {"segmentId": segment_id, "pid": pid})
            while _process_alive(
                int(pid),
                expected_started_epoch=float(child_started_epoch)
                if child_started_epoch
                else None,
            ):
                self._heartbeat_once()
                time.sleep(max(self.config.adopt_poll_seconds, 0.05))
        request = SegmentRequest(
            lineage_id=self.paths.lineage_id,
            segment_id=segment_id,
            sequence=sequence,
            attempt=attempt,
            input_state=input_state,
            segment_dir=segment_dir,
        )
        if request.report_path.is_file():
            execution = SegmentExecution(
                report_path=request.report_path,
                return_code=int(registration.get("returnCode") or 0),
                child_pid=int(pid) if pid else None,
                stdout_path=segment_dir.parent / f".{segment_id}.stdout.log",
                stderr_path=segment_dir.parent / f".{segment_id}.stderr.log",
            )
            self._record_event("recovered_completed_segment", {"segmentId": segment_id})
            return self._finalize_segment(request, execution)
        registration.update(
            {
                "status": "interrupted",
                "completedUtc": utc_now(),
                "checkpoint": {
                    "schema": "checkpoint_interrogation_v1",
                    "verdict": "supervisor_interruption",
                    "confidence": "high",
                    "continueRecommended": True,
                    "summary": "Supervisor restarted after the child ended without a report; the prior safe state remains authoritative.",
                    "evidence": ["child_alive=false", "report_exists=false"],
                    "reviewItems": [],
                    "fallbackTaken": ["continue_from_previous_safe_state"],
                },
                "diagnostic": {"needsDiagnosis": True, "diagnosable": True},
            }
        )
        atomic_write_json(segment_dir / "manifest.json", registration)
        self._register_segment(registration)
        self._queue_review(registration)
        self._advance_sequence(registration)
        return None

    def _ensure_layout(self) -> None:
        for directory in (
            self.paths.lineage_root,
            self.paths.segments,
            self.paths.reviews,
            self.paths.failures,
            self.paths.events,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.paths.manifest.exists():
            if self.config.initial_state is None or not self.config.initial_state.is_file():
                raise FileNotFoundError("A real --initial-state is required for a new lineage.")
            atomic_write_json(
                self.paths.manifest,
                {
                    "schema": "segment_lineage_manifest_v1",
                    "lineageId": self.paths.lineage_id,
                    "createdUtc": utc_now(),
                    "updatedUtc": utc_now(),
                    "nextSequence": 1,
                    "lastSafeState": {
                        "path": str(self.config.initial_state.resolve()),
                        "segmentId": None,
                        "updatedUtc": utc_now(),
                    },
                    "segments": [],
                },
            )
        if not self.paths.state.exists():
            self._transition("idle", reason="supervisor_initialized")

    def _manifest(self) -> dict[str, Any]:
        manifest = read_json(self.paths.manifest)
        if not manifest or manifest.get("schema") != "segment_lineage_manifest_v1":
            raise RuntimeError("Lineage manifest is missing or invalid.")
        return manifest

    def _last_safe_state(self, manifest: dict[str, Any]) -> Path | None:
        item = manifest.get("lastSafeState") if isinstance(manifest.get("lastSafeState"), dict) else {}
        raw = item.get("path")
        return Path(str(raw)).resolve() if raw else None

    def _previous_report(self) -> dict[str, Any] | None:
        segments = self._manifest().get("segments", [])
        for item in reversed(segments if isinstance(segments, list) else []):
            if not isinstance(item, dict):
                continue
            segment_id = item.get("segmentId")
            if not segment_id:
                continue
            report = read_json(self.paths.segments / str(segment_id) / "report.json")
            if report:
                return report
        return None

    def _control_signal(self) -> str:
        stop = read_json(self.paths.operator_stop) or {}
        action = str(stop.get("action") or "")
        if action in {"pause", "emergency_stop", "stop_after_action"}:
            return action
        if not self.config.operations_control_path:
            return "continue"
        control = read_json(self.config.operations_control_path) or {}
        state = str(control.get("state") or "running")
        if state == "paused":
            return "pause"
        if state == "emergency_stopped":
            return "emergency_stop"
        if control.get("stopAfterAction"):
            return "stop_after_action"
        return "continue"

    def _disk_ready(self) -> bool:
        free = shutil.disk_usage(self.paths.lineage_root).free
        self._record_event(
            "disk_check",
            {"freeBytes": free, "minimumFreeBytes": self.config.min_free_bytes},
            compact=True,
        )
        return free >= self.config.min_free_bytes

    def _transition(
        self,
        state: str,
        *,
        reason: str,
        current_segment: str | None = None,
        child_pid: int | None = None,
        child_started_epoch: float | None = None,
    ) -> None:
        if state not in SUPERVISOR_STATES:
            raise ValueError(f"Unsupported supervisor state: {state}")
        with self._state_lock:
            previous = read_json(self.paths.state) or {}
            payload = {
                "schema": "segment_supervisor_state_v1",
                "lineageId": self.paths.lineage_id,
                "state": state,
                "reason": reason,
                "revision": int(previous.get("revision") or 0) + 1,
                "ownerId": self.owner_id,
                "pid": os.getpid(),
                "currentSegment": current_segment,
                "childPid": child_pid,
                "childStartedEpoch": child_started_epoch,
                "updatedUtc": utc_now(),
            }
            atomic_write_json(self.paths.state, payload)
            self.lease.renew(state=state, current_segment=current_segment)
        self._record_event(
            "state_transition",
            {"from": previous.get("state"), "to": state, "reason": reason},
        )

    def _write_final_checkpoint(
        self,
        reason: str,
        *,
        segment: dict[str, Any] | None = None,
    ) -> None:
        state = read_json(self.paths.state) or {}
        manifest = self._manifest()
        atomic_write_json(
            self.paths.final_checkpoint,
            {
                "schema": "supervisor_final_checkpoint_v1",
                "lineageId": self.paths.lineage_id,
                "createdUtc": utc_now(),
                "supervisorState": state.get("state"),
                "reason": reason,
                "machineReason": reason,
                "segmentId": segment.get("segmentId") if segment else None,
                "segmentCheckpoint": segment.get("checkpoint") if segment else None,
                "lastSafeState": manifest.get("lastSafeState"),
                "stable": bool((manifest.get("lastSafeState") or {}).get("path")),
            },
        )

    def _record_event(
        self,
        event: str,
        fields: dict[str, Any],
        *,
        compact: bool = False,
    ) -> None:
        if compact:
            existing = sorted(self.paths.events.glob(f"*-{event}.json"), reverse=True)
            if existing:
                try:
                    age = time.time() - existing[0].stat().st_mtime
                except OSError:
                    age = 999
                if age < max(self.config.heartbeat_seconds, 1.0):
                    return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        atomic_write_json(
            self.paths.events / f"{stamp}-{event}.json",
            {
                "schema": "segment_supervisor_event_v1",
                "lineageId": self.paths.lineage_id,
                "event": event,
                "createdUtc": utc_now(),
                **fields,
            },
        )

    def _start_heartbeat(self) -> None:
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"supervisor-heartbeat-{self.paths.lineage_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=max(self.config.heartbeat_seconds * 2, 1.0))
            self._heartbeat_thread = None

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(max(self.config.heartbeat_seconds, 0.05)):
            self._heartbeat_once()

    def _heartbeat_once(self) -> None:
        with self._heartbeat_write_lock:
            state = read_json(self.paths.state) or {}
            atomic_write_json(
                self.paths.heartbeat,
                {
                    "schema": "segment_supervisor_heartbeat_v1",
                    "lineageId": self.paths.lineage_id,
                    "ownerId": self.owner_id,
                    "pid": os.getpid(),
                    "state": state.get("state") or "idle",
                    "currentSegment": state.get("currentSegment"),
                    "childPid": state.get("childPid"),
                    "childStartedEpoch": state.get("childStartedEpoch"),
                    "updatedUtc": utc_now(),
                    "updatedEpoch": time.time(),
                },
            )
            self.lease.renew(
                state=str(state.get("state") or "idle"),
                current_segment=str(state.get("currentSegment"))
                if state.get("currentSegment")
                else None,
            )

    def _stop_result(self) -> dict[str, Any]:
        return {
            "state": read_json(self.paths.state),
            "checkpoint": read_json(self.paths.final_checkpoint),
            "manifest": self._manifest(),
        }


def _report_path(report: dict[str, Any], key: str) -> Path | None:
    raw = report.get(key)
    if not raw and isinstance(report.get("artifacts"), dict):
        raw = report["artifacts"].get(key)
    return Path(str(raw)).resolve() if raw else None


def _lock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle: Any) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _process_started_epoch(pid: int) -> float | None:
    if pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        try:
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return None
        finally:
            kernel32.CloseHandle(handle)
        ticks = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        return ticks / 10_000_000 - 11_644_473_600
    stat_path = Path(f"/proc/{pid}/stat")
    uptime_path = Path("/proc/uptime")
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
        uptime_seconds = float(uptime_path.read_text(encoding="utf-8").split()[0])
        clock_ticks = float(os.sysconf("SC_CLK_TCK"))
        start_since_boot = float(fields[21]) / clock_ticks
    except (FileNotFoundError, OSError, ValueError, IndexError):
        return None
    return time.time() - uptime_seconds + start_since_boot


def _process_alive(pid: int, *, expected_started_epoch: float | None = None) -> bool:
    if pid <= 0:
        return False
    current_started_epoch = _process_started_epoch(pid)
    if expected_started_epoch is not None and current_started_epoch is not None:
        if abs(current_started_epoch - expected_started_epoch) > 2:
            return False
    if os.name == "nt":
        return current_started_epoch is not None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
